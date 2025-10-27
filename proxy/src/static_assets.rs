use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use async_trait::async_trait;
use bytes::Bytes;
use http::header::{
    ACCESS_CONTROL_ALLOW_CREDENTIALS, ACCESS_CONTROL_ALLOW_METHODS, ACCESS_CONTROL_ALLOW_ORIGIN,
    ACCESS_CONTROL_MAX_AGE, CACHE_CONTROL, CONTENT_LENGTH, CONTENT_TYPE, ETAG, IF_MODIFIED_SINCE,
    IF_NONE_MATCH, LAST_MODIFIED, ORIGIN, VARY,
};
use httpdate::fmt_http_date;
use log::{debug, error, info, trace};
use mime_guess::MimeGuess;
use pingora::Error;
use pingora::ErrorType;
use pingora::http::ResponseHeader;
use pingora::prelude::*;
use pingora::proxy::Session;
use pingora::server::ShutdownWatch;
use pingora::services::background::{BackgroundService, background_service};
use tokio::fs;
use tokio::io::AsyncReadExt;
use tokio::sync::RwLock;

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(untagged)]
pub enum ManifestValue {
    Direct(String),
    Entry { file: String },
}

/// Configuration for serving static assets.
#[derive(Clone, Debug)]
pub struct StaticAssetConfig {
    pub mount_path: String,
    pub root: PathBuf,
    pub index_file: String,
    pub manifest_path: Option<PathBuf>,
    pub immutable_cache_seconds: u64,
    pub default_cache_seconds: u64,
    pub keepalive_seconds: u64,
}

#[derive(Clone, Debug)]
struct ManifestState {
    entries: HashMap<String, String>,
    last_modified: Option<SystemTime>,
}

#[derive(Clone)]
struct ManifestHandle {
    path: PathBuf,
    state: Arc<RwLock<ManifestState>>,
}

impl ManifestHandle {
    fn new(path: PathBuf, initial: ManifestState) -> Self {
        Self {
            path,
            state: Arc::new(RwLock::new(initial)),
        }
    }

    async fn get(&self, logical: &str) -> Option<String> {
        let guard = self.state.read().await;
        guard.entries.get(logical).cloned()
    }

    async fn reload_if_needed(&self) {
        match fs::metadata(&self.path).await {
            Ok(metadata) => {
                let modified = metadata.modified().ok();
                {
                    let guard = self.state.read().await;
                    if guard.last_modified == modified {
                        trace!(
                            "manifest at {:?} unchanged (mtime: {:?})",
                            self.path, modified
                        );
                        return;
                    }
                }

                match fs::read_to_string(&self.path).await {
                    Ok(contents) => match parse_manifest_entries(&contents) {
                        Ok(entries) => {
                            info!(
                                "reloaded static manifest {:?} with {} entries",
                                self.path,
                                entries.len()
                            );
                            let mut guard = self.state.write().await;
                            guard.entries = entries;
                            guard.last_modified = modified;
                        }
                        Err(err) => {
                            error!("failed to parse manifest {:?}: {}", self.path, err);
                        }
                    },
                    Err(err) => {
                        error!("failed to read manifest {:?}: {}", self.path, err);
                    }
                }
            }
            Err(err) => {
                error!("manifest {:?} metadata error: {}", self.path, err);
            }
        }
    }
}

#[derive(Clone, Debug)]
struct ResolvedFile {
    full_path: PathBuf,
    logical_path: String,
    from_manifest: bool,
}

/// Handles resolving and serving static assets from disk.
#[derive(Clone)]
pub struct StaticAssets {
    mount_path: String,
    root: PathBuf,
    index_file: String,
    manifest: Option<ManifestHandle>,
    immutable_cache_seconds: u64,
    default_cache_seconds: u64,
    keepalive_seconds: u64,
}

impl StaticAssets {
    pub fn new(config: StaticAssetConfig) -> std::io::Result<Self> {
        let manifest = if let Some(path) = config.manifest_path {
            let state = load_manifest_blocking(&path)?;
            Some(ManifestHandle::new(path, state))
        } else {
            None
        };

        Ok(Self {
            mount_path: normalise_prefix(&config.mount_path),
            root: config.root,
            index_file: config.index_file,
            manifest,
            immutable_cache_seconds: config.immutable_cache_seconds,
            default_cache_seconds: config.default_cache_seconds,
            keepalive_seconds: config.keepalive_seconds,
        })
    }

    pub fn manifest_background(
        &self,
        poll_seconds: u64,
    ) -> Option<pingora::services::background::GenBackgroundService<StaticManifestService>> {
        self.manifest.as_ref().map(|handle| {
            background_service(
                "static manifest reload",
                StaticManifestService {
                    handle: handle.clone(),
                    interval: Duration::from_secs(poll_seconds.max(1)),
                },
            )
        })
    }

    pub async fn try_serve(&self, session: &mut Session) -> Result<bool> {
        match session.req_header().method.as_str() {
            "GET" | "HEAD" => {}
            _ => return Ok(false),
        }

        let path = session.req_header().uri.path();
        let Some(resolved) = self.resolve(path).await else {
            return Ok(false);
        };

        match fs::metadata(&resolved.full_path).await {
            Ok(metadata) => {
                if !metadata.is_file() {
                    debug!("static path {:?} is not a file", resolved.full_path);
                    return self.respond_not_found(session).await;
                }
                let etag = build_etag(metadata.len(), metadata.modified().ok());
                let last_modified = metadata.modified().ok().map(fmt_http_date);
                if self.is_not_modified(session, &etag, last_modified.as_deref()) {
                    return self
                        .respond_not_modified(session, &etag, last_modified.as_deref())
                        .await;
                }
                self.respond_with_file(session, resolved, metadata.len(), etag, last_modified)
                    .await
            }
            Err(err) => {
                if err.kind() == std::io::ErrorKind::NotFound {
                    debug!(
                        "static asset miss for {:?}, falling back to upstream",
                        resolved.full_path
                    );
                    return Ok(false);
                }
                error!(
                    "error accessing static asset {:?}: {}",
                    resolved.full_path, err
                );
                Err(Error::because(
                    ErrorType::FileReadError,
                    format!("failed to read static asset {:?}", resolved.full_path),
                    err,
                ))
            }
        }
    }

    async fn respond_with_file(
        &self,
        session: &mut Session,
        resolved: ResolvedFile,
        len: u64,
        etag: String,
        last_modified: Option<String>,
    ) -> Result<bool> {
        let mut header = ResponseHeader::build(200, None)?;
        header.insert_header(CONTENT_LENGTH, len.to_string())?;

        if let Some(mime) = content_type_for(&resolved.logical_path) {
            header.insert_header(CONTENT_TYPE, mime)?;
        }

        header.insert_header(ETAG, etag.clone())?;
        if let Some(value) = &last_modified {
            header.insert_header(LAST_MODIFIED, value.as_str())?;
        }

        if resolved.logical_path.ends_with(".html") {
            header.insert_header(CACHE_CONTROL, "no-cache, must-revalidate")?;
        } else {
            let cache_header = if resolved.from_manifest {
                format!(
                    "public, max-age={}, immutable",
                    self.immutable_cache_seconds
                )
            } else {
                format!("public, max-age={}", self.default_cache_seconds)
            };
            header.insert_header(CACHE_CONTROL, cache_header)?;
        }

        apply_cors(session, &mut header)?;

        let head_only = session.req_header().method.as_str() == "HEAD";
        session
            .write_response_header(Box::new(header), head_only)
            .await?;

        if head_only {
            session.finish_body().await?;
            return Ok(true);
        }

        let mut file = fs::File::open(&resolved.full_path).await.map_err(|err| {
            Error::because(
                ErrorType::FileOpenError,
                format!("failed to open static asset {:?}", resolved.full_path),
                err,
            )
        })?;
        let mut buffer = vec![0u8; 16 * 1024];
        loop {
            let n = file.read(&mut buffer).await.map_err(|err| {
                Error::because(
                    ErrorType::FileReadError,
                    format!("failed to read static asset {:?}", resolved.full_path),
                    err,
                )
            })?;
            if n == 0 {
                break;
            }
            session
                .write_response_body(Some(Bytes::copy_from_slice(&buffer[..n])), false)
                .await?;
        }
        session.finish_body().await?;
        session.set_keepalive(Some(self.keepalive_seconds));
        info!("served static asset {}", resolved.logical_path);
        Ok(true)
    }

    async fn respond_not_modified(
        &self,
        session: &mut Session,
        etag: &str,
        last_modified: Option<&str>,
    ) -> Result<bool> {
        let mut header = ResponseHeader::build(304, None)?;
        header.insert_header(ETAG, etag)?;
        if let Some(value) = last_modified {
            header.insert_header(LAST_MODIFIED, value)?;
        }
        apply_cors(session, &mut header)?;
        session
            .write_response_header(Box::new(header), true)
            .await?;
        session.finish_body().await?;
        Ok(true)
    }

    async fn respond_not_found(&self, session: &mut Session) -> Result<bool> {
        let mut header = ResponseHeader::build(404, None)?;
        header.insert_header(CONTENT_TYPE, "text/plain; charset=utf-8")?;
        apply_cors(session, &mut header)?;
        session
            .write_response_header(Box::new(header), false)
            .await?;
        let body = Bytes::from_static(b"404 not found");
        session.write_response_body(Some(body), true).await?;
        session.finish_body().await?;
        Ok(true)
    }

    fn is_not_modified(&self, session: &Session, etag: &str, last_modified: Option<&str>) -> bool {
        if let Some(value) = session
            .req_header()
            .headers
            .get(IF_NONE_MATCH)
            .and_then(|v| v.to_str().ok())
            && value.split(',').any(|candidate| candidate.trim() == etag)
        {
            return true;
        }

        if let (Some(if_modified_since), Some(last_modified)) = (
            session
                .req_header()
                .headers
                .get(IF_MODIFIED_SINCE)
                .and_then(|v| v.to_str().ok()),
            last_modified,
        ) && if_modified_since == last_modified
        {
            return true;
        }
        false
    }

    async fn resolve(&self, request_path: &str) -> Option<ResolvedFile> {
        if !request_path.starts_with(&self.mount_path) {
            return None;
        }

        let mut trimmed = &request_path[self.mount_path.len()..];
        if trimmed.starts_with('/') {
            trimmed = &trimmed[1..];
        }

        let logical = if trimmed.is_empty() || trimmed.ends_with('/') {
            format!("{trimmed}{}", self.index_file)
        } else {
            trimmed.to_string()
        };

        if contains_illegal_component(&logical) {
            debug!("rejecting static path with illegal components: {}", logical);
            return None;
        }

        let mut from_manifest = false;
        let mut file_path = logical.clone();

        let should_consult_manifest = !logical.ends_with(".html");

        if should_consult_manifest
            && let Some(manifest) = &self.manifest
            && let Some(mapped) = manifest.get(&logical).await
        {
            file_path = mapped;
            from_manifest = true;
        }

        if contains_illegal_component(&file_path) {
            debug!(
                "rejecting mapped static path with illegal components: {}",
                file_path
            );
            return None;
        }

        let mut full_path = self.root.clone();
        full_path.push(Path::new(&file_path));

        Some(ResolvedFile {
            full_path,
            logical_path: logical,
            from_manifest,
        })
    }

    pub fn mount_path(&self) -> &str {
        &self.mount_path
    }

    pub fn root_path(&self) -> &Path {
        &self.root
    }
}

fn build_etag(len: u64, modified: Option<SystemTime>) -> String {
    match modified.and_then(|ts| ts.duration_since(UNIX_EPOCH).ok()) {
        Some(duration) => format!("\"{:x}-{:x}\"", len, duration.as_secs()),
        None => format!("\"{:x}\"", len),
    }
}

fn content_type_for(path: &str) -> Option<String> {
    MimeGuess::from_path(path)
        .first()
        .map(|mime| mime.essence_str().to_string())
}

fn contains_illegal_component(path: &str) -> bool {
    Path::new(path)
        .components()
        .any(|c| matches!(c, Component::ParentDir | Component::RootDir))
}

fn normalise_prefix(prefix: &str) -> String {
    if prefix.is_empty() {
        return "/".to_string();
    }
    if prefix == "/" {
        return prefix.to_string();
    }
    let cleaned = if prefix.starts_with('/') {
        prefix.to_string()
    } else {
        format!("/{prefix}")
    };
    cleaned.trim_end_matches('/').to_string()
}

fn load_manifest_blocking(path: &Path) -> std::io::Result<ManifestState> {
    let metadata = std::fs::metadata(path)?;
    let modified = metadata.modified().ok();
    let contents = std::fs::read_to_string(path)?;
    let entries = parse_manifest_entries(&contents)
        .map_err(|err| std::io::Error::new(std::io::ErrorKind::InvalidData, err))?;
    Ok(ManifestState {
        entries,
        last_modified: modified,
    })
}

fn parse_manifest_entries(contents: &str) -> Result<HashMap<String, String>, serde_json::Error> {
    let raw: HashMap<String, ManifestValue> = serde_json::from_str(contents)?;
    let mut map = HashMap::with_capacity(raw.len());
    for (key, value) in raw {
        let file = match value {
            ManifestValue::Direct(path) => path,
            ManifestValue::Entry { file } => file,
        };
        map.insert(key, file);
    }
    Ok(map)
}

/// Background service that refreshes the manifest on a fixed interval.
pub struct StaticManifestService {
    handle: ManifestHandle,
    interval: Duration,
}

#[async_trait]
impl BackgroundService for StaticManifestService {
    async fn start(&self, mut shutdown: ShutdownWatch) {
        info!(
            "starting static manifest watcher for {:?} (interval: {:?})",
            self.handle.path, self.interval
        );
        let mut ticker = tokio::time::interval(self.interval);
        loop {
            tokio::select! {
                _ = ticker.tick() => {
                    self.handle.reload_if_needed().await;
                }
                _ = shutdown.changed() => {
                    info!("static manifest watcher shutting down");
                    break;
                }
            }
        }
    }
}

fn apply_cors(session: &Session, header: &mut ResponseHeader) -> Result<()> {
    if let Some(origin_value) = session.req_header().headers.get(ORIGIN) {
        header.insert_header(ACCESS_CONTROL_ALLOW_ORIGIN, origin_value)?;
        header.append_header(VARY, "Origin")?;
        header.insert_header(ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")?;
        header.insert_header(
            ACCESS_CONTROL_ALLOW_METHODS,
            "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        )?;
        header.insert_header(ACCESS_CONTROL_MAX_AGE, "86400")?;
    }
    Ok(())
}

mod static_assets;

use async_trait::async_trait;
use http::header::{
    ACCESS_CONTROL_ALLOW_CREDENTIALS, ACCESS_CONTROL_ALLOW_METHODS, ACCESS_CONTROL_ALLOW_ORIGIN,
    ACCESS_CONTROL_MAX_AGE, ORIGIN, VARY,
};
use log::info;
use pingora::http::{Method, ResponseHeader};
use pingora::prelude::*;
use pingora::proxy::http_proxy_service;
use pingora::server::configuration::{Opt, ServerConf};
use serde::Deserialize;
use std::fs;
use std::path::PathBuf;

use static_assets::{StaticAssetConfig, StaticAssets};

const DEFAULT_STATIC_MOUNT: &str = "/";
const DEFAULT_STATIC_INDEX: &str = "index.html";
const DEFAULT_STATIC_CACHE_SECONDS: u64 = 60;
const DEFAULT_STATIC_IMMUTABLE_CACHE_SECONDS: u64 = 60 * 60 * 24 * 365; // 1 year
const DEFAULT_STATIC_KEEPALIVE_SECONDS: u64 = 60;
const DEFAULT_STATIC_MANIFEST_POLL_SECONDS: u64 = 5;

#[derive(Deserialize, Debug, Clone)]
struct Config {
    upstream_addr: String,
    listen_addr: Option<String>,
    log_level: Option<String>,
    grace_period_seconds: Option<u64>,
    graceful_shutdown_timeout_seconds: Option<u64>,
    static_root: Option<String>,
    static_mount: Option<String>,
    static_index_file: Option<String>,
    static_manifest: Option<String>,
    static_default_cache_seconds: Option<u64>,
    static_immutable_cache_seconds: Option<u64>,
    static_keepalive_seconds: Option<u64>,
    static_manifest_poll_seconds: Option<u64>,
}

#[derive(Clone)]
pub struct RoseProxy {
    upstream_addr: String,
    static_assets: Option<StaticAssets>,
}

#[async_trait]
impl ProxyHttp for RoseProxy {
    type CTX = ();
    fn new_ctx(&self) -> Self::CTX {}

    async fn upstream_peer(
        &self,
        _session: &mut Session,
        _ctx: &mut Self::CTX,
    ) -> Result<Box<HttpPeer>> {
        let peer = Box::new(HttpPeer::new(&self.upstream_addr, false, "".to_string()));
        Ok(peer)
    }

    async fn upstream_request_filter(
        &self,
        _session: &mut Session,
        upstream_request: &mut RequestHeader,
        _ctx: &mut Self::CTX,
    ) -> Result<()> {
        let host = self
            .upstream_addr
            .split(':')
            .next()
            .unwrap_or(&self.upstream_addr);
        upstream_request.insert_header("Host", host)?;
        Ok(())
    }

    async fn response_filter(
        &self,
        session: &mut Session,
        response: &mut ResponseHeader,
        _ctx: &mut Self::CTX,
    ) -> Result<()> {
        if let Some(origin_value) = session.req_header().headers.get(ORIGIN) {
            response.insert_header(ACCESS_CONTROL_ALLOW_ORIGIN, origin_value)?;

            response.append_header(VARY, "Origin")?;

            response.insert_header(ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")?;

            response.insert_header(
                ACCESS_CONTROL_ALLOW_METHODS,
                "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            )?
        }

        Ok(())
    }

    async fn request_filter(&self, session: &mut Session, _ctx: &mut Self::CTX) -> Result<bool> {
        if let Some(static_assets) = &self.static_assets
            && static_assets.try_serve(session).await?
        {
            return Ok(true);
        }

        if session.req_header().method == Method::OPTIONS {
            if let Some(origin_value) = session.req_header().headers.get(ORIGIN) {
                let mut resp = ResponseHeader::build(204, None)?;

                resp.insert_header(ACCESS_CONTROL_ALLOW_ORIGIN, origin_value)?;

                resp.insert_header(ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")?;

                resp.insert_header(
                    ACCESS_CONTROL_ALLOW_METHODS,
                    "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                )?;

                resp.insert_header(ACCESS_CONTROL_MAX_AGE, "86400")?; // 1 day

                session.write_response_header(Box::new(resp), true).await?;
                session.finish_body().await?;
                return Ok(true);
            } else {
                session.respond_error(200).await?;
                return Ok(true);
            }
        }
        Ok(false)
    }
}

fn main() {
    let config_path = "/proxy/config.toml";
    let config_str = fs::read_to_string(config_path)
        .unwrap_or_else(|_| panic!("Failed to read config file: {}", config_path));

    let config: Config = toml::from_str(&config_str)
        .unwrap_or_else(|_| panic!("Failed to parse config file: {}", config_path));

    let log_level_filter = config
        .log_level
        .clone()
        .unwrap_or_else(|| "info".to_string());

    env_logger::Builder::new()
        .parse_filters(&log_level_filter)
        .init();

    info!("Loaded configuration: {:?}", config);

    let listen_addr = config
        .listen_addr
        .clone()
        .expect("listen_addr must be set in the config file");

    let opt = Opt::parse_args();

    let default_conf = ServerConf::default();
    let server_conf = ServerConf {
        grace_period_seconds: config
            .grace_period_seconds
            .or(default_conf.grace_period_seconds),
        graceful_shutdown_timeout_seconds: config
            .graceful_shutdown_timeout_seconds
            .or(default_conf.graceful_shutdown_timeout_seconds),
        ..default_conf
    };
    info!("Using ServerConf: {:?}", server_conf);

    let mut my_server = Server::new_with_opt_and_conf(opt, server_conf);

    my_server.bootstrap();

    let static_assets = config
        .static_root
        .as_ref()
        .map(|root| build_static_assets(&config, root));

    if let Some(ref assets) = static_assets {
        info!(
            "Static assets enabled: mount '{}' -> {:?}",
            assets.mount_path(),
            assets.root_path()
        );
    }

    let manifest_poll = config
        .static_manifest_poll_seconds
        .unwrap_or(DEFAULT_STATIC_MANIFEST_POLL_SECONDS);

    if let Some(ref assets) = static_assets
        && let Some(manifest_service) = assets.manifest_background(manifest_poll)
    {
        my_server.add_service(manifest_service);
    }

    let proxy_config = RoseProxy {
        upstream_addr: config.upstream_addr.clone(),
        static_assets: static_assets.clone(),
    };

    let mut proxy_service = http_proxy_service(&my_server.configuration, proxy_config);

    proxy_service.add_tcp(&listen_addr);
    info!("Proxy listening on {}", listen_addr);

    my_server.add_service(proxy_service);

    info!("Starting server...");
    my_server.run_forever();
}

fn build_static_assets(config: &Config, root: &str) -> StaticAssets {
    let asset_root = PathBuf::from(root);
    let mount_path = config
        .static_mount
        .as_deref()
        .unwrap_or(DEFAULT_STATIC_MOUNT);
    let index_file = config
        .static_index_file
        .as_deref()
        .unwrap_or(DEFAULT_STATIC_INDEX);
    let manifest_path = config.static_manifest.as_ref().map(PathBuf::from);
    let immutable_cache_seconds = config
        .static_immutable_cache_seconds
        .unwrap_or(DEFAULT_STATIC_IMMUTABLE_CACHE_SECONDS);
    let default_cache_seconds = config
        .static_default_cache_seconds
        .unwrap_or(DEFAULT_STATIC_CACHE_SECONDS);
    let keepalive_seconds = config
        .static_keepalive_seconds
        .unwrap_or(DEFAULT_STATIC_KEEPALIVE_SECONDS);

    let asset_config = StaticAssetConfig {
        mount_path: mount_path.to_string(),
        root: asset_root,
        index_file: index_file.to_string(),
        manifest_path,
        immutable_cache_seconds,
        default_cache_seconds,
        keepalive_seconds,
    };

    StaticAssets::new(asset_config)
        .unwrap_or_else(|err| panic!("Failed to initialise static assets with root {root}: {err}"))
}

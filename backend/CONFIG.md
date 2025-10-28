# Configuration Reference

The backend reads all runtime settings from `config.toml` (located at the repository root). This document explains each section, default values, and how to override the configuration per environment.

## Loading rules

- `app/config.py` loads `config.toml` on startup.
- Set `APP_CONFIG_FILE=/path/to/custom.toml` to point to an alternate file.
- Environment variables take precedence over file values for sensitive fields:
  - `REGISTRATION_TOKEN`
  - `JWT_SECRET_KEY`
  - `JWT_ALGORITHM`
  - `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `REFRESH_TOKEN_EXPIRE_DAYS`
  - `DATABASE_URL`
  - `OPENAI_BASE_URL`
  - `OPENAI_API_KEY`
  - `WEB_SEARCH_TIMEOUT`
  - `LLM_TEMPERATURE`
  - `LLM_TOP_P`
  - `LLM_MAX_TOKENS`
  - `LLM_FREQUENCY_PENALTY`
  - `LLM_PRESENCE_PENALTY`
  - `MAX_FILE_SIZE`
  - `LIBREOFFICE_TIMEOUT`
  - `LIBREOFFICE_PATH`
  - `DDGS_TIMEOUT`
  - `DDGS_VERIFY_SSL`
  - `DDGS_PROXY`
  - `DDGS_MAX_THREADS`
  - `DDGS_CACHE_TTL_SECONDS`
  - `DDGS_CACHE_MAXSIZE`

> **Tip:** Check the `Config` class in `app/config.py` for the authoritative list of overrides and defaults.

## Sections

| Section              | Description                                                          |
| -------------------- | -------------------------------------------------------------------- |
| `[registration]`     | Shared token that gatekeeps user signups.                            |
| `[jwt]`              | Secrets & timeouts for access/refresh tokens.                        |
| `[database]`         | Database connection string (`sqlite:///./data/app.db` by default).   |
| `[openai]`           | Base URL, API key, and available model definitions.                  |
| `[ddgs]`             | Defaults for the DDGS web search tool (region, backend, caching).    |
| `[web_search]`       | Model fallback order and timeout for the search tool.                |
| `[llm]`              | Default sampling parameters applied to chat completions.             |
| `[prompts]`          | System prompt plus error/warning messages shown to the agent.        |
| `[file_uploads]`     | File size limit, allowed MIME types, and image compression settings. |
| `[libreoffice]`      | CLI path and timeout values for LibreOffice conversions.             |
| `[agent]`            | Agent loop guard rails (max iterations, tool retry limit).           |
| `[background_tasks]` | Worker pool size for background document processing.                 |

## Example snippet

```toml
[registration]
token = "CHANGE_ME"

[jwt]
secret_key = "change-this-secret"
algorithm = "HS256"
access_token_expire_minutes = 30
refresh_token_expire_days = 7

[openai]
base_url = "https://api.openai.com/v1"
api_key = "sk-your-api-key"

[[openai.available_models]]
id = "gpt-5-chat-latest"
name = "GPT-5"
supports_vision = true
```

## Adding a model

Append another `[[openai.available_models]]` block with `id`, `name`, and `supports_vision`. The `/api/models` endpoint exposes this list to clients.

## DDGS search configuration

The `[ddgs]` section tunes the built-in `ddgs_search` tool:

- `default_category`: One of `text`, `images`, `news`, `videos`, `books`.
- `default_backend`: Comma-separated backend list or `auto`.
- `default_region`: Region code such as `us-en`, `cn-zh`.
- `default_safesearch`: `on`, `moderate`, or `off`.
- `default_timelimit`: Optional time filter (`d`, `w`, `m`, `y`). Leave blank for none.
- `timeout`: Per-request timeout in seconds passed to DDGS.
- `verify_ssl`: Whether to verify TLS certificates.
- `proxy`: Optional proxy (supports `http`, `https`, `socks5`, or `tb` for Tor Browser).
- `max_threads`: Upper bound for the DDGS thread pool (`None`/empty uses library default).
- `cache_ttl_seconds`: How long cached search results are reused.
- `cache_maxsize`: Maximum number of cached query variants.

## File upload configuration

- `file_uploads.max_file_size`: max upload size in bytes (default 50 MB).
- `file_uploads.allowed_file_types`: MIME types grouped by logical type (`image`, `pdf`, `docx`, `ppt`).
- `file_uploads.image`: Controls WebP output (`format`, `compression_quality`, `max_dimension`).

## LibreOffice & pdf2image

- Ensure `libreoffice` CLI is installed and matches the `libreoffice.path`.
- `libreoffice.timeout` guards long-running conversions.
- `libreoffice.pdf_to_image_dpi` controls rendering DPI before compression.

## Background processing

`background_tasks.max_workers` controls the `ThreadPoolExecutor` size used for async document conversion. Tune this based on available CPU cores to avoid over-saturation.

## Deployment checklist

1. Replace placeholder secrets (`registration.token`, `jwt.secret_key`, `openai.api_key`).
2. Point `database.url` to your production database.
3. Verify LibreOffice and Poppler are installed on the target host.
4. Adjust `file_uploads.max_file_size` to match business requirements.
5. Update model IDs to those available in your OpenAI-compatible provider.
6. (Optional) Set environment variables for secrets instead of committing them to `config.toml`.

# ActReply Agent Backend

Backend service for the ActReply agent, powered by FastAPI, SQLite, and OpenAI.

## Highlights

- JWT authentication with access and refresh tokens
- Conversation and message management
- File uploads with image/PDF/DOCX/PPT processing
- Document-to-image conversion (WebP)
- Tool orchestration with single-tool enforcement
- Server-Sent Events (12 event types) for streaming responses
- Multimodal support (text + image)

## Requirements

- Python 3.8+ (3.12 recommended)
- LibreOffice (DOCX/PPT conversion)
- `poppler-utils` (PDF rendering)
- `libmagic` (MIME detection)

## Installation

### 1. System dependencies (Debian/Ubuntu example)

```bash
sudo apt-get update
sudo apt-get install -y \
    libreoffice libreoffice-writer libreoffice-impress \
    poppler-utils libmagic1
```

Install fonts if you expect to render CJK content:

```bash
sudo apt-get install -y fonts-noto-cjk
```

### 2. Python dependencies

Using pip:

```bash
# Project dependencies
pip install -e .

# Development extras (tests, linters, formatter)
pip install -e ".[dev]"
```

Using uv (faster resolver):

```bash
pip install uv
uv pip install -e .
```

## Configuration

All runtime settings live in `config.toml`. See [CONFIG.md](CONFIG.md) for a complete reference, including environment-variable overrides. At minimum, update:

- `registration.token`
- `jwt.secret_key`
- `openai.base_url`
- `openai.api_key`
- `openai.available_models`

## Running the app

### Development

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# Single worker
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Multi-worker
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

After startup:

- OpenAPI docs: <http://localhost:8000/docs>
- ReDoc docs: <http://localhost:8000/redoc>
- Health check: <http://localhost:8000/health>

## Project layout

- `app/` – FastAPI application, APIs, services, models
- `config.toml` – Default configuration (sanitize secrets before committing)
- `pyproject.toml` – Dependencies and tooling configuration
- `CODE_QUALITY.md` – Formatting, linting, typing workflow
- `CONFIG.md` – Configuration reference
- `README.md` – This guide

Planning notes are available in `plan.md` (if present).

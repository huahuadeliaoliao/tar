# Tar Agent System

Tar stands for **Tool Act Reply**. This stack combines a FastAPI backend, proxy, and frontend to deliver an agent that executes tool calls, handles multimodal uploads, and streams responses.

## Highlights

- JWT-secured API with conversation & file management
- Document conversion (DOCX/PPT → WebP via LibreOffice) and PDF/image ingestion
- Docker-based dev/prod setups with optional proxy

## Quick start (Docker Compose)

```bash
# Development (bind-mount source, hot reload)
docker compose --profile dev up --build -d

# Production-style run
docker compose --profile prod up --build -d

# Use prebuilt images from Aliyun Container Registry
docker compose --profile prebuilt-acr up -d

# Use prebuilt images from Docker Hub
docker compose --profile prebuilt-dh up -d
```

Stop containers with `docker compose --profile <dev|prod> down`. Add `-v` to remove sqlite data.

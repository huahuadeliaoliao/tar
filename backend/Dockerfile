FROM astral/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
  UV_PROJECT_ENVIRONMENT=/app/.venv

# System dependencies for LibreOffice + PDF tooling + MIME detection
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  libreoffice \
  libreoffice-writer \
  libreoffice-impress \
  poppler-utils \
  libmagic1 \
  fonts-noto-cjk \
  fonts-noto-core \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata first to leverage Docker layer caching
COPY pyproject.toml README.md CODE_QUALITY.md CONFIG.md config.toml ./
# Copy application source for editable install
COPY app ./app
COPY typings ./typings

# Install Python dependencies via uv (system site-packages)
RUN uv pip install --system -e .

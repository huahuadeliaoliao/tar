FROM astral/uv:python3.12-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1 \
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"

# System dependencies for LibreOffice + PDF tooling + MIME detection + Playwright
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  libreoffice \
  libreoffice-writer \
  libreoffice-impress \
  poppler-utils \
  libmagic1 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libgbm1 \
  libgtk-3-0 \
  libnss3 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libasound2 \
  ca-certificates \
  fonts-noto-cjk \
  fonts-noto-core \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS playwright-browsers

# Install the Playwright Python package to access the CLI
RUN uv pip install --system "playwright>=1.55.0"

# Preinstall Chromium browsers and cache downloads across builds
RUN --mount=type=cache,target=/root/.cache/ms-playwright \
  python -m playwright install chromium --with-deps

FROM base

# Reuse browsers installed in the dedicated stage
COPY --from=playwright-browsers /ms-playwright /ms-playwright

# Copy project metadata first to leverage Docker layer caching
COPY pyproject.toml README.md CODE_QUALITY.md CONFIG.md config.toml ./

# Create minimal package structure for dependency installation
RUN mkdir -p app && touch app/__init__.py

# Install Python dependencies via uv (system site-packages)
# This layer will be cached as long as pyproject.toml doesn't change
RUN uv pip install --system .

# Copy application source (changes here won't invalidate dependency cache)
COPY app ./app
COPY typings ./typings

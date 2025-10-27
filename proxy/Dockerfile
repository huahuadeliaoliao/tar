FROM node:24 AS frontend-builder

RUN apt-get update && apt-get install -y curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*

# Install Bun (just once)
RUN curl -fsSL https://bun.sh/install | bash

ENV PATH="/root/.bun/bin:${PATH}"

WORKDIR /frontend

# Copy entire frontend workspace
COPY frontend/ ./

# Install dependencies and build
RUN bun install
RUN bun run build

FROM ubuntu:noble-20241118.1 AS builder

ENV PATH="/root/.cargo/bin:${PATH}"

RUN apt-get update && apt-get install -y \
  curl \
  build-essential \
  pkg-config \
  libssl-dev \
  cmake \
  clang \
  mold && \
  rm -rf /var/lib/apt/lists/* && \
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

WORKDIR /app
COPY proxy/Cargo.toml proxy/Cargo.lock ./
COPY proxy/src ./src

RUN mkdir -p .cargo && echo '[target.x86_64-unknown-linux-gnu]\nlinker = "clang"\nrustflags = ["-C", "link-arg=-fuse-ld=/usr/bin/mold"]' > .cargo/config.toml

RUN cargo build --release

FROM ubuntu:noble-20241118.1 AS runtime

RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /proxy

COPY proxy/config.toml /proxy/config.toml
COPY --from=frontend-builder /frontend/dist /proxy/frontend/dist
COPY --from=builder /app/target/release/proxy /usr/local/bin/proxy

ENTRYPOINT ["/usr/local/bin/proxy"]

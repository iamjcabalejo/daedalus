# syntax=docker/dockerfile:1
# Benchmark execution boundary (bench/README.md; plan §3.8). bench/run.py starts one container per phase
# (setup, each agent step, collection, scoring) and bind-mounts /work, /remote.git, /outside, /home/dev, /deps,
# /arm and /opt/tools; hidden tests (/hidden) are mounted only in the scoring container. No path, name or variable
# inside the image names the benchmark: the agent can list them.
#
# Every ARG below deliberately has no default: P0b (T0) pins each one and records it in the findings document.
# Nothing here may be a moving tag or "latest".
#
#   docker build -t daedalus-bench:<pin> \
#     --build-arg BASE_IMAGE=<debian-or-ubuntu-image>@sha256:<digest> \
#     --build-arg CLAUDE_CODE_VERSION=<exact version> \
#     --build-arg NODE_VERSION=<x.y.z> --build-arg NODE_SHA256=<sha256 of the linux tarball for this arch> \
#     --build-arg PNPM_VERSION=<x.y.z> \
#     --build-arg GO_VERSION=<x.y.z> --build-arg GO_SHA256=<sha256 of the linux tarball for this arch> \
#     bench/container

# P0b (T0) pins the base image by digest (name@sha256:...). It must be Debian- or Ubuntu-based (apt below).
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# P0b (T0) pins the exact Claude Code CLI version (npm package @anthropic-ai/claude-code).
ARG CLAUDE_CODE_VERSION
# P0b (T0) pins the toolchains: a Node.js release and its tarball SHA-256, pnpm, a Go release and its SHA-256.
# The checksums are per architecture: build once per architecture you run on.
# Facts the task authors found at the pinned SHAs (pick the exact versions and digests in T0; none are set here):
# - NODE_VERSION must be >= 22.21: row I (create-t3-turbo) requires it in its .nvmrc and engines.
# - PNPM_VERSION should be 10.19.0, matching row I's packageManager field.
ARG NODE_VERSION
ARG NODE_SHA256
ARG PNPM_VERSION
ARG GO_VERSION
ARG GO_SHA256
ARG TARGETARCH

# apt package versions follow the archive at build time; T0 records them (dpkg -l) with the image digest.
# gcc and libc6-dev: row G (golang-gin) depends on mattn/go-sqlite3, which needs cgo.
RUN set -eu; \
    : "${CLAUDE_CODE_VERSION:?pin in P0b T0}" "${NODE_VERSION:?pin in T0}" "${NODE_SHA256:?pin in T0}" \
      "${PNPM_VERSION:?pin in T0}" "${GO_VERSION:?pin in T0}" "${GO_SHA256:?pin in T0}"; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl gcc git libc6-dev python3 python3-venv python3-pip xz-utils; \
    rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) node_arch=x64; go_arch=amd64 ;; \
      arm64) node_arch=arm64; go_arch=arm64 ;; \
      *) echo "unsupported architecture ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner; \
    curl -fsSLo /tmp/go.tar.gz "https://go.dev/dl/go${GO_VERSION}.linux-${go_arch}.tar.gz"; \
    echo "${GO_SHA256}  /tmp/go.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/go.tar.gz -C /usr/local; \
    rm -f /tmp/node.tar.xz /tmp/go.tar.gz; \
    npm install -g "pnpm@${PNPM_VERSION}" "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    npm cache clean --force

# Mount points. The harness runs containers as the host user (--user uid:gid), so they are world-writable;
# the bind mounts replace them at run time.
RUN mkdir -p /work /remote.git /outside /home/dev /deps /arm /opt/tools /hidden \
    && chmod 0777 /work /remote.git /outside /home/dev /deps

# Each phase is a fresh container, so dependencies installed by a task's setup steps must live in /work or
# /deps (a per-run volume). A setup step that runs `python3 -m venv /deps/venv` puts that venv first on PATH
# for the agent and the scoring container too.
ENV HOME=/home/dev \
    DAEDALUS_NONINTERACTIVE=1 \
    VIRTUAL_ENV=/deps/venv \
    PATH=/deps/venv/bin:/usr/local/go/bin:/deps/go/bin:/usr/local/bin:/usr/bin:/bin \
    GOPATH=/deps/go \
    GOMODCACHE=/deps/gomod \
    GOCACHE=/deps/gocache \
    CGO_ENABLED=1 \
    npm_config_cache=/deps/npm \
    PIP_CACHE_DIR=/deps/pip \
    XDG_CACHE_HOME=/deps/cache \
    XDG_DATA_HOME=/deps/share

WORKDIR /work

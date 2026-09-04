# syntax=docker/dockerfile:1
#
# Build context is the repository root:  docker build -f runtime/image/Dockerfile .
#
# uv stays inside the image as the dependency resolver and runner -- what
# changed relative to legacy/runtime-clone is WHEN the executable version is
# fixed: at release (this build), not at task start (see legacy/runtime-clone/README.md).
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS stage-0

ARG GIT_COMMIT=unknown
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONUNBUFFERED=1 \
    GIT_COMMIT=${GIT_COMMIT}

# uv from Docker Hub (astral/uv), pinned by digest -- no ghcr.io dependency, by project policy.
COPY --from=astral/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff /uv /uvx /bin/

WORKDIR /app

COPY runtime/image/pyproject.toml runtime/image/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY ingestion ./ingestion
COPY silver ./silver
COPY runtime/image/entrypoint.py ./entrypoint.py
RUN uv sync --frozen --no-dev

LABEL org.opencontainers.image.revision=${GIT_COMMIT} \
      org.opencontainers.image.source="https://github.com/efthomsen/lakehouse-runtime-demo"

RUN useradd --uid 10001 --no-create-home worker \
    && mkdir -p /data \
    && chown worker /data \
    && rm -rf /tmp/uv-cache \
    && mkdir -p /tmp/uv-cache \
    && chown worker /tmp/uv-cache
USER worker

ENTRYPOINT ["uv", "run", "--frozen", "--no-sync", "entrypoint.py"]

# `docker compose run --rm core-test` targets this stage: the same pinned
# dependency set, plus the dev group (pytest), used to run `tests/core`
# against this image's own Python -- not a separate, potentially drifted
# environment.
FROM stage-0 AS test
USER root
# orchestration/ isn't part of the shipped workload (it runs where jobs are
# submitted from, not inside the container) but its tests are part of
# `tests/core`, so it's included here for test-time only.
COPY orchestration ./orchestration
COPY tests/__init__.py tests/conftest.py ./tests/
COPY tests/core ./tests/core
RUN uv sync --frozen && chown -R worker /tmp/uv-cache
USER worker
ENTRYPOINT ["uv", "run", "--frozen", "--no-sync", "pytest", "-p", "no:cacheprovider"]
CMD ["tests/core"]

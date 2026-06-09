# syntax=docker/dockerfile:1

# ---------- Stage 1: builder ----------
# Build wheels for all runtime deps into an isolated prefix, so the runtime
# image stays slim and free of build toolchains.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps needed by some wheels (e.g. tiktoken/asyncpg fallbacks). Removed from runtime stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies into an isolated prefix.
# Copy the dependency manifest plus a minimal package stub first, so the deps
# layer is cached and re-installed only when pyproject.toml changes — not on
# every source edit. The real source is copied into the runtime stage.
COPY pyproject.toml ./
RUN mkdir -p app && : > app/__init__.py
RUN pip install --prefix=/install .

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/install/lib/python3.12/site-packages"

# Create a dedicated non-root user/group.
RUN groupadd --system app && useradd --system --gid app --no-create-home --home-dir /app app

WORKDIR /app

# Copy installed dependencies from the builder prefix.
COPY --from=builder /install /install

# Copy application source and migration assets.
# .dockerignore keeps secrets/tests/docs out of the image.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Container-level healthcheck hitting the public /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4); sys.exit(0 if r.status==200 else 1)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]

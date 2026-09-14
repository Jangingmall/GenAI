FROM ghcr.io/astral-sh/uv:0.11.4 AS uv

FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SQLITE_PATH=/var/lib/detail-page-ai/state.sqlite3 \
    ASSET_STORE_DIR=/var/lib/detail-page-ai/assets \
    U2NET_HOME=/var/lib/detail-page-ai/models/u2net

WORKDIR /app

# The service itself is CPU-only. Playwright installs Chromium's system
# libraries in addition to the Node.js runtime used by the renderer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Keep dependency layers ahead of application source for build-cache reuse.
COPY pyproject.toml uv.lock package.json package-lock.json ./

RUN uv sync --locked --no-dev --no-install-project --no-cache \
    && npm ci --no-audit --no-fund \
    && npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

COPY src ./src
COPY web ./web
COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json
COPY scripts/runtime/render_detail_page.mjs ./scripts/runtime/render_detail_page.mjs

# This repository is intentionally source-run (no build-system table), so uv
# installs the locked dependencies while this wrapper keeps the public command
# pointed at /app/src.  That preserves PROJECT_ROOT=/app for renderer assets.
RUN printf '%s\n' '#!/bin/sh' 'exec python -c "from detail_page_ai.app import run; run()"' \
        > /app/.venv/bin/serve-ai \
    && chmod 755 /app/.venv/bin/serve-ai

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home --home-dir /home/appuser appuser \
    && mkdir -p /var/lib/detail-page-ai/models/u2net \
    && chown -R appuser:appuser /app /home/appuser /ms-playwright /var/lib/detail-page-ai

VOLUME ["/var/lib/detail-page-ai"]
EXPOSE 8000

# The public legacy route is present even when disabled and returns 404. This
# checks that FastAPI is serving without inventing a health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=3); c.request('GET','/api/v1/ai/detail-page-jobs/does-not-exist'); sys.exit(0 if c.getresponse().status == 404 else 1)"]

USER appuser
CMD ["serve-ai"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SQLITE_PATH=/var/lib/detail-page-ai/state.sqlite3 \
    ASSET_STORE_DIR=/var/lib/detail-page-ai/assets

WORKDIR /app

# The service itself is CPU-only. Playwright installs Chromium's system
# libraries in addition to the Node.js runtime used by the renderer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Keep dependency layers ahead of application source for build-cache reuse.
COPY pyproject.toml package.json package-lock.json ./

RUN python -m pip install --no-cache-dir \
        "fastapi>=0.115,<1" \
        "httpx>=0.28,<1" \
        "pillow>=10.4,<12" \
        "pydantic-settings>=2.7,<3" \
        "python-multipart>=0.0.20,<1" \
        "uvicorn>=0.34,<1" \
    && npm ci --no-audit --no-fund \
    && npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

COPY src ./src
COPY scripts/runtime/render_detail_page.mjs ./scripts/runtime/render_detail_page.mjs

# Dependencies are installed above; this layer installs the project and its
# serve-ai console entry point without reinstalling them.
RUN python -m pip install --no-cache-dir --no-deps .

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home --home-dir /home/appuser appuser \
    && mkdir -p /var/lib/detail-page-ai \
    && chown -R appuser:appuser /app /home/appuser /ms-playwright /var/lib/detail-page-ai

VOLUME ["/var/lib/detail-page-ai"]
EXPOSE 8000

# The public legacy route is present even when disabled and returns 404. This
# checks that FastAPI is serving without inventing a health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD-SHELL python -c "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=3); c.request('GET','/api/v1/ai/detail-page-jobs/does-not-exist'); sys.exit(0 if c.getresponse().status == 404 else 1)"

USER appuser
CMD ["serve-ai"]

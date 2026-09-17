FROM ghcr.io/astral-sh/uv:0.11.4 AS uv

# Playwright 1.62 in package-lock.json requires Node.js >=20. Copy the
# maintained Node 22 runtime instead of depending on the CUDA base image's
# distribution Node.js package version.
FROM node:22-bookworm-slim AS node

# The official SGLang image supplies the CUDA runtime and the text-serving
# stack.  The diffusion extra is installed below because it is not included
# in the base image.
FROM lmsysorg/sglang:v0.5.19

ARG SGLANG_VERSION=0.5.19

COPY --from=uv /uv /uvx /bin/
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    HOME=/home/appuser \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SQLITE_PATH=/var/lib/detail-page-ai/state.sqlite3 \
    ASSET_STORE_DIR=/var/lib/detail-page-ai/assets \
    U2NET_HOME=/var/lib/detail-page-ai/models/u2net \
    XDG_CACHE_HOME=/var/lib/detail-page-ai/cache \
    HF_HOME=/var/lib/detail-page-ai/models/huggingface \
    HF_HUB_CACHE=/var/lib/detail-page-ai/models/huggingface/hub \
    HF_DATASETS_CACHE=/var/lib/detail-page-ai/models/huggingface/datasets \
    TRANSFORMERS_CACHE=/var/lib/detail-page-ai/models/huggingface/hub \
    TORCH_HOME=/var/lib/detail-page-ai/models/torch \
    SGLANG_CACHE_DIR=/var/lib/detail-page-ai/cache/sglang \
    FLASHINFER_CACHE_DIR=/var/lib/detail-page-ai/cache/flashinfer \
    TRITON_CACHE_DIR=/var/lib/detail-page-ai/cache/triton \
    TORCHINDUCTOR_CACHE_DIR=/var/lib/detail-page-ai/cache/torchinductor \
    CUDA_CACHE_PATH=/var/lib/detail-page-ai/cache/cuda \
    LOCAL_TEXT_PROVIDER=sglang \
    LOCAL_IMAGE_PROVIDER=sglang \
    BACKGROUND_PROVIDER=sglang \
    LOCAL_TEXT_URL=http://127.0.0.1:30000 \
    LOCAL_IMAGE_URL=http://127.0.0.1:30001 \
    LOCAL_TEXT_MODEL=qwen-text \
    LOCAL_IMAGE_MODEL=flux-klein \
    TEXT_MODEL_PATH=cyankiwi/Qwen3.8-27B-AWQ-INT4 \
    TEXT_MODEL_REVISION=6e134bae811fb5adac50ee042ae5f029ac6779aa \
    TEXT_SERVED_MODEL_NAME=qwen-text \
    TEXT_MEM_FRACTION=0.50 \
    TEXT_CONTEXT_LENGTH=8192 \
    IMAGE_MODEL_PATH=circulus/FLUX.2-klein-9B-bnb-4bit \
    IMAGE_MODEL_REVISION=58c2804f31af12c8888504b96250010c50b55e44 \
    IMAGE_SERVED_MODEL_NAME=flux-klein

WORKDIR /app

# Preserve the base image interpreter for SGLang before the service venv is
# created and placed first on PATH below.
RUN ln -s "$(command -v python3)" /usr/local/bin/sglang-python

# Node.js is needed by the HTML renderer. Playwright installs Chromium and its
# OS libraries during the build, so runtime rendering does not download files.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Keep the dependency layers ahead of application source for build-cache reuse.
# The project has no build-system table, so uv installs the locked runtime
# dependencies without trying to install the repository as a Python package.
COPY pyproject.toml uv.lock package.json package-lock.json ./

RUN pip install --no-cache-dir \
        "sglang[diffusion]==${SGLANG_VERSION}" \
        "bitsandbytes==0.50.2" \
    && uv sync --locked --no-dev --no-install-project --no-cache \
        --python 3.13 \
    && npm ci --no-audit --no-fund \
    && npx playwright install --with-deps chromium \
    && rm -rf /root/.cache /root/.npm /home/appuser/.cache /home/appuser/.npm \
        /var/lib/apt/lists/*

COPY src ./src
# Copy only HTML/CSS templates needed by html_renderer; static demo UI files in web/ are test-only.
COPY web/detail_page.html web/detail_page.css ./web/
COPY assets/references/detail-page-layouts.json ./assets/references/detail-page-layouts.json
COPY scripts/runtime/render_detail_page.mjs ./scripts/runtime/render_detail_page.mjs
COPY sglang/entrypoint.sh /usr/local/bin/detail-page-ai-entrypoint

# Keep PROJECT_ROOT=/app while running the service directly from /app/src.
RUN printf '%s\n' '#!/bin/sh' 'exec python -c "from detail_page_ai.app import run; run()"' \
        > /app/.venv/bin/serve-ai \
    && chmod 755 /app/.venv/bin/serve-ai /usr/local/bin/detail-page-ai-entrypoint \
    && groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home \
        --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && mkdir -p \
        /var/lib/detail-page-ai/assets \
        /var/lib/detail-page-ai/cache \
        /var/lib/detail-page-ai/models/u2net \
        /var/lib/detail-page-ai/models/huggingface/hub \
        /var/lib/detail-page-ai/models/huggingface/datasets \
        /var/lib/detail-page-ai/models/torch \
        /var/lib/detail-page-ai/cache/sglang \
        /var/lib/detail-page-ai/cache/flashinfer \
        /var/lib/detail-page-ai/cache/triton \
        /var/lib/detail-page-ai/cache/torchinductor \
        /var/lib/detail-page-ai/cache/cuda \
    && chown -R appuser:appuser \
        /app /home/appuser /ms-playwright /var/lib/detail-page-ai

# EKS mounts one PVC at /var/lib/detail-page-ai. It stores SQLite at
# /var/lib/detail-page-ai/state.sqlite3, assets at /var/lib/detail-page-ai/assets,
# Hugging Face's text (about 19.6 GiB) and image (about 10.2 GiB) models at
# /var/lib/detail-page-ai/models/huggingface, rembg/U2NET weights (about 973 MB)
# at /var/lib/detail-page-ai/models/u2net, and framework caches below
# /var/lib/detail-page-ai/cache. No VOLUME is declared so EKS chooses the PVC.
# Runtime secrets such as HF_TOKEN, BACKEND_AUTH_TOKEN, and
# AI_INTERNAL_AUTH_TOKEN are intentionally not set in the image.
EXPOSE 8000 30000 30001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',8000,timeout=3); c.request('GET','/health'); sys.exit(0 if c.getresponse().status == 200 else 1)"]

USER appuser
ENTRYPOINT ["/usr/local/bin/detail-page-ai-entrypoint"]

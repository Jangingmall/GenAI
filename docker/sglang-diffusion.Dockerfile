ARG BASE_IMAGE=lmsysorg/sglang:v0.5.19
FROM ${BASE_IMAGE}

ARG SGLANG_VERSION=0.5.19
RUN pip install --no-cache-dir "sglang[diffusion]==${SGLANG_VERSION}"

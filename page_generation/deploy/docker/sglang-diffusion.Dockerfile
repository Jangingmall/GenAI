ARG BASE_IMAGE=lmsysorg/sglang:v0.5.19
FROM ${BASE_IMAGE}

ARG SGLANG_VERSION=0.5.19
# bitsandbytes is only in sglang's "test" extra, but the 4-bit (nf4) FLUX.2-klein-9B
# pipeline needs it at load time for both the transformer and the text encoder.
RUN pip install --no-cache-dir "sglang[diffusion]==${SGLANG_VERSION}" "bitsandbytes==0.50.2"

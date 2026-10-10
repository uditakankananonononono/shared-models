#!/usr/bin/env bash
# Serve Inkling-Small NVFP4 on a GPU server with vLLM (recipe: https://recipes.vllm.ai/thinkingmachines/Inkling-Small).
# Floor: >=180 GB aggregate VRAM -> 1x B300/GB300 (TP1) or 2x B200/GB200/H200 (TP2). BF16 needs ~600 GB.
# Then: INSTINCT_INKLING_LOCAL_URL=http://<server>:8000/v1 INSTINCT_INKLING_LOCAL_MODEL=thinkingmachines/Inkling-Small-NVFP4
set -euo pipefail
# Pinned image: explicit vLLM RELEASE tag plus the registry manifest-list digest.
# v0.31.0 published 2026-10-05 (GitHub release vllm-project/vllm v0.31.0); its source tree contains
# vllm/models/inkling and the inkling reasoning/tool parsers (checked at that tag). Digest read from the
# Docker registry (HEAD /v2/vllm/vllm-openai/manifests/v0.31.0) and matches Docker Hub tag metadata.
# Override only deliberately: INKLING_VLLM_IMAGE. This replaces the floating :nightly tag.
VLLM_IMAGE="${INKLING_VLLM_IMAGE:-vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3}"
# SECURITY (unchanged behavior, reviewed): --privileged gives the container near-host access, and
# --trust-remote-code runs Python code shipped in the model repo. Run only on a dedicated GPU host and
# only against the pinned model repo. Neither flag was changed by the pinning patch.
# NOTE: the model weights (thinkingmachines/Inkling-Small-NVFP4) are NOT revision-pinned here.
TP="${INKLING_TP:-2}"
PORT="${INKLING_PORT:-8000}"
exec docker run --gpus all --privileged --ipc=host -p "$PORT:8000" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e VLLM_USE_V2_MODEL_RUNNER=1 -e FLASH_ATTENTION_CUTE_DSL_CACHE_ENABLED=1 \
  "$VLLM_IMAGE" thinkingmachines/Inkling-Small-NVFP4 \
  --trust-remote-code --tokenizer-mode inkling \
  --kernel-config.enable_flashinfer_autotune=False \
  --tensor-parallel-size "$TP" \
  --enable-auto-tool-choice --tool-call-parser inkling --reasoning-parser inkling

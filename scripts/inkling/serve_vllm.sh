#!/usr/bin/env bash
# Serve Inkling-Small NVFP4 on a GPU server with vLLM (recipe: https://recipes.vllm.ai/thinkingmachines/Inkling-Small).
# Floor: >=180 GB aggregate VRAM -> 1x B300/GB300 (TP1) or 2x B200/GB200/H200 (TP2). BF16 needs ~600 GB.
# Then: INSTINCT_INKLING_LOCAL_URL=http://<server>:8000/v1 INSTINCT_INKLING_LOCAL_MODEL=thinkingmachines/Inkling-Small-NVFP4
set -euo pipefail
TP="${INKLING_TP:-2}"
PORT="${INKLING_PORT:-8000}"
exec docker run --gpus all --privileged --ipc=host -p "$PORT:8000" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -e VLLM_USE_V2_MODEL_RUNNER=1 -e FLASH_ATTENTION_CUTE_DSL_CACHE_ENABLED=1 \
  vllm/vllm-openai:nightly thinkingmachines/Inkling-Small-NVFP4 \
  --trust-remote-code --tokenizer-mode inkling \
  --kernel-config.enable_flashinfer_autotune=False \
  --tensor-parallel-size "$TP" \
  --enable-auto-tool-choice --tool-call-parser inkling --reasoning-parser inkling

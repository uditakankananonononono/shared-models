#!/usr/bin/env bash
# Serve real Inkling-Small (276B MoE, Unsloth dynamic GGUF) on your own machine with llama.cpp.
# Memory floor (RAM + VRAM, or unified memory), from https://unsloth.ai/docs/models/inkling :
#   2-bit ~89 GB | 3-bit ~128 GB | 4-bit 132-170 GB | 6/8-bit 256 GB
# Then: INSTINCT_INKLING_LOCAL_URL=http://127.0.0.1:8080/v1 INSTINCT_INKLING_LOCAL_MODEL=inkling-small
set -euo pipefail
QUANT="${INKLING_QUANT:-UD-Q2_K_XL}"          # UD-Q3_K_XL / UD-Q4_K_XL if you have the memory
PORT="${INKLING_PORT:-8080}"
DIR="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
CUDA="${GGML_CUDA:-ON}"                         # OFF for CPU-only or Apple Metal
if [ ! -x "$DIR/build/bin/llama-server" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$DIR" 2>/dev/null || true
  # Inkling support landed via llama.cpp PR 25731 (per the Unsloth guide); fetch it if main lacks it.
  (cd "$DIR" && git fetch origin pull/25731/head:inkling && git checkout inkling) || true
  cmake "$DIR" -B "$DIR/build" -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA="$CUDA"
  cmake --build "$DIR/build" --config Release -j --target llama-server
fi
export LLAMA_CACHE="${LLAMA_CACHE:-$HOME/.cache/unsloth/Inkling-Small-GGUF}"
exec "$DIR/build/bin/llama-server" -hf "unsloth/Inkling-Small-GGUF:$QUANT" \
  --alias inkling-small --host 127.0.0.1 --port "$PORT" --jinja \
  --temp 1.0 --top-p 1.0 --min-p 0.0

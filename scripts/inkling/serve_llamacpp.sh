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
# Pinned llama.cpp source for Inkling support: head of OPEN, mutable PR ggml-org/llama.cpp#25731
# ("Add TML Inkling architecture"). Head SHA observed 2026-10-10 via `git ls-remote` on
# refs/pull/25731/head and the GitHub PR API (head repo danielhanchen/llama.cpp, base master).
# The PR is not merged; if its head moves, this script FAILS until a human re-reviews and updates the pin.
PIN_PR=25731
PIN_SHA="68cd3f6cb06b1e425ea7221af03a93099aa6ab84"
die() { echo "serve_llamacpp.sh: FATAL: $*" >&2; exit 1; }
if [ ! -d "$DIR/.git" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$DIR" || die "git clone failed"
fi
cd "$DIR"
if [ "$(git rev-parse HEAD)" != "$PIN_SHA" ]; then
  git fetch origin "pull/$PIN_PR/head" || die "could not fetch pull/$PIN_PR/head; refusing to fall back to an Inkling-less checkout"
  git cat-file -e "$PIN_SHA^{commit}" 2>/dev/null \
    || die "pinned commit $PIN_SHA not found after fetch (PR head now $(git rev-parse FETCH_HEAD); it moved or was force-pushed). Re-review and update PIN_SHA."
  git checkout --detach "$PIN_SHA" || die "checkout of $PIN_SHA failed"
  rm -rf "$DIR/build"   # any existing build is of a different source; rebuild from the pin
fi
[ "$(git rev-parse HEAD)" = "$PIN_SHA" ] || die "HEAD is not $PIN_SHA after checkout"
cd - >/dev/null
if [ ! -x "$DIR/build/bin/llama-server" ]; then
  cmake "$DIR" -B "$DIR/build" -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA="$CUDA" || die "cmake configure failed"
  cmake --build "$DIR/build" --config Release -j --target llama-server || die "build failed"
fi
export LLAMA_CACHE="${LLAMA_CACHE:-$HOME/.cache/unsloth/Inkling-Small-GGUF}"
exec "$DIR/build/bin/llama-server" -hf "unsloth/Inkling-Small-GGUF:$QUANT" \
  --alias inkling-small --host 127.0.0.1 --port "$PORT" --jinja \
  --temp 1.0 --top-p 1.0 --min-p 0.0

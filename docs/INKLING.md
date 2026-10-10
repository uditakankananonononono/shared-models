# Running Inkling

Inkling-Small: Thinking Machines, Apache-2.0 open weights, 276B total / 12B active MoE,
text + image + audio in, tool calling (https://huggingface.co/thinkingmachines/Inkling-Small).

## Hosted: Hugging Face router (free tier, metered past it)
1. Free account at https://huggingface.co, then a token at https://huggingface.co/settings/tokens
   (fine-grained, permission "Make calls to Inference Providers").
2. `export HF_TOKEN=hf_...` - `InklingHFRouter` uses it with model `thinkingmachines/Inkling-Small`.
3. Check: `python -c "import os; from instinct_models.health import probe; print(probe('https://router.huggingface.co/v1','thinkingmachines/Inkling-Small',os.environ['HF_TOKEN']))"`

Free accounts get $0.10/month of credit (https://huggingface.co/docs/inference-providers/pricing);
more needs purchased credits. Inkling-Small is about $0.50 in / $1.20 out per million tokens on
the cheapest router provider. Hosted: never used for private tasks. `INSTINCT_ALLOW_HOSTED=0` turns it off.

## Her own PC: llama.cpp + Unsloth GGUF (real Inkling-Small, quantized)
`scripts/inkling/serve_llamacpp.sh` (quant via `INKLING_QUANT`, default `UD-Q2_K_XL`).
Memory, RAM + VRAM combined (https://unsloth.ai/docs/models/inkling):
2-bit ~89 GB | 3-bit ~128 GB | 4-bit 132-170 GB | 6/8-bit 256 GB.
The script builds llama.cpp from the pinned head commit `68cd3f6cb06b1e425ea7221af03a93099aa6ab84` of llama.cpp PR 25731 (open, unmerged, mutable head; observed 2026-10-10). If the commit cannot be fetched or checked out it exits with an error instead of falling back to main (which lacks Inkling). Update `PIN_SHA` only after reviewing the new head. UNRUN: this pin has not been built or executed.
Then `INSTINCT_INKLING_LOCAL_URL=http://127.0.0.1:8080/v1`, `INSTINCT_INKLING_LOCAL_MODEL=inkling-small`.

## GPU server: vLLM NVFP4
`scripts/inkling/serve_vllm.sh`, the official recipe (https://recipes.vllm.ai/thinkingmachines/Inkling-Small),
Docker with `--privileged --ipc=host` as the recipe specifies. Needs >=180 GB aggregate VRAM:
1x B300/GB300 (TP1) or 2x B200/GB200/H200 (TP2, `INKLING_TP`). BF16 needs ~600 GB.
Then `INSTINCT_INKLING_LOCAL_URL=http://<server>:8000/v1`,
`INSTINCT_INKLING_LOCAL_MODEL=thinkingmachines/Inkling-Small-NVFP4`.
Weights are public (not gated), so no HF token is needed to download.
The image is pinned to release `vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3`
(manifest-list digest read from the Docker registry and matching Docker Hub metadata, 2026-10-10), replacing the floating `:nightly` tag.
Override with `INKLING_VLLM_IMAGE` only deliberately. Not pulled or run. The recipe says "a nightly build with Inkling support";
v0.31.0 contains the Inkling model and parsers in source, but whether it runs this recipe end to end is UNVERIFIED.
Risks, unchanged by the pin: `--privileged` gives the container near-host access, and `--trust-remote-code` executes code from the model repo.
Use a dedicated GPU host. The model weights are not revision-pinned.

Warning: `http://<server>:8000/v1` to a non-loopback host is unencrypted. Prompts and answers, including private ones, travel in clear text, and the API-key guard does not cover calls made without a key. Put the server behind https (or an SSH tunnel to a loopback port) before sending anything private.

## Fine-tuning Inkling
Needs Thinking Machines' Tinker service (paid) or 180 GB+ of GPU memory. Not part of this
package; per-product training here is Needle LoRA.

## Current rebuild boundary (2026-10-01)

No real Inkling inference was run in this ~2 GiB CPU-only environment. The cited
Unsloth page returned HTTP 403 when rechecked; the ~89 GB 2-bit floor above is
inherited documentation, not a new measured result. Nothing was substituted.
For private calls to a remote self-hosted vLLM server, explicitly set
`INSTINCT_TRUST_REMOTE=1` only after trusting that endpoint, or use
`InklingLocal(url, model, trusted_remote=True)`. The default private policy is
loopback HTTP with an explicit port; hosted HF routing never handles private data.

### Pin verification record (integrator, 2026-10-10)
- vLLM image `vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd...e67c3` is a docker manifest LIST. Its body was fetched from the registry and its sha256 equals that digest. Entries: linux/amd64 `sha256:a4a4c0437bf7240089da5f08aa370c4aee17ae5290f7a3b468825ee26c4c3a6b`, linux/arm64 `sha256:3f7dd5b777d34d1724456ce71f87385dca288c3bb23029ab27dee358f5d2b971`. GitHub marks v0.31.0 as the latest release (published 2026-10-05T06:44:55Z). Older releases (0.29, 0.30) also contain Inkling code, so 0.31.0 is not established as the first supporting release.
- UNPROVEN: that this image serves Inkling end to end (the vLLM recipe names only a nightly build), the open vLLM Inkling bugs, and the llama.cpp PR code. Nothing here was pulled, built or run. Model weights and the GGUF download are not revision-pinned.

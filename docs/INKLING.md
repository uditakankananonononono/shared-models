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
The script builds llama.cpp and, per the Unsloth guide, checks out llama.cpp PR 25731 for Inkling support.
Then `INSTINCT_INKLING_LOCAL_URL=http://127.0.0.1:8080/v1`, `INSTINCT_INKLING_LOCAL_MODEL=inkling-small`.

## GPU server: vLLM NVFP4
`scripts/inkling/serve_vllm.sh`, the official recipe (https://recipes.vllm.ai/thinkingmachines/Inkling-Small),
Docker with `--privileged --ipc=host` as the recipe specifies. Needs >=180 GB aggregate VRAM:
1x B300/GB300 (TP1) or 2x B200/GB200/H200 (TP2, `INKLING_TP`). BF16 needs ~600 GB.
Then `INSTINCT_INKLING_LOCAL_URL=http://<server>:8000/v1`,
`INSTINCT_INKLING_LOCAL_MODEL=thinkingmachines/Inkling-Small-NVFP4`.
Weights are public (not gated), so no HF token is needed to download.

## Fine-tuning Inkling
Needs Thinking Machines' Tinker service (paid) or 180 GB+ of GPU memory. Not part of this
package; per-product training here is Needle LoRA.

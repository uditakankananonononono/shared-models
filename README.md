# shared-models (`instinct_models`)

This is the shared model layer for Atlas, Meemee and Sugarcode. It's built once here, and each product pins a commit of it. The training pipeline is shared, but each product keeps its own training data. The core runs on the Python standard library alone; `cactus-needle` is only needed to run Needle.

Install: `pip install "git+ssh://git@github.com/uditakankananonononono/shared-models.git@<commit>"`. You can also copy `instinct_models/` into your product at a pinned commit.

## Components

| Component | What it is (verified) | Class | Cost |
|---|---|---|---|
| Inkling | Thinking Machines' open model family | `InklingLocal` runs it on her own server (llama.cpp / vLLM / SGLang). `InklingHFRouter` uses the HF router with `HF_TOKEN` and is never used for private tasks. | Free locally. The HF router has a free tier and may bill past it. |
| Ornith | DeepReinforce's self-improving open models (https://ornith.ai, https://github.com/deepreinforce-ai/Ornith-1) | `OrnithOpenAICompat` runs an Ornith-1.5 GGUF through llama.cpp or Ollama (`/v1`) | Free, runs locally |
| Needle | Cactus Compute's on-device tool-calling model (https://github.com/cactus-compute/needle) | `NeedleLocal` uses the documented `Needle(...).complete()` call. It is also the model each product fine-tunes. | Free, runs locally |
| The AI Library | A public AI tools and prompts directory (https://www.theailibrary.co) | `AILibraryCatalog` (implements `CatalogSource`): read-only, follows robots.txt, caches results and rate-limits requests | Free |

Union Alpha was removed at the user's request. The package has no paid route.

## Router

`Router.from_config(load_config())` tries models in this order: Needle, then Ornith, then Inkling local, then the Inkling HF router (the HF router is left out when `INSTINCT_ALLOW_HOSTED=0`). `Router.run(Task(...))` returns the result along with every attempt it made.

## Training (per product)

1. The product writes a `DomainDataset` whose `rows()` returns `ExampleRow`s (query, tools, answers, confirmed, source_ref, private).
2. `build_needle_jsonl` writes the data in Needle's finetune JSONL format:
   - Only confirmed rows are kept.
   - Every argument must appear word-for-word in the query.
   - Off-topic rows (empty answers) are kept, and the build warns if there are too few.
   - It writes a hash manifest and marks private datasets as local-only.
3. `train_needle_lora` runs `needle finetune` and then `needle build` locally. It never uploads, refuses to run if the dataset changed after its manifest was written, and adds each run to `registry.jsonl`.
4. `ornith_rl_preflight` refuses to run without roughly 80 GB of GPU memory.
5. Fine-tuning Inkling needs Tinker (paid) or 180 GB+ of GPU memory. It is documented here as a future route and is not run.

## Config

Set these environment variables: `INSTINCT_PRODUCT` (atlas | meemee | sugarcode), `INSTINCT_INKLING_LOCAL_URL`, `INSTINCT_INKLING_LOCAL_MODEL`, `INSTINCT_HF_MODEL`, `INSTINCT_ORNITH_URL`, `INSTINCT_ORNITH_MODEL` (use the tag you pulled), `INSTINCT_NEEDLE_WEIGHTS`, `INSTINCT_ALLOW_HOSTED`. `HF_TOKEN` is read from the environment and never stored. You can also pass a JSON or YAML file through `load_config(path=...)`.

## Tests

`python3 -m unittest tests/test_instinct_models.py`

The tests use fakes, so they need no network connection, GPU or Needle install.


## Rules every product wires against

1. **Needle only handles tool calls.** It returns function calls or refuses, with no free text, and inference has a 256-token window. Send Needle only tasks that carry `tools`. Everything else goes straight to Ornith or Inkling. Past the base model's confidence threshold, an empty call list means "escalate", not "done".
2. **Every task declares whether it's private.** Set `Task(private=True)` for anything holding personal or contract data (Atlas contracts and receipts, Meemee personal data, Sugarcode customer code). Private tasks never reach a hosted route. If nothing local is available, the router stops and reports that, rather than sending the data out.
3. **Training data is confirmed-only, stays in its own product, and trains locally.** Products don't share datasets. Rows she rejected or never confirmed never reach training.
4. **The AI Library is read-only.** Browsing and suggesting are fine. Submitting or listing her products on that site is a public action and is out of scope for this package.
5. **Nothing here spends money.** There is no paid route. The HF router uses her own token and may bill past the free tier, so products should let her turn it off (`INSTINCT_ALLOW_HOSTED=0`).

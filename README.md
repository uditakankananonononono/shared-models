# shared-models (`instinct_models`)

This is the shared model layer for Atlas, Meemee and Sugarcode. It's built once here, and each product pins a commit of it. The training pipeline is shared, but each product keeps its own training data. The core runs on the Python standard library alone; `cactus-needle` is only needed to run Needle.

Install: `pip install "git+ssh://git@github.com/uditakankananonononono/shared-models.git@<commit>"`. You can also copy `instinct_models/` into your product at a pinned commit.

## Components

| Component | What it is (verified) | Class | Cost |
|---|---|---|---|
| Inkling | Thinking Machines' open model family | `InklingLocal` runs it on her own server (llama.cpp / vLLM / SGLang). `InklingHFRouter` uses the HF router with `HF_TOKEN` and is never used for private tasks. | Free locally. HF router: free tier, metered past it. |
| Ornith | DeepReinforce's self-improving open models (https://ornith.ai, https://github.com/deepreinforce-ai/Ornith-1) | `OrnithOpenAICompat` runs an Ornith-1.5 GGUF through llama.cpp or Ollama (`/v1`) | Free, runs locally |
| Needle | Cactus Compute's on-device tool-calling model (https://github.com/cactus-compute/needle) | `NeedleLocal` uses the documented `Needle(...).complete()` call. It is also the model each product fine-tunes. | Free, runs locally |
| The AI Library | A public AI tools and prompts directory (https://www.theailibrary.co) | `AILibraryCatalog` (implements `CatalogSource`): read-only, follows robots.txt, caches results and rate-limits requests | Free |
| Jev | TypeSafe AI's "System One" evaluation model (https://thejevai.com) | `JevEval`: send one state plus typed questions (choice / score / noul), get structured decisions with probabilities. It is an evaluation model, not a chat model, so it never joins the `Router` chain. | Paid credits, key-gated. Optional and OFF by default. |

Union Alpha was removed at the user's request. Everything runs free locally; the one hosted route (HF router) is free tier, metered past it.

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

Set these environment variables: `INSTINCT_PRODUCT` (atlas | meemee | sugarcode), `INSTINCT_INKLING_LOCAL_URL`, `INSTINCT_INKLING_LOCAL_MODEL`, `INSTINCT_HF_MODEL`, `INSTINCT_ORNITH_URL`, `INSTINCT_ORNITH_MODEL` (use the tag you pulled), `INSTINCT_NEEDLE_WEIGHTS`, `INSTINCT_ALLOW_HOSTED`, `INSTINCT_JEV_API_KEY` (optional; falls back to `JEV_API_KEY`). `HF_TOKEN` and the Jev key are read from the environment and never stored. You can also pass a JSON or YAML file through `load_config(path=...)`.

## Jev (opt-in, paid)

[Jev](https://thejevai.com) is TypeSafe AI's "System One" evaluation model: instead of generating text, it evaluates one piece of state against typed questions and returns decisions software can branch on. Question types (per https://thejevai.com/docs): `choice` (pick one of up to 255 options), `score` (rate on an ordered 2-10 level rubric) and `noul` (yes probability). Multiple questions are evaluated in parallel per request.

Facts checked on 2026-09-26:

- Endpoint `POST https://thejevai.com/v1/systemone`, `Authorization: Bearer <key>`, model `jev-latest`.
- Keys are created at https://thejevai.com/settings/apikeys.
- It is **paid**: https://thejevai.com/pricing lists a $10 one-time Starter tier (100,000 credits) and up; no free tier is offered.
- The same model is also listed on the Vercel AI Gateway as `typesafe-ai/jev` ($0.042 per 1M input tokens, https://vercel.com/ai-gateway/models/jev), which needs a Vercel AI Gateway key. This package talks to the direct Jev API; the gateway route is documented here for completeness only.
- Jev cannot generate text. It is not in the chat `Router` chain; call `JevEval.evaluate(...)` directly.

Setup (OFF by default - without a key nothing calls it and nothing can be billed):

```python
from instinct_models import JevEval
jev = JevEval()  # reads JEV_API_KEY, or INSTINCT_JEV_API_KEY via ProductConfig.jev_api_key
if jev.available():
    out = jev.evaluate(
        "Help! My payouts have been failing for 3 days.",
        {"department": {"type": "choice", "instructions": "Which team should handle this?",
                        "criteria": {"billing": "Payments, refunds", "technical": "Bugs, outages"}}})
    print(out["answers"], out["usage"])
```

Retries: 429 and 529 are retried with exponential backoff (per the Jev docs); 401 raises a clear "key missing or invalid" error. It is a hosted third-party route: never send private state to it.

## Tests

`python3 -m unittest tests/test_instinct_models.py`

The tests use fakes, so they need no network connection, GPU or Needle install.


## Rules every product wires against

1. **Needle only handles tool calls.** It returns function calls or refuses, with no free text, and inference has a 256-token window. Send Needle only tasks that carry `tools`. Everything else goes straight to Ornith or Inkling. Past the base model's confidence threshold, an empty call list means "escalate", not "done".
2. **Every task declares whether it's private.** Set `Task(private=True)` for anything holding personal or contract data (Atlas contracts and receipts, Meemee personal data, Sugarcode customer code). Private tasks never reach a hosted route. If nothing local is available, the router stops and reports that, rather than sending the data out.
3. **Training data is confirmed-only, stays in its own product, and trains locally.** Products don't share datasets. Rows she rejected or never confirmed never reach training.
4. **The AI Library is read-only.** Browsing and suggesting are fine. Submitting or listing her products on that site is a public action and is out of scope for this package.
5. **Nothing here spends money on its own.** Local routes are free. The HF router is free tier, metered past it (it bills her own token), so products should let her turn it off (`INSTINCT_ALLOW_HOSTED=0`).

## Needle privacy guard: sources

Checked against the installed cactus-needle 3.0.5 package on 2026-09-24:
- `needle/_telemetry.py` sends anonymous usage counts unless `NEEDLE_TELEMETRY=0` (or `DO_NOT_TRACK` / `CI` is set).
  The package README says the engine binary needs both `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1`. `NeedleLocal`
  sets both unless constructed with `telemetry=True`. Setting them changes the process environment.
- `needle/__init__.py` (`_annotate_ungrounded`) writes `response["validation"]["ungrounded"]`, the list of
  argument values not found in the query. `NeedleLocal` drops those calls so the router escalates.
If a future cactus-needle release renames either, re-check these files when bumping the version.

## Needle engine 404 workaround (cactus-needle 3.0.5)

cactus-needle 3.0.5 (latest on PyPI, 2026-09-24) pins the Needle 3 engine to 3.0.2
(`needle/agent/fetch.py`, `ENGINE_VERSIONS`), but Hugging Face `Cactus-Compute/needle3/python`
only publishes 3.0.0 and 3.0.1 wheels, so the first `Needle()` call fails with a 404.
`NeedleLocal` maps the unpublished 3.0.2 pin to 3.0.1 (override with `INSTINCT_NEEDLE_ENGINE_V3`).
If Needle 3 still fails to load, it falls back to Needle 2 (engine 2.0.4, published for all platforms);
tuned weights are never silently switched. Live-checked on linux-x86_64: both routes returned
`get_weather(city="Lagos")` for "what's the weather in Lagos right now?" (confidence 1.0 and 0.969).
Running the 3.0.1 engine under the 3.0.5 Python wrapper is a combination upstream did not ship.
Remove the mapping when upstream publishes 3.0.2.

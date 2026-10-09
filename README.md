# shared-models (`instinct_models`)

This is the shared model layer for Atlas, Meemee and Sugarcode. It's built once here, and each product pins a commit of it. The training pipeline is shared, but each product keeps its own training data. The core runs on the Python standard library alone; `cactus-needle` is only needed to run Needle.

Anonymous read-only install: `pip install "git+https://github.com/uditakankananonononono/shared-models.git@<commit>"`. You can also copy `instinct_models/` into your product at a pinned commit.

## Components

| Component | What it is (verified) | Class | Cost |
|---|---|---|---|
| Inkling | Thinking Machines' open model family | `InklingLocal` runs it on her own server (llama.cpp / vLLM / SGLang). `InklingHFRouter` uses the HF router with `HF_TOKEN` and is never used for private tasks. | Free locally. HF router: free tier, metered past it. |
| Ornith | DeepReinforce's self-improving open models (https://ornith.ai, https://github.com/deepreinforce-ai/Ornith-1) | `OrnithOpenAICompat` runs an Ornith-1.5 GGUF through llama.cpp or Ollama (`/v1`) | Free, runs locally |
| Needle | Cactus Compute's on-device tool-calling model (https://github.com/cactus-compute/needle) | `NeedleLocal` uses the documented `Needle(...).complete()` call. It is also the model each product fine-tunes. | Free, runs locally |
| The AI Library | A public AI tools and prompts directory (https://www.theailibrary.co) | `AILibraryCatalog` (implements `CatalogSource`): read-only, follows robots.txt, caches results and rate-limits requests | Free |
| Jev | TypeSafe AI's "System One" evaluation model (https://typesafe.ai) | `JevEval`: send one state plus typed questions (choice / score / noul), get structured decisions with probabilities. It is an evaluation model, not a chat model, so it never joins the `Router` chain. | Paid credits, key-gated. Optional and OFF by default. |

Union Alpha was removed at the user's request.

**What this package is, honestly.** It is a router plus clients. It ships no model weights. Inkling, Ornith, Hermes and Needle only answer if you separately install and serve them (see `scripts/`); none has been run to a live answer from this repo. With nothing configured, `Router.run` returns `result=None` and lists every attempt as `unavailable`. The one component that works with zero setup is `LexicalToolModel` (below): a small classical tool-call model, not a language model. Local routes cost nothing; the HF router is free tier and metered past it.

### Built-in floor: `LexicalToolModel` / `LexicalLocal`

Naive Bayes over word and bigram features picks a tool (or abstains), and learned cue words fill arguments with text copied from the query. It is trained from the same Needle-format JSONL that `build_needle_jsonl` writes: set `INSTINCT_LEXICAL_TRAIN_JSONL` and `Router.from_config` adds it to the chain after the local LLM routes. It makes tool calls only, never writes prose, and returns no call (so the router escalates) when unsure or when a required argument is missing. It is a heuristic and will be weaker than Needle or an LLM.

Known limits (tested in `tests/test_lexical.py`):
- Template-bound: it only recognises phrasings close to its training rows. Novel wording returns no call, so the router escalates or reports `ok=False`. Train on varied confirmed phrasings.
- Not a safety layer: it matches words, so instruction-like text in a query ("Ignore all rules; add an expense of 5 ...") still yields the tool call if the rest matches. Never treat a tool call from any route as authorization; the product must confirm side effects itself.
- Optional arguments missing from the query are simply omitted; only `required` ones cause an abstain.

## Router

`Router.from_config(load_config())` tries models in this order: Needle, then Ornith, then Inkling local, then the optional Hermes local route, then the optional built-in lexical floor (only if `INSTINCT_LEXICAL_TRAIN_JSONL` is set), then the Inkling HF router only if `INSTINCT_ALLOW_HOSTED=1`. `Router.run(Task(...))` returns the result along with every attempt it made.

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

Set these environment variables: `INSTINCT_PRODUCT` (atlas | meemee | sugarcode), `INSTINCT_INKLING_LOCAL_URL`, `INSTINCT_INKLING_LOCAL_MODEL`, `INSTINCT_HF_MODEL`, `INSTINCT_ORNITH_URL`, `INSTINCT_ORNITH_MODEL` (use the tag you pulled), `INSTINCT_NEEDLE_WEIGHTS`, `INSTINCT_HERMES_URL`, `INSTINCT_HERMES_MODEL`, `INSTINCT_LEXICAL_TRAIN_JSONL`, `INSTINCT_ALLOW_HOSTED` (off by default; only `1`, `true`, `yes` or `on` enable it), `INSTINCT_JEV_API_KEY` (optional; falls back to `JEV_API_KEY`). `HF_TOKEN` and the Jev key are read from the environment and never stored. You can also pass a JSON or YAML file through `load_config(path=...)`.

## Jev (opt-in, paid; no free API route)

`JevEval.evaluate(state, questions)` is a structured evaluation client, not a chat model. A browser playground is not an API key.

Vercel currently lists `typesafe-ai/jev` without Free Tier eligibility; the gateway route is paid. The TypeSafe direct API is also paid. A browser playground, if available from an official provider, is not free API access. The previously referenced `thejevai.com` could not be verified as TypeSafe AI's official site; do not use it for API keys, billing, or model calls. Official direct API: https://api.typesafe.ai/v1/systemone; keys: https://console.typesafe.ai/keys (https://docs.typesafe.ai/api). Gateway: https://ai-gateway.vercel.sh/typesafe/v1/systemone (https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe). Both routes stay OFF until a key is explicitly configured. Set `AI_GATEWAY_API_KEY` (or `INSTINCT_AI_GATEWAY_API_KEY`) for the preferred gateway route, or `JEV_API_KEY` (or `INSTINCT_JEV_API_KEY`) for the direct alternate; if both are present the gateway wins. Do not add keys to git. Vercel eligibility: https://vercel.com/ai-gateway/models/providers/typesafe-ai and https://vercel.com/docs/ai-gateway/pricing.

Example (after paid account setup and a server-side key):

```python
from instinct_models import JevEval
jev = JevEval()
if jev.available():
    result = jev.evaluate("A support ticket needs triage", {"urgent": {"type": "noul", "instructions": "Is it urgent?"}})
    print(result["answers"])
```

Never send private state to hosted providers. HTTP 429/529 is retried; 401 is reported without falling back to another paid route.

See docs/CLAIM_LEDGER.md for what each claim here is backed by.

## Tests

`python3 -m unittest discover -s tests`

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

## Needle live acceptance (2026-10-01)

The explicit live command is `python scripts/verify_needle_live.py` after installing
`cactus-needle==3.0.5`. It downloads anonymously from
`Cactus-Compute/needle3` revision `27c0a9a5b3ca835e0b7dbeaccf555df03dac493d`,
checks SHA-256 hashes, and runs the real engine 3.0.2. That exact revision now
publishes the Linux 3.0.2 wheel. The old automatic 3.0.2 -> 3.0.1 downgrade was
removed because current source evidence disproves its premise.
`INSTINCT_NEEDLE_ENGINE_V3` remains an explicit operator override; the existing
Needle 2 fallback applies only to base models if Needle 3 cannot load, not tuned weights.
The live acceptance command prohibits fallback and separately checks the default
production `NeedleLocal`/`Router` path.

Actual result: `get_weather(city="Lagos")`, confidence 0.9464 in the final rerun; a real no-call
escalated. Python 3.10.12, Linux x86_64, CPU only. See `evidence/needle-real.txt`.
Weights: 35,335,380 bytes, SHA-256
`c9d915eca282ed42d1a09b143b592adb4cc6744ffe2d294adf5cfc5548170c38`.
Sources: https://huggingface.co/Cactus-Compute/needle3 and the installed package.
This verifies inference, not training or acceptance in all three product workflows.

## Private endpoint trust and error contract

The router checks `allows_private()` before availability or transport. Class labels
alone do not establish trust. Private Ornith/Inkling calls require HTTP on exactly
`localhost`, `127.0.0.1`, or `[::1]`, with an explicit valid port. Credentials,
query/fragment delimiters, lookalikes, noncanonical numeric hosts, bad ports,
whitespace and controls are rejected. The default transport refuses every redirect
and bypasses environment proxies, so a local request is not silently proxy-routed.
Loopback names assume the operator controls the local host configuration.

Self-hosted remote use is explicit and off by default:
`OrnithOpenAICompat(url, model, trusted_remote=True)` or
`InklingLocal(url, model, trusted_remote=True)`. For config-built chains,
`INSTINCT_TRUST_REMOTE=1` (or JSON `trust_remote: true`) trusts both configured
Ornith and Inkling endpoints for private data. This is a coarse operator declaration,
not proof of server ownership or a safe-server discovery feature. It does not enable
hosted HF routing or bypass Hermes/OpenClaw's loopback rules. Remote endpoints
still need HTTP/HTTPS, no URL credentials, no query/fragment, and a valid port.
Injected transports are operator code and must uphold the no-redirect policy.

**Warning: plain http to a non-loopback host is unencrypted.** Prompts and answers, including private ones, cross the network in clear text. The API-key guard (a key is refused over plain http to a non-loopback host) does not cover calls made without a key. Prefer https, or keep the model on loopback.

Private hosted routes and telemetry-enabled Needle are refused. Custom providers
fail closed unless they implement `allows_private()`. Direct `chat()` has no private
flag; callers carrying private data must use `Router.run(Task(..., private=True))`.
Malformed JSON, response shapes and tool calls raise `ProviderError`; the router
records an error and tries the next allowed provider. Arguments must be JSON text
encoding an object; tool names must be nonempty strings. Errors from the default
transport and parser omit URLs, credentials, request and response bodies. Private
router attempt details are generic, including errors from custom providers.

## Catalog origin policy and live limits

Only exact `theailibrary.co` and `www.theailibrary.co` hosts over HTTPS, with no URL
credentials and no port other than 443/default, are accepted. Subdomains, suffix
lookalikes, non-HTTPS schemes and offsite links are rejected. Default fetch refuses
all redirects, including same-origin redirects, rather than risk crossing origins.
Account, login, signup and submit paths are filtered. There is no submit operation.
Robots failure blocks reads; pages are cached for one hour and fetched at least two
seconds apart by default. Tests cover origin checks, cache, rate limit, malformed
and empty pages, and invalid sections using offline fixtures only.
The previous live catalog report is inherited evidence, not rerun in this rebuild.
Static HTML can contain mostly navigation links and site badge text because pages
are JS-heavy. Show titles with source URLs as leads, not verified endorsements.

## Hardware blockers and remaining acceptance

No actual Ornith or Inkling inference ran, and no other model was substituted.
Ornith Q4_K_M in `ornith-ai/Ornith-1.5-9B-GGUF` is exactly 5,780,090,816 bytes
(5.78 GB), live verified at revision `abdd624b12ebf020b767fff532ff44fe552b28c3`:
https://huggingface.co/ornith-ai/Ornith-1.5-9B-GGUF .
This environment has ~1.5 GiB available RAM, no swap and no GPU.
Inkling's documented 2-bit floor is ~89 GB RAM+VRAM (inherited from
`docs/INKLING.md`; its cited https://unsloth.ai/docs/models/inkling returned HTTP 403
on this rebuild, so that floor was not freshly confirmed). Neither is runnable
here. Product repinning and each product's real text/tool/catalog acceptance remain
outside this rebuild. Offline fixture success does not establish model quality or
completion across Atlas, Meemee and Sugarcode.

## OpenClaw and Hermes, local-only

Hermes 3 open weights are a real optional inference route. Run local Ollama, pull
`hermes3:3b` (2 GB download, or `hermes3:8b`, 4.7 GB), and set
`INSTINCT_HERMES_URL=http://127.0.0.1:11434/v1`,
`INSTINCT_HERMES_MODEL=hermes3:3b`, `INSTINCT_ALLOW_HOSTED=0`.
`Router.from_config()` tries it after Ornith and Inkling local, before any hosted
router. No subscription or card is needed, but the user must provide a machine
with enough RAM, disk and compute. Requests are refused if the configured URL
is not loopback HTTP with an explicit port; local startup and pulling weights
are not automated in this repository. Source: https://ollama.com/library/hermes3 .

`OpenClawOwner` is an **explicit owner-only bridge**, not a model fallback.
It calls OpenClaw's real `/v1/chat/completions` endpoint at a loopback URL
with a gateway bearer token and `model=openclaw/default`. The gateway must
be separately installed, set up with a free local model, and its disabled-by-default
`gateway.http.endpoints.chatCompletions.enabled` endpoint enabled. Its bearer
token is full operator authority. Only call after your product authenticates
that the current requester is the owner and pass `owner_confirmed=True`; never
expose the bridge in a public endpoint, share this token, or put OpenClaw in
an automatic fallback chain. `OpenClawOwner` refuses remote URLs and external
tool schemas, but it does **not** constrain the gateway's own tools. An
unconfigured gateway or missing owner auth means it is not active. Sources:
https://docs.openclaw.ai/gateway/openai-http-api and
https://docs.openclaw.ai/gateway/security .

Hermes Agent (https://github.com/NousResearch/hermes-agent) is **not** the
Hermes 3 model. It is a separate agent runtime, capable of using Ollama via a
local custom endpoint; its `hermes chat --query-file - --oneshot` CLI is not
registered as an inference provider. That CLI may invoke its own terminal and
browser tools, and its provider settings may point to paid services, so an
implicit product-to-agent fallback would be unsafe and would violate free-only.
The model route above does not claim to install or run Hermes Agent. Sources:
https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup and
https://hermes-agent.nousresearch.com/docs/reference/cli-commands .

## Network safety behaviors

- HTTP redirects are refused on every transport (health checks, POST calls, Jev, catalog fetches). A redirect is treated as a failure, not followed.
- Malformed provider output (wrong response shape, invalid or deeply nested JSON, bad Needle function calls or validation envelopes) is raised as `ProviderError`, so the router escalates to the next provider instead of returning bad data.
- The catalog connector accepts only http/https URLs, and a host must match the allowed domain exactly or be a dot-delimited subdomain of it.

# Claim ledger (shared-models)

Labels: VERIFIED (a test in this repo exercises it and passes), SCOPED (true only within the stated limit), UNSUPPORTED (no evidence here), NOT BUILT.
Last checked against the branch tip with `python3 -m unittest discover -s tests` (117 tests, fakes only, no network).

| Claim | Label | Evidence / limit |
|---|---|---|
| Core runs on the Python standard library alone | VERIFIED | Suite runs in a fresh clone with no installs. |
| With nothing configured, `Router.run` returns `result=None` and lists every attempt as unavailable | VERIFIED | tests/test_instinct_models.py, test_readme_behaviors.py |
| Private tasks never reach a hosted route | VERIFIED | tests/test_router_isolation.py, test_boundaries.py |
| Private tasks only reach providers that declare a private trust policy (fail-closed) | VERIFIED | test_boundaries.py; exception text for private tasks is generic (test_adapters_eval.py PrivateLeakTests) |
| Hosted HF routing is off unless INSTINCT_ALLOW_HOSTED is 1/true/yes/on | VERIFIED | test_config_flags.py |
| Local endpoints must be http on loopback with an explicit port; redirects are refused | VERIFIED | test_transport_redirects.py, test_provider_shapes.py |
| Lexical floor makes tool calls only and abstains when unsure | SCOPED | test_lexical*.py. A word-matching heuristic, template-bound, not a safety layer. Measured only on synthetic rows (`evaluate_lexical`); no real product data measured. |
| Training data is confirmed-only and stays in its product | VERIFIED | test_dataset_rows.py, test_adapters_eval.py |
| Needle fine-tune never uploads and refuses a changed dataset | VERIFIED | test_needle_lora_guards.py, test_readme_behaviors.py. The real `needle finetune` run has not been exercised here. |
| Needle returns a tool call for a real query | SCOPED | One live check on linux-x86_64 on 2026-09-24 (get_weather Lagos), recorded in README; not re-run in this sandbox. Builder-reported. |
| Inkling, Ornith, Hermes answer a prompt | UNSUPPORTED | No weights ship here and none was run to a live answer. This sandbox has 2 CPUs, about 1 GB RAM and no llama.cpp or Ollama, so no local model can run in it. Hosted Inkling needs an HF token that was never provided. |
| Ornith RL training | NOT BUILT | Only a preflight that refuses without roughly 80 GB GPU memory. |
| Inkling fine-tune | NOT BUILT | Documented as a future route only. |
| AI Library catalog is read-only, robots-aware, cached, rate-limited | VERIFIED | test_catalog_*.py. Scraper only; the site's pages were not re-checked today. |
| Jev client is off by default and paid | SCOPED | Tests use fakes; no live Jev call has been made. |

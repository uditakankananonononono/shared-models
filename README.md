
## Rules every product wires against

1. **Needle only handles tool calls.** It returns function calls or refuses, with no free text, and inference has a 256-token window. Send Needle only tasks that carry `tools`. Everything else goes straight to Ornith or Inkling. Past the base model's confidence threshold, an empty call list means "escalate", not "done".
2. **Every task declares whether it's private.** Set `Task(private=True)` for anything holding personal or contract data (Atlas contracts and receipts, Meemee personal data, Sugarcode customer code). Private tasks never reach a hosted route. If nothing local is available, the router stops and reports that, rather than sending the data out.
3. **Training data is confirmed-only, stays in its own product, and trains locally.** Products don't share datasets. Rows she rejected or never confirmed never reach training.
4. **The AI Library is read-only.** Browsing and suggesting are fine. Submitting or listing her products on that site is a public action and is out of scope for this package.
5. **Nothing here spends money.** There is no paid route. The HF router uses her own token and may bill past the free tier, so products should let her turn it off (`INSTINCT_ALLOW_HOSTED=0`).

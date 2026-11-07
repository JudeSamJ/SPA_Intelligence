# Copilot Studio: internal staff copilot (demo)

Status: **definition only, not created in a tenant.** Uses `../power-platform/spa-intelligence.apikey.swagger.json` through a connector
connection holding the **staff** key (demo) or an Entra user connection (real deployment).

Actions to add: `ListContracts`, `GetContract`, `ListObligations`, `ListAlerts`, `ListReviewQueue`, `GetStatuteGap`. Do **not** add
`ReviewField`, `ExtractContract` or `PushToErp` to a chat agent: they change data or spend LLM calls; keep those in flows that ask a person first.

Instructions:

```
You help the contracts team. Answer only from the actions' results; never from your own knowledge; never do arithmetic yourself.
Use ListObligations for "what is due / overdue", ListAlerts for open alerts, ListReviewQueue for fields needing review, GetStatuteGap for contract-versus-statute questions.
When a result has "can_compute": false, say so and give the reason. Always mention that statutory figures use legal logic no lawyer has reviewed.
Quote the page numbers the actions return. If an action fails, say you cannot answer right now.
End with: "Decision support, not legal advice."
```

Demo questions: What is overdue as of 2025-03-16? · What needs review? · Show the gap for the India sample at 180 days · Which contract has a payment plan that does not total 100%?

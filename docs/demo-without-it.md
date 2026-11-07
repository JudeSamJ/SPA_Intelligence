# Demo with Power Automate Premium + Copilot Studio, without IT

You have: Power Automate Premium and Copilot Studio. You do **not** have: Entra app registrations, Azure hosting, D365 admin.
So this guide uses only things you can do yourself: API keys instead of Entra, your own laptop as the host, and flows/agents you
create in your own maker environment.

**Status: everything on the API side (key auth, scoping, webhooks, connector files, launcher) is built and tested. The Power
Automate and Copilot Studio steps below were written from the product's documented behaviour and have not been run in a real
tenant. Allow time for small adjustments.**

## What you can and cannot show

| Works without IT | Needs IT (skipped in this demo) |
|---|---|
| Upload a contract, extraction, evidence highlights, gap, simulation, playbook, cross-check (the web app, on your laptop) | Entra sign-in and real per-person roles |
| Contract ready / overdue-payment / review-needed events posted to **Teams (to yourself or a chat)**, **email**, **an Excel table in your OneDrive** by Power Automate | A shared channel in a team you do not own |
| A Power Automate flow that **calls the API** (statute gap, alerts, review decision) through a custom connector | Writing into D365 F&O (use the CSV/JSON dry-run export instead) |
| A **Copilot Studio buyer agent** that answers only from the demo contract through the API, with citations and refusals | Production hosting, real buyers, WhatsApp |
| An **internal Copilot** for staff questions (obligations, alerts, review queue, statute gap) | Power BI (deliberately not part of this app) |

Possible blockers you cannot fix yourself: a data-loss-prevention policy in your environment that blocks custom connectors or the
HTTP action, or a network policy that blocks tunnels. If a step fails with a policy message, tell your IT team *only* that one
sentence. The outbound-only parts (flows triggered by our webhook, Excel/Teams/email) usually work even then.

## Use demo data only

Everything that leaves your laptop through the tunnel is reachable by anyone who has the URL **and** an API key. Use the synthetic
samples (`samples/`), not real contracts or real buyer data. Your company's Azure OpenAI key stays on your laptop; the server's
`LLM_MAX_CALLS` cap still protects it. Stop the tunnel when you finish and delete `data/demo_keys.json` to rotate the keys.

## 1. Start the two servers

```bash
npm run build                   # once
scripts/demo_up.sh
```

- `http://127.0.0.1:8000`: your private UI and API, no sign-in, bound to your laptop only. **Never tunnel this port.**
- `http://127.0.0.1:8001`: API only, `AUTH_MODE=apikey`. This is what Power Platform will call.
- Keys are created once in `data/demo_keys.json` (gitignored): a **staff** key (reviewer role) and a **buyer** key bound to sample A.

Open the UI and extract sample A once (1 LLM call) so the buyer agent has something to answer from.

## 2. Give Power Platform a public HTTPS address for port 8001

Pick one that your laptop is allowed to run (try them in this order):

1. **Dev Tunnels** (Microsoft): `devtunnel user login` then `devtunnel host -p 8001 --allow-anonymous`.
   "Anonymous" only means no Microsoft login at the tunnel; our API still demands the `X-API-Key` header.
2. **Cloudflare quick tunnel**: `cloudflared tunnel --url http://127.0.0.1:8001`.
3. **ngrok**: `ngrok http 8001`.

Copy the `https://…` host (without the path). Test it: `curl https://<host>/api/health` should answer, and
`curl https://<host>/api/contracts` should answer **401**.
Tunnel URLs change every time you restart; update the connector host when they do.

## 3. Import the connector (Power Automate > Data > Custom connectors)

1. New custom connector > **Import an OpenAPI file** > `integrations/power-platform/spa-intelligence.apikey.swagger.json`.
2. General: host = your tunnel host. Security: **API Key**, parameter label `API Key`, parameter name `X-API-Key`, location **Header**.
3. Create, then on the Test tab create a connection with the **staff** key and run `ListContracts` (you should see the five samples).
4. Repeat for Copilot Studio with `integrations/copilot-studio/buyer-chat.apikey.swagger.json` and the **buyer** key (a second connector,
   because it must carry the buyer key, not the staff key).

## 4. Turn on outbound events (no tunnel needed for this part)

Create a flow: **When an HTTP request is received** (Who can trigger: "Any user in my tenant"; keep the URL private). Put it in `.env`:

```
ALERT_WEBHOOK_URL=<the flow's HTTP POST URL>
ALERT_WEBHOOK_SECRET=<any long random text>
```

Restart `demo_up.sh`. The API now posts `contract_ready`, `alert` and `review_needed` events (no contract text). Build the actions you
want behind the trigger; ready recipes are in `integrations/power-automate/README.md`:

- **Contract ready → Excel table** row in `SPA Demo.xlsx` in your OneDrive (Excel Online (Business) > Add a row into a table).
- **Overdue / due-soon alert → Teams message to yourself** ("Post message in a chat or channel" > Flow bot > Chat with Flow bot) or an email.
- **Review needed → adaptive card** to yourself; your reply calls `ReviewField` through the connector (the staff key's name appears in the audit trail).
- **Statute gap on demand**: a manual flow that calls `GetStatuteGap` and posts the numbers with the "unreviewed legal logic" note.

## 5. Copilot Studio agents

**Buyer agent** (customer-facing demo): follow `integrations/copilot-studio/agent-instructions.md`, but in step 2 choose
**No authentication** for the demo and in step 3 add the buyer connector with the buyer key (a fixed connection). The agent can then only ever
reach sample A, because the key is bound to that one contract server-side. In the real deployment you would switch to Entra sign-in so each buyer
reaches their own contract. Run the twelve conversations in `integrations/copilot-studio/test-conversations.md`.

**Staff copilot** (internal demo): `integrations/copilot-studio/staff-agent.md`: actions `ListObligations`, `ListAlerts`, `ListReviewQueue`,
`GetStatuteGap`, `GetContract` through the staff connector. Ask "what is overdue?", "what needs review?", "show the gap for sample D at 180 days".

## 6. Shut down

Stop the tunnel and `scripts/demo_up.sh` (Ctrl+C). Delete `data/demo_keys.json` to invalidate the keys.

## What this demo does not prove

- Real per-person identity: the staff key is shared, so the review log shows "Demo reviewer", not a named person.
- The India statute figures use illustrative rates unless you added dated rows; Dubai has no formula. Say so when showing the Gap tab.
- Extraction accuracy on real contracts: the golden set has only synthetic documents.

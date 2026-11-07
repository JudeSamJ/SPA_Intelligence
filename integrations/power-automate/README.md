# Power Automate recipes

All flows call the API through the **custom connector** built from `../power-platform/spa-intelligence.swagger.json`
(see `docs/entra-setup.md` for the Entra registrations and `docs/power-platform.md` for importing it). Nothing here replaces the
API's calculations: flows only move data and ask people to decide. Card templates are in this folder; `@{...}` marks dynamic content you pick in the flow designer.

**Status: written to match the API and covered by structure tests, but not run in a real Power Automate tenant** (none was available).
Expect small designer adjustments.

## Turning on outbound events

Create a flow that starts with **When an HTTP request is received** (restrict "Who can trigger" to your tenant), copy its URL, then on the server:

```
ALERT_WEBHOOK_URL=https://prod-xx.westeurope.logic.azure.com/workflows/...
ALERT_WEBHOOK_SECRET=<long random string>        # optional, see below
```

The API then POSTs two kinds of JSON (no contract text, only ids, dates, severity, page numbers):

```json
{"type":"alert","alert":{"id","contract_id","contract_name","event_type","severity","message","due_date","days_until","label","page"}}
{"type":"review_needed","review":{"contract_id","contract_name","field","status","confidence","page"}}
```

Every request carries `X-SPA-Timestamp` and `X-SPA-Signature: sha256=HMAC_SHA256(secret, timestamp + "." + body)`. Power Automate expressions
cannot compute an HMAC, so for a flow rely on the trigger URL's own signature (keep it secret and rotate it if leaked). If you
need to verify the HMAC, put an Azure Function (or Logic App with a function) in front; `app/notifiers.verify` shows the exact check.
Failures to deliver are logged and retried on the next recompute for review items; alerts are sent once when first created.

## Flow 1: new contract arrives

Trigger: *When a file is created* (SharePoint library "Contracts") or *When a new email arrives (V3)* with a PDF attachment.
1. **Condition:** file name ends with `.pdf`.
2. HTTP/connector call **upload**: the API has `POST /contracts/upload` (multipart). It starts extraction (1 LLM call).
   *Custom connectors cannot send multipart well; use the built-in **HTTP** action with the Entra token (HTTP with Microsoft Entra ID, base resource `api://<API client id>`).*
3. **Do until** `GetExtractionStatus` is `extracted` (delay 10 s, limit 30).
4. `GetContract` → create or update the buyer/agreement record in D365 F&O (Finance and Operations connector, *Create a new record*), using the fields you confirmed in `erp/d365_mapping.yaml`.
5. Post to Teams: "New contract ready for review: <name>".

## Flow 2: review in Teams (trigger = `review_needed` webhook)

1. Trigger: HTTP request (above). Parse JSON with the shapes shown.
2. **Post adaptive card and wait for a response** to channel *Contract review*, card = `adaptive-card-review.json`.
3. **Switch** on `action`:
   - `accept` / `reject` → `ReviewField` with `{"action": <action>, "note": <note>}`.
   - `correct` → `ReviewField` with `{"action":"correct","value": <value>, "note": <note>}`.
4. The API records the decision with the **signed-in user's** name (the connector must use *Sign in as the user*, not a shared connection, or the audit trail shows the service account).
5. Reply in the thread: "Recorded by <name>".
Reviewed values become part of the golden set export, which is how you get real evaluation data.

## Flow 3: obligation reminders (trigger = `alert` webhook)

1. Trigger: HTTP request, filter `type == "alert"`.
2. **Condition** severity: `high` → Teams post to the collections channel with `adaptive-card-alert.json`; `medium` → email to the account manager.
3. On "Acknowledge": `AcknowledgeAlert` with the alert id.
4. Optional second action: send a polite WhatsApp/SMS to the buyer through your approved messaging provider. The API never contacts buyers itself; a person should approve any buyer-facing message.
Also add a **Recurrence** flow (daily 07:00) calling `ListAlerts` as a safety net in case a webhook delivery failed.

## Flow 4: approval before ERP push

Trigger: manual ("For a selected row") or after Flow 1.
1. `GetStatuteGap` for the delay scenario you care about.
2. **Condition** `findings` contains severity `high` → **Start and wait for an approval**, or the card `adaptive-card-approval.json` to legal.
3. If approved → `PreviewErpExport`; if `valid` is true → `PushToErp` with `confirm: true`.
4. If the server has push disabled, or the mapping still has placeholders, the call returns 409 with the reason: show it in Teams.
The approval card states that the statutory figure is unreviewed legal logic.

## Limits worth knowing

- Flow runs and premium connectors (custom connector, HTTP) need the right Power Platform licence.
- The API caps LLM calls per process (`LLM_MAX_CALLS`); do not trigger extraction on every file event in a busy library: add a condition or an approval.
- Flows run as the connection owner; use per-user connections where identity matters (review, push).

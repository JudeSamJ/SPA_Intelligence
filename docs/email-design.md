# Designed emails (Power Automate)

The app now builds the **whole email** (subject, HTML and a hosted image card) and sends it to your flow inside the webhook payload, so the flow
needs **one** "Send an email (V2)" action instead of a Switch with hand-typed text. Every email has: a hero image card, the same facts as
selectable text (for clients that block images), a button that opens the right page, then

> With regards,
> **<your name>**
> Unlimited Innovations India Pvt. Ltd
> *(the Unlimited Innovations logo)*

and the "Decision support, not legal advice." footer. Previews you can open without sending anything: `docs/email-previews/*.html`.

## 1. Settings (Render > Environment)

| Variable | Value |
|---|---|
| `PUBLIC_BASE_URL` | `https://spa-intelligence-bkf2.onrender.com` (already set for sign-in; it hosts the logo and card images and builds the links) |
| `ALERT_WEBHOOK_SECRET` | already set; it **signs** the image-card links. Changing it later breaks the images in emails already sent |
| `EMAIL_SENDER_NAME` | the name after "With regards," e.g. `Jude Sam J` (default: "The SPA Intelligence team") |
| `EMAIL_SENDER_TITLE` | line under the name (default: "Unlimited Innovations India Pvt. Ltd") |

Save and redeploy.

## 2. Change the flow (once)

1. Open the trigger **When an HTTP request is received** and click "Use sample payload to generate schema". Paste:
```json
{"type":"contract_ready","test":false,"email":{"subject":"","html":"","text":"","preheader":"","image_url":""},"alert":{"id":"","contract_id":"","contract_name":"","event_type":"","severity":"","message":"","due_date":"","days_until":0,"label":"","page":0},"review":{"contract_id":"","contract_name":"","field":"","status":"","confidence":0,"page":0},"contract":{"contract_id":"","contract_name":"","unit_id":"","buyer":"","currency":"","price":0,"handover_date":"","jurisdiction":"","milestones":0,"payment_plan_percent_sum":0,"warnings":0,"needs_review":0,"model":""}}
```
2. Keep the **Response** (202) action right after the trigger.
3. Delete the **Switch** (and everything inside it).
4. Add **Condition**: `email html` (dynamic content) **is not equal to** an empty value (leave the right side blank).
5. In the **Yes** branch add **Send an email (V2)**:
   - **To:** your address
   - **Subject:** dynamic content `email subject`
   - **Body:** dynamic content `email html`
6. Save.

If the Body shows the raw tags in the received email, open the Body field's code view (`</>`) and put the `email html` dynamic content there.

## 3. Test it (no extraction, no waiting)

```bash
curl -X POST -H "X-API-Key: <staff key>" -H "Content-Type: application/json" -d "{\"kind\":\"contract_ready\"}" https://spa-intelligence-bkf2.onrender.com/api/webhook/test
```
`kind` can be `contract_ready`, `alert` or `review_needed`. It sends one email (subject starts with `[TEST]`) using real data if the app has any, otherwise clearly labelled sample data.
The reply says `"sent": true` when your flow accepted it.

## How it works and what to know

- The image is drawn on demand from a **small signed link** (HMAC, 30 days). It contains headline facts only (unit, price, dates, plan percentages), never contract text, and nobody can make the server draw anything without the secret. A bad or expired link returns 404.
- Many mail apps **block remote images until you click "download pictures"**. That is why every fact is also in the email as text, and the images carry descriptive alt text.
- Outlook desktop ignores rounded corners and may show the hero slightly squarer; the content and signature still render (the layout uses tables and inline styles, with a fixed-width fallback for Outlook).
- Sending to yourself shows two blocks in Outlook's conversation view (the sent copy and the received copy). Not a duplicate.
- The logo file is `assets/brand/email-logo.png`; swap it to change the sign-off logo. Fonts (Inter, Fraunces; SIL OFL) are bundled for the image cards.
- Regenerate the previews with `python scripts/preview_email.py --name "Your Name"`.
- **Not tested in real mail clients** (Outlook desktop, Gmail, phone apps) from this environment: the HTML was checked in a browser at desktop and phone widths and the fuzz tests cover odd data, but expect small differences in Outlook.

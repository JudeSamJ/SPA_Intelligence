# Supabase setup (database for SPA Intelligence)

Links: dashboard https://supabase.com/dashboard · connecting https://supabase.com/docs/guides/database/connecting-to-postgres ·
Row Level Security https://supabase.com/docs/guides/database/postgres/row-level-security · Render https://dashboard.render.com

## What the database holds

| Table | Purpose |
|---|---|
| `app_files` | Durable copy of every file the app keeps: uploaded PDFs, extractions, review decisions, alerts, document sets. Restored automatically when the server starts with an empty disk. |
| `contracts` | One readable row per contract (name, pages, status, open review items). Use the Supabase Table Editor to see the portfolio. |
| `buyer_assignments` | Which buyer (email or phone) may ask about which contract. |
| `audit_log` | Every buyer question and what the assistant did (no contract text). |

All four tables have Row Level Security **on with no policies**, so Supabase's public REST API cannot read or write them.
Only the app, connecting with `DATABASE_URL`, can. Never put `DATABASE_URL` in the browser or in a public repository.

## One-time setup

1. Create a project at https://supabase.com/dashboard. Save the database password somewhere safe.
2. Click **Connect** at the top of the project. Copy the **Session pooler** connection string
   (it looks like `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`).
   - Use the **Session pooler** string for Render. The "Direct connection" host (`db.<ref>.supabase.co`) is IPv6-only on most
     plans, and Render's free tier cannot reach it.
   - Replace `[YOUR-PASSWORD]` with your database password. If it has special characters, URL-encode them (`@` → `%40`).
3. Check it from your own machine (no data is touched except one throwaway row):

   ```bash
   DATABASE_URL='postgresql://...' python scripts/check_supabase.py
   ```

   You should see six PASS lines. It also creates the tables. You can instead paste `supabase/schema.sql` into the
   Supabase **SQL Editor**; the app creates the tables on start-up anyway (`DB_AUTO_MIGRATE=1`, the default).
4. In Render, open the service → **Environment** and add `DATABASE_URL` with that string. Save; Render redeploys.
5. Open `https://<your-app>/api/health`. It must show `"database": {"enabled": true, "ok": true, ...}`.
6. Upload a contract, wait ten seconds, and look in Supabase → **Table Editor** → `contracts` and `app_files`.
7. Restart the Render service. The contract must still be there. That is the proof the data survives.

## How it behaves

- **Restart:** on start-up the app downloads any file missing on disk, so extractions, reviews and PDFs come back.
- **Saving:** changes are copied to the database every 10 seconds (`DB_SYNC_SECONDS`), and immediately after an upload,
  an extraction or a review decision.
- **If the database is down:** the app keeps working on local files and `/api/health` shows `"ok": false`. Nothing crashes.
- **Cost of a restart:** the extraction cache comes back too, so a redeploy does not repeat paid model calls.

## Linking buyers to contracts (no more per-buyer keys)

1. Create **one** channel key per channel (Teams agent, WhatsApp adapter) in `API_KEYS` with the role `Spa.Channel`:
   `{"<24+ character key>": {"name": "Teams agent", "roles": ["Spa.Channel"]}}`.
2. A reviewer opens **Buyers** in the app and links an email or phone number to a contract. That is all.
3. The channel calls `POST /api/buyer/chat` with its key and the header `X-Buyer-Identity: <buyer email or phone>`.
   The contract is looked up in the table. An unknown buyer gets a refusal. Removing the row cuts access at once.

## Direct email (no Power Automate needed)

Set these on Render to send the designed alert emails straight from the app:

| Variable | Example |
|---|---|
| `SMTP_HOST` | `smtp.office365.com` |
| `SMTP_PORT` | `587` (use `465` with `SMTP_SECURITY=ssl`) |
| `SMTP_USER` / `SMTP_PASSWORD` | the mailbox login or an app password |
| `SMTP_FROM` | sender address (defaults to `SMTP_USER`) |
| `ALERT_EMAIL_TO` | `ops@company.com, legal@company.com` |
| `PUBLIC_BASE_URL`, `ALERT_WEBHOOK_SECRET` | already used for the summary image in the email |

Then use **POST /api/webhook/test** (reviewer) to send a test email. The Power Automate webhook still works if you set
`ALERT_WEBHOOK_URL`; both can be on at once.

## Limits and good practice

- PDFs are stored inside Postgres (`app_files`), up to 30 MB each. The free Supabase database is small (about 500 MB), so
  watch its size for large portfolios; moving PDFs to Supabase Storage is a contained change if needed.
- Free projects can pause when inactive. Check your plan before a client demo.
- Rotate the database password in Supabase (**Project Settings → Database**) if it was ever shared, and update Render.
- This layer was tested against a real PostgreSQL 16, but the live Supabase connection must be checked by running
  `scripts/check_supabase.py` with your own connection string.

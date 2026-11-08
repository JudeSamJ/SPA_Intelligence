# SPA Intelligence: handoff (read this, then `CLAUDE.md`)

Repo `github.com/JudeSamJ/SPA_Intelligence`, branch `main`. Live demo on Render: `https://spa-intelligence-bkf2.onrender.com`.
Product: reads property Sale & Purchase Agreements; LLM extracts, Python calculates, every value has page+quote, humans review the uncertain.

## Stack
FastAPI + pydantic v2 + PyMuPDF (`app/`, `backend/api/`) · React 19 + Vite + TS + TanStack Query + GSAP, EN/AR RTL (`frontend/src`) ·
PostgreSQL via Supabase (`app/db.py`, `supabase/schema.sql`) · Supabase Auth (server-side) · Azure OpenAI (extraction/chat) ·
optional OCR: Docling and/or Qwen vision model (`app/ocr/`) · optional Power Platform/Copilot Studio (`integrations/`) · email: SMTP or webhook.

## Map
| Area | Where |
|---|---|
| Extraction, grounding, evidence boxes, review | `app/extract.py`, `grounding.py`, `evidence.py`, `review.py` |
| Calculators | `penalty.py`, `cashflow.py`, `montecarlo.py`, `statute_gap.py`, `obligations.py` (rules in `rules/`) |
| Buyer assistant + refusals | `app/agent.py`, `app/buyer.py`, `backend/api/routes/buyer.py` |
| DB persistence (files mirror, restore on boot) | `app/db.py`, `app/mirror.py`, `backend/api/persistence.py` |
| RBAC / buyers | `app/users.py`, `app/buyers.py`, `backend/api/auth.py`, `routes/{users,buyers,supabase_auth}.py` |
| OCR | `app/ocr/` (+ `docs/ocr.md`), hook in `extract.postprocess`, job step in `deps.start_extraction` |
| Email | `app/notifiers.py` (SMTP + webhook), `app/emailcards.py` |
| Frontend pages | `frontend/src/pages/*` (Login, Reset, Pending, BuyerHome, Users, Buyers, Terms…), nav in `components/TopBar.tsx`, roles in `auth/roles.ts` |

## Auth and roles (`AUTH_MODE=off|entra|apikey|supabase`; production uses `supabase`)
Admin (`ADMIN_EMAILS`) > Reviewer (writes) > Staff (read) ; Buyer = own contract chat only (auto by confirmed email linked on **Buyers** page).
No role = "waiting for approval". Machine channels use `X-API-Key` with role `Spa.Channel` + `X-Buyer-Identity`. Roles live in table `app_users`, checked per request.
Server refuses to start if supabase mode is misconfigured.

## OCR (built, tested, NOT yet configured or run live by the owner)
Scans: pages with an image and <25 chars of text are OCR'd, text is added back as an invisible layer (same contract id, original kept in `uploads/originals/`).
Engines: Docling (heavy, not for 512 MB Render) and Qwen via OpenAI-compatible API. Both configured = cross-check per page **and per number**; one engine = all values go to review (`OCR_REVIEW_UNVERIFIED=0` relaxes).
Verified: fakes, mock HTTP, **real Tesseract behind a stand-in Qwen endpoint** over HTTP, real browser upload, Docling geometry vs Docling's own classes.
**Not verified:** a real Qwen model, a full Docling OCR run (models could not download here).

### OCR rollout checklist (owner + agent)
1. Owner picks a provider and a Qwen **vision** model name (e.g. Alibaba Model Studio; or self-hosted vLLM/Ollama via `QWEN_BASE_URL`). Confirm they may send contract page images to it.
2. Render env: `QWEN_API_KEY`, `QWEN_MODEL`, optional `QWEN_BASE_URL`. (Optionally `OCR_ENGINE=qwen`.) Redeploy latest `main`.
3. `GET /api/health` must show `"ocr":{"enabled":true,"engine":"qwen",...}`.
4. From any machine with the same env: `python scripts/check_ocr.py` (PASS/FAIL, no secrets printed). Fix per output.
5. Upload a real scanned SPA: chip "Reading scanned pages…" → Extracted; open Terms: OCR warnings + review flags; click a page chip: highlight must sit on the right words.
6. If highlights are misplaced set `QWEN_BBOX_MODE=pixels` or `relative1000`. If the model returns no boxes, highlights are approximate (warning shown).
7. Optional second reader: run Docling on a larger host (`pip install -r requirements-ocr.txt`; needs HF access) and set it as `OCR_ENGINE=docling` there with Qwen verifying.
8. Measure real accuracy on the owner's own scans; tune `OCR_AGREEMENT_MIN`, `OCR_DPI`; add scans to the eval set.

## Environment variables (Render; never commit values)
Core: `AUTH_MODE=supabase` `SUPABASE_URL` `SUPABASE_ANON_KEY` (publishable key ok) `SESSION_SECRET`(32+) `PUBLIC_BASE_URL` `ADMIN_EMAILS` `DATABASE_URL` (**Session pooler** string; direct host is IPv6-only and fails on Render) `SERVE_FRONTEND=1` `NODE_VERSION=22`.
LLM: `LLM_PROVIDER=azure_openai` `AZURE_OPENAI_API_KEY/ENDPOINT/DEPLOYMENT` `LLM_MAX_CALLS`. Machine keys: `API_KEYS` (JSON). Optional GitHub sign-in: `GITHUB_*`, `GITHUB_USERS`.
Email: `SMTP_HOST/PORT/USER/PASSWORD/FROM` `ALERT_EMAIL_TO`; or `ALERT_WEBHOOK_URL/SECRET`. OCR: see `docs/ocr.md`. Start cmd: `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`.
Free-tier facts: disk is wiped on restart (DB mirror restores it), service sleeps when idle, 512 MB RAM.

## Run and test
- Local PostgreSQL for tests (root sandbox): `su postgres -c "initdb -D /tmp/pgdata/c1 -A trust -U postgres"` then `pg_ctl -D /tmp/pgdata/c1 -o '-p 54329 -k /tmp/pgdata -c listen_addresses=127.0.0.1' -l /tmp/pgdata/log start` (binaries in `/usr/lib/postgresql/16/bin`). Tests use `TEST_DATABASE_URL` (default that server) and refuse to drop tables on non-local hosts.
- Tesseract tests need `apt-get update && apt-get install -y tesseract-ocr`; skipped if absent. Docling test: skipped unless `docling` installed.
- Python env: `.venv` (`pip install -r requirements.txt`). Always `OMP_THREAD_LIMIT=1` when running Tesseract in parallel.
- E2E (311 checks): `rm -rf /tmp/spa-e2e; SERVE_FRONTEND=1 E2E_UNSEEDED=sample_c.pdf E2E_FIXTURE_CASE=1 python -m backend.tests.e2e_server &` then `NODE_PATH=$(npm root -g) node scripts/e2e_check.mjs` (it rewrites `docs/screenshots`; commit only if all pass). Wrong env = false failures.
- Auth/OCR browser scripts: `scripts/checks/README.md`.

## Status (fill from last run)
Last run at commit `a26e052`: backend 403 passed + 1 skipped (Docling-only), frontend 117 passed, tsc/eslint clean, production build OK. Browser suite 311/311 passed at `941f749` (before OCR); re-run after OCR is recorded in the git log if it passed.

## Owner actions still open (agent should remind, not do)
1. Reset the Supabase DB password (pasted in chat twice) and update `DATABASE_URL`; rotate the staff/buyer API keys and Power Automate flow URL pasted earlier.
2. OCR rollout checklist above (steps 1-5 need the owner's keys/accounts).
3. Supabase: custom SMTP (done by owner), redirect URLs include `/login` and `/reset`.
4. Lawyer review of `rules/packs/*` and refusal wording; native Arabic review of strings.
5. Real Teams/Copilot/WhatsApp work is optional; WhatsApp (Twilio sandbox endpoint) was designed but **not built**.

## Backlog (suggested order)
1. Finish OCR live verification; fix issues found. 2. Portfolio dashboard (total delay exposure, open reviews, deadlines this month).
3. Bulk upload. 4. Larger labelled accuracy set incl. scans (`eval/`). 5. Production hosting (paid Render, backups, error alerts, domain).
6. Arabic OCR text layer. 7. Add auth/OCR browser checks to CI-style scripts. 8. Optional WhatsApp endpoint.

## Known gotchas
- Contract id = SHA-256 of the **uploaded** file; OCR'd uploads keep it via `.meta.json` `"id"` (`deps._stable_id`).
- `/api/health` response model has literals (auth modes); extending a mode needs the schema + `frontend/src/api/types.ts` updated (a past 500).
- Hard-coded `choose` binding breaks monkeypatching; call `ocr.choose()` via the module.
- New tests must be shown to fail without the fix; skipped tests (no local Postgres) are not a pass.

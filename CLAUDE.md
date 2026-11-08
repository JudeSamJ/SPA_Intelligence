# SPA Intelligence: rules for any agent working here

Read `docs/HANDOFF.md` first (state, architecture, commands, backlog). Business logic: `docs/business-logic.md`.

## Non-negotiable product rules
- The LLM only **extracts**. All arithmetic (delay interest, cap, cash flow, statute gap) is tested Python. Never let a model compute money.
- Every extracted value carries `source_page` + `source_quote`. Missing = `null` / "not stated". Never guess, never invent data.
- Output is "Decision support, not legal advice." Legal-advice and other-buyer questions are refused **before** any model call.
- Statute packs are marked `reviewed_by_lawyer: false`; do not remove that flag. Arabic text needs native review.
- Keep Power Automate / Copilot Studio **optional**; do not extend them. No Power BI. No new features outside the core workflow unless asked.

## Working agreements (the owner's explicit decisions)
- Work on `main` only. Commit only **tested** work. Author `JudeSamJ <judesam.work@gmail.com>`. **No** attribution/co-author trailers.
- Never write secrets into the repo, logs, tests or chat. Server env only. The owner has pasted keys/passwords in chat before: flag and advise rotation.
- Do not make live calls with the company Azure OpenAI key unless asked (there is a per-process cap, `LLM_MAX_CALLS`).
- Report results faithfully: say what was **not** verified (no live Supabase/Qwen/Docling access from the sandbox).
- Prefer minimal, additive changes; keep existing tests green; add tests for every behaviour change (and make sure a new test fails without the fix).

## Quick commands
- Backend tests: `.venv/bin/python -m pytest -q` (DB tests need local PostgreSQL, else they skip; see HANDOFF.md)
- Frontend: `cd frontend && npx tsc --noEmit -p . && npx eslint src && npx vitest run && npm run build`
- Browser suite: see HANDOFF.md ("E2E").

# Browser checks used during development (not part of the automated suite)

Need: `playwright` on NODE_PATH (`NODE_PATH=$(npm root -g)`), a built frontend (`cd frontend && npm run build`), a local PostgreSQL on
127.0.0.1:54329 (see HANDOFF.md), and for OCR: `apt install tesseract-ocr`.

- `fake_gotrue.py` stands in for Supabase Auth on 127.0.0.1:9999. Start it, then start `python -m backend.tests.e2e_server` with
  `AUTH_MODE=supabase SUPABASE_URL=http://127.0.0.1:9999 SUPABASE_ANON_KEY=anon-public-key-123456 SESSION_SECRET=<40 chars>
  PUBLIC_BASE_URL=http://localhost:8000 ADMIN_EMAILS=boss@co.com DATABASE_URL=postgresql://postgres@127.0.0.1:54329/postgres SERVE_FRONTEND=1`,
  then `node auth_flow.js` (18 checks: roles, buyer isolation, role removal, sign-out).
- `ocr_app.py` runs the real app with real OCR (Tesseract behind a stand-in Qwen endpoint) and a fake model on :8124;
  `ocr_ui.js` uploads a scanned PDF through the UI (expects /tmp/scan2.pdf, an image-only copy of samples/sample_a.pdf).
Paths inside are for the sandbox; adjust as needed.

# SPA Intelligence

Decision support for UAE off-plan **Sale and Purchase Agreements (SPAs)**: upload a PDF, get the key terms with the
**page and exact source quote** for each, a deterministic **delay-penalty simulator**, a **cash-flow** view, a
**buyer assistant** that answers only from the extracted contract, and an **accuracy** table.

> **Decision support, not legal advice.** The banner is shown on every screen of the app; you can dismiss it and restore it from the corner tab.

Design principle: **cinematic outside, clear inside.** The landing page, transitions, loaders and empty/error states use
heavy GSAP, WebGL and canvas effects. The data layer (terms, penalty and cash-flow figures, chat answers) only gets
entrance animations: no continuous distortion, and every number settles on the exact value the API returned.

## Hard rules (enforced in code and tests)

1. The LLM only extracts and phrases. All arithmetic (penalties, cash-flow, percentage sums) is plain, unit-tested Python.
2. Every extracted value carries `source_page` and `source_quote`; `null` if the document does not state it. Quotes are verified against the PDF text after extraction.
3. No fake or hardcoded numbers in the UI: everything rendered comes from API responses. Skyline, dunes, particles are decorative only.
4. Jurisdiction rules live in `rules/uae.yaml` (day-count, scenarios, the "at risk" definition, legal-advice patterns).
5. The buyer agent answers only from the selected contract's JSON, cites the quote, refuses legal-advice questions ("please contact the legal team"), and treats contract text as data, not instructions.
6. The disclaimer is shown on every screen by default. It can be dismissed (the choice is remembered), and a small scales tab stays in the corner so it is always one click away.
7. API keys stay on the server. The browser bundle contains no key names (checked on every build).

## Architecture

```
 Browser (Vite + React + TS)                    FastAPI (backend/api)                    Core (app/)
 ┌───────────────────────────────┐   /api   ┌──────────────────────────────┐   ┌───────────────────────────────┐
 │ landing: GSAP, WebGL, SVG     │─────────▶│ routes: contracts, penalty,  │──▶│ extract.py  PDF -> ContractData│
 │ app: terms | penalty | cash-  │◀─────────│   cashflow, chat, eval       │   │ penalty.py  pure maths         │
 │   flow | assistant | accuracy │  JSON    │ upload checks, rate limits,  │   │ cashflow.py pure maths         │
 │ i18n EN/AR (RTL), 2 themes    │          │ CORS allow-list, error shape │   │ agent.py    tools over the JSON│
 │ typed client from OpenAPI     │          │ jobs (extraction), gzip      │   │ llm.py      Azure / Anthropic  │
 └───────────────────────────────┘          └──────────────────────────────┘   │ rules/uae.yaml                 │
                                                                                └───────────────────────────────┘
```

```
spa-intel/
├── backend/api/        main.py, routes/{contracts,penalty,cashflow,chat,eval}.py, schemas.py, deps.py
├── backend/tests/      test_api.py (LLM mocked), e2e_server.py (test-only stub server)
├── app/                core logic: schema, extract, penalty, cashflow, agent, llm, config
├── frontend/           Vite + React + TS (src/api, i18n, motion, scenes, components, pages, styles, state)
├── samples/            three synthetic Dubai SPAs (generated)        ground_truth.json
├── rules/uae.yaml      eval/run_eval.py        scripts/        docs/ (screenshots, video, reports)
```

## Setup

Python 3.11+ and Node 20+.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the Azure OpenAI values (see below)
cd frontend && npm install && cd ..
```

`.env` (server side only; it is gitignored):

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `azure_openai` (default) or `anthropic` |
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` | your Azure resource; the endpoint can be `https://<res>.openai.azure.com/` or the Foundry v1 form `https://<res>.services.ai.azure.com/openai/v1/`; the deployment is the deployment *name* |
| `AZURE_OPENAI_API_VERSION` | classic endpoints only (not the model version) |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | if `LLM_PROVIDER=anthropic` |
| `LLM_MAX_CALLS` | hard cap on LLM calls per server process (default 40) |
| `CORS_ORIGINS` | comma-separated explicit origins (default `http://localhost:5173`); a wildcard is ignored |
| `SERVE_FRONTEND` | `1` to serve `frontend/dist` from the API |
| `RATE_UPLOADS`, `RATE_CHAT` | requests per minute per IP (defaults 10, 30) |

## Run

```bash
npm run dev          # API on :8000 and Vite on :5173 together (or dev:backend / dev:frontend separately)
npm run build && npm run serve    # production-style: one server on :8000 serving the built frontend (gzip + immutable caching)
npm test             # pytest (94) + vitest (75)
npm run lint         # eslint (typescript-eslint, react-hooks); tsc runs in `npm run build`
npm run gen:api      # regenerate frontend/src/api/types.ts from the FastAPI OpenAPI schema
npm run e2e          # Playwright end-to-end checks (needs `playwright`; see "Verification")
python eval/run_eval.py --yes      # extraction accuracy vs ground_truth.json (uses LLM calls only for uncached samples)
```

Extraction costs 1 LLM call (2 if the first answer fails validation) and is cached by file hash and model. Nothing calls the
model on page load: extraction runs only when you click **Extract** (or upload), and the API refuses scanned PDFs.

## API (`/api`, JSON; errors are `{"error": {"code", "message"}}`)

| Method and path | Purpose |
|---|---|
| `GET /health` | status, whether the LLM is configured, call counter and cap |
| `GET /contracts` | samples + uploads with status (`not_extracted`, `queued`, `running`, `extracted`, `error`) |
| `POST /contracts/upload` | multipart PDF only: magic-byte + parse check, 20 MB and 300-page limits, rate limited; starts an async extraction job |
| `GET /contracts/{id}/status` | poll an extraction job |
| `POST /contracts/{id}/extract?force=` | start (or re-run) extraction, cached otherwise |
| `GET /contracts/{id}` | extracted terms (value, page, quote), warnings, plan rows with computed amounts |
| `GET /contracts/{id}/pdf` | the PDF, inline |
| `POST /contracts/{id}/penalty` | `{scenarios}`: deterministic penalty table (default scenarios from `rules/uae.yaml`) |
| `POST /contracts/{id}/cashflow` | `{granularity, delay_days}`: schedule, at-risk summary and the definition text |
| `POST /contracts/{id}/chat` | `{message, history}`: answer, citations, `refused` |
| `GET /eval/results`, `POST /eval/run`, `GET /eval/run/status` | accuracy results; running asks for explicit confirmation before spending LLM calls |

Contract ids are SHA-256 file hashes (validated); contract text and keys are never logged; uploads are stored as `<hash>.pdf`
with a sanitised display name.

## Effects inventory: GSAP plugin to feature

All animation code is in `frontend/src/motion/` and `frontend/src/scenes/`; every plugin is registered in
`motion/registry.ts` (core eagerly, heavy ones lazy). Components use `useGSAP` for cleanup and `gsap.matchMedia()` (via
`useMotion`) for desktop/mobile variants.

| Plugin / tool | Where it is used |
|---|---|
| ScrollTrigger | pinned and scrubbed skyline and roadmap scenes; for the Palm it only *starts* a time-based animation when the scene enters view (the island grows from the sea: ripples, trunk, fronds sprout, crescent sweeps, plane flies), so scroll speed and direction cannot affect it; the skyline lights the tower tier by tier with each step's card beside it; snap to step labels; batch reveals; progress bar |
| ScrollSmoother | smooth scrolling and `data-speed` parallax on the **landing page only** (off on data pages, touch, lite, reduced, and on macOS/iOS where native momentum scrolling is already smooth) |
| ScrollToPlugin | anchor navigation, jump to the PDF panel from a citation, and the frame-settling glide when there is no smoother |
| SplitText | hero headline reveal (Arabic is split by words/lines only, never characters) |
| ScrambleTextPlugin | hero tagline decode; decode on extracted field values (resolves to the exact text) |
| TextPlugin | assistant reply typewriter (HTML-escaped twice, finalised with `textContent`; tested with real GSAP) |
| DrawSVGPlugin | Palm Jumeirah line art, loader star |
| MorphSVGPlugin | sun to moon theme toggle, day to night skyline silhouette, loader shape |
| MotionPathPlugin | dhow along the horizon wave, plane on the Palm crescent, payment dot on the milestone timeline (mirrored in RTL) |
| Flip | sidebar card expansion, tab highlight pill, terms table re-sort |
| Draggable + InertiaPlugin | rotary delay dial that snaps to presets (also keyboard accessible), draggable milestone timeline |
| Physics2DPlugin | gold-coin / sand burst when extraction completes |
| PhysicsPropsPlugin | falling dust on error states |
| CustomEase / CustomWiggle / CustomBounce | `dune` settle ease; warning-card wiggle; CTA bounce |
| RoughEase / SlowMo / ExpoScaleEase | glitch jitter; hero eyebrow reveal; slow push-in on the hero scene |
| quickTo / quickSetter, stagger, utils | magnetic buttons, 3D tilt cards, table row entrances |
| GSDevTools, MotionPathHelper | **dev only** (`?devtools=1` in `vite dev`); absent from production bundles (verified) |

The cursor is a plain orange arrow (CSS image cursor; text fields keep the text caret); there is no custom cursor or trail.

Other effects: ogl WebGL glitch shader (RGB split, scanlines, noise, displacement, heat haze, pointer parallax) on the hero and
route transitions; canvas **sandstorm** route transition; SVG `feTurbulence` heat haze; twinkling stars (dusk); grain overlay;
glass panels; hero **video** with a procedural fallback. Glitch is limited to the hero, transitions, logo and loaders, never data.

Safeguards: `prefers-reduced-motion` **and** a persisted "Reduce effects" toggle switch everything heavy to simple fades
(no video, WebGL, smooth scroll, particles); mobile/low-power uses a "lite" tier; glitch bursts stay well under
3 flashes per second; all ScrollTriggers/tweens are reverted on unmount.

## Scene framing and scrolling (landing page)

- **Framing:** every full-screen scene is centred in the area the user can actually see: the viewport minus the fixed header and the
  disclaimer banner. Their real heights are measured at runtime (`--inset-top`, `--inset-bottom`), so it adapts to display scaling,
  short laptop windows, the Windows taskbar (which already shrinks the browser viewport) and a dismissed banner. The Palm
  illustration is capped to fit that area.
- **Free scrolling, then settle:** scrolling is never hijacked. When it genuinely stops, the page glides to the nearest scene frame in
  the direction of travel (hero, Palm, skyline, roadmap, CTA); a small nudge settles back, a larger one advances. Inside the pinned
  skyline and roadmap scenes it does nothing (they have their own step snapping). Desktop with full effects only.
- **The Palm starts only when framed** (its top within 14% of the viewport) and replays from the start if you scroll away before it
  finishes.
- **macOS:** ScrollSmoother is not used (trackpad and Magic Mouse momentum already scroll smoothly; stacking a smoother on top feels
  floaty). The same framing and settling apply. Windows and Linux wheel mice keep ScrollSmoother.
- **Scrollbar:** themed to the site (navy track with a gold-to-terracotta thumb; sand track with a terracotta thumb in the day theme;
  always dark on the landing page). Chromium/Safari use `::-webkit-scrollbar`; Firefox gets `scrollbar-color`.

## Adding hero video

No footage is shipped (see `frontend/public/media/CREDITS.md`). The hero falls back to the procedural scene. To use your own
**licensed** clip: `scripts/prepare_media.sh path/to/clip.mp4` encodes `hero.mp4`, `hero.webm` and `hero-poster.jpg` (each under
6 MB) into `frontend/public/media` and updates `manifest.json`; then add the licence to `CREDITS.md`. The video is paused when
off-screen and skipped for reduced effects, mobile/lite and data-saver.

## Responsive design (phones and tablets)

The whole app is built to work from 320 px phones up to desktop (breakpoints: 640 px phone, 860 px header, 900 px app shell,
1000 px for the side-by-side skyline steps).

- **Header:** one row on wide screens. On phones it shows the brand, the theme toggle and a **menu** button; the menu holds
  navigation, language, "Reduce effects" and the Arabic-digits option (closes on Escape, outside tap or navigation). Nothing is
  pushed off-screen.
- **Tables become cards on phones:** the extracted terms, payment plan, scenarios, cash-flow periods and accuracy tables show one
  card per row with "label: value" lines (labels come from `data-label`), so no sideways scrolling to find the page number or quote.
- **Touch:** on touch devices every control is at least 44 px tall, controls have no tap delay, inputs are 16 px (no iOS zoom on focus),
  and fixed bars respect safe areas (`viewport-fit=cover`).
- **Layout:** tabs become a 2x2 grid; the contract list is a collapsible panel that is closed once a contract is open; charts are
  shorter, drop the second axis and use compact numbers (490K); scenes size to their content instead of reserving a full screen;
  landscape phones get a tighter hero.
- **Effects on phones:** touch and small screens use the "lite" tier (no smooth scrolling, WebGL, video or pinning).
- **Arabic:** the mobile layout mirrors fully (menu, cards, tabs).

Verified by emulation (Playwright, touch and mobile flags) at 320x640, 360x740, 390x844, 430x932, 768x1024 and 740x360 landscape
on all 7 routes: no horizontal overflow, no off-screen header controls, no cut-off elements, no tap targets under 32 px, and no
sideways-scrolling tables. **This is emulation, not a real device:** I have not tested on physical iOS or Android hardware or in
Safari, so please check on your phone.

## Internationalisation

English and Arabic (`frontend/src/i18n/*.json`), with `<html lang dir>` switched on toggle, logical CSS properties, and
mirrored animations. Contract text and quotes stay in their source language (`dir="auto"`). Figures use Western digits by
default; an Arabic-Indic digits toggle appears in AR mode. **The Arabic translations were written without a native review and
need one before release.** A test keeps the EN/AR key sets identical (allowing Arabic's extra plural forms).

## Verification (what was actually run)

| Check | Result |
|---|---|
| `pytest` | 94 passed (API tests mock the LLM; penalty example 1,000,000 / 6% / 90 days / 30 grace = 9,863.01) |
| `vitest` | 75 passed (API client, responsive header menu, dismissible disclaimer, penalty table from mocked API, chat refusal and plain-text rendering, `dir` toggle, number settling, typewriter safety with real GSAP, EN/AR keys, WCAG contrast of both themes) |
| `eslint`, `tsc` (strict), `prettier --check`, `vite build` | clean |
| Playwright e2e (`scripts/e2e_check.mjs`, 183 checks) | 183/183: landing in 8 theme x language x effects combinations; all 4 tabs for all 3 samples in EN, AR (RTL), day theme and reduced effects; mobile viewport; sample C flags; refusal; citation to PDF page; 9,863.01 case; banner dismiss/restore/remember; skyline lights floor by floor with step cards alternating sides and does not trap scrolling; the Palm animation takes the same time for a slow scroll and a hard flick; scenes settle into a centred frame at Windows- and macOS-like window sizes; themed scrollbar; plain orange cursor; mobile responsiveness across 6 viewports and 7 routes (no overflow, no off-screen controls, 44px touch targets, card tables, header menu); UI numbers equal API values; no console errors. Results in `docs/e2e-results.json`, screenshots in `docs/screenshots/`, demo video `docs/landing-scroll.webm` / `.gif` |
| Bundle | 198 kB gzip on initial load; Draggable, Inertia, Morph, Physics, ScrollSmoother, ogl and the chart library are lazy chunks; 0 key-name strings and 0 GSDevTools/MotionPathHelper in JS |

**Lighthouse 12** (headless Chromium, production build with gzip; single runs; `docs/lighthouse.json`):

| Route | Desktop perf / a11y | Mobile profile perf / a11y |
|---|---|---|
| Terms | 99 / 100 | 86 / 100 |
| Penalty | 99 / 100 | 85 / 100 |
| Cash-flow | 99 / 100 | 70 / 100 |
| Assistant | 100 / 100 | 88 / 100 |
| Accuracy | 99 / 100 | 79 / 100 |
| Landing | 93 / 100 | 75 / 100 |

Accessibility is 100 and best-practices 100 everywhere; CLS is at most 0.03 on desktop and 0.016 on mobile. The mobile profile
(4x CPU slowdown, slow 4G) varies by roughly 8 points between runs and **cash-flow (70), accuracy (79) and landing (75) are below
the 80 target on mobile**: the cost is the chain of requests and lazy chunks, not layout shift. The frame-rate probe measured
about 51 fps on the landing page in headless software-rendered Chromium; that is not representative of a GPU laptop and
was not measured on one.

The e2e and screenshots use `backend/tests/e2e_server.py`, a **test-only** server whose model is a deterministic stub and whose
cache is seeded from ground-truth fixtures, because no model key exists in the build environment. It exercises the real API, core
logic and UI, but extraction and chat text in those screenshots are **not real model output**. Headless Chromium also has no
built-in PDF viewer, so the PDF side panel shows blank in screenshots (the e2e asserts the iframe URL `#page=3` and that the PDF
endpoint serves a valid inline PDF).

## Assumptions and limitations

- Extraction and the eval were last run against the real model **before** the samples were moved to Dubai districts. The sample PDFs
  changed (project names/locations; sample C is now a Downtown unit `OTC-2106`), so cached extractions no longer match and
  `eval/results.json` is stale. Re-run extraction and `python eval/run_eval.py --yes` (3 samples, about 3 LLM calls).
- `gpt-5.4-mini` behaviour on these prompts is verified only on the original samples; prompts may need tuning.
- Scanned PDFs are detected and refused (no OCR yet). English contracts only.
- "At risk" is keyword-based on milestone text (a heuristic); penalty exposure is compensation the buyer could be owed, so it is shown separately as well as summed.
- The legal-advice gate is regex plus prompt based: it can over-refuse (any question containing "cancel") and can miss new phrasings.
- Rate limits and the call cap are in-memory and per process; there is no authentication or database. Put auth in front before exposing a keyed server publicly.
- Landing text is always light on a dark cinematic palette in both themes; the day/dusk themes fully restyle the app.
- ScrollSmoother's `data-speed` is used; `data-lag` is not.

## Roadmap

Document Intelligence / Docling swap behind `extract.py` (scans, complex layouts) · cross-document check · Arabic-English check
(and Arabic contract parsing) · rulebook check against `rules/*.yaml` · WhatsApp assistant · authentication and persistence · a
real, labelled evaluation set · mobile performance (prefetch the contract/cash-flow requests, preload route chunks).

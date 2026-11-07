// End-to-end verification with Playwright against a running server (production bundle served by FastAPI).
//   python -m backend.tests.e2e_server  (stub LLM, fixtures)   then   node scripts/e2e_check.mjs
// Needs `playwright` resolvable (NODE_PATH or local install). Writes docs/screenshots/*.png and prints a summary.
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const OUT = "docs/screenshots";
const results = [];
const consoleErrors = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); if (!ok) console.log(`  FAIL ${name} ${detail}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });

async function ctxFor({ theme = "dusk", lang = "en", reduce = false, vw = 1440, vh = 900 } = {}) {
  const ctx = await browser.newContext({ viewport: { width: vw, height: vh } });
  // seed preferences only once per context so a reload keeps whatever the user toggled
  await ctx.addInitScript(([t, l, r]) => { if (localStorage.getItem("spa.seeded") === null) { localStorage.setItem("spa.theme", t); localStorage.setItem("spa.lang", l); localStorage.setItem("spa.reduce", r ? "1" : "0"); localStorage.setItem("spa.seeded", "1"); } }, [theme, lang, reduce]);
  return ctx;
}
function watch(page, label) {
  page.on("pageerror", (e) => consoleErrors.push(`${label}: PAGEERROR ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(`${label}: ${m.text().slice(0, 200)}`); });
}
const shot = (page, name, full = false) => page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 80, fullPage: full });
const disclaimer = async (page, where) => check(`disclaimer visible: ${where}`, await page.getByTestId("disclaimer").isVisible() && /not legal advice|ليست استشارة|وليس استشارة/.test(await page.getByTestId("disclaimer").innerText()));

const api = await (await fetch(`${BASE}/api/contracts`)).json();
const idOf = (n) => api.find((c) => c.name === n)?.id;
const A = idOf("sample_a.pdf"), B = idOf("sample_b.pdf"), C = idOf("sample_c.pdf"), FX = idOf("fixture_penalty_case.pdf");
const SAMPLE = { a: A, b: B, c: C };
const post = async (path, body) => (await fetch(`${BASE}/api${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json();
const aedFmt = (n, d = 2) => `AED ${new Intl.NumberFormat("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }).format(n)}`;

// ------------------------------------------------------------------ A. landing matrix
console.log("A. landing: theme x language x effects");
for (const theme of ["dusk", "day"]) for (const lang of ["en", "ar"]) for (const reduce of [false, true]) {
  const tag = `${theme}_${lang}_${reduce ? "reduced" : "full"}`;
  const ctx = await ctxFor({ theme, lang, reduce }); const page = await ctx.newPage(); watch(page, `landing ${tag}`);
  await page.goto(`${BASE}/`); await sleep(reduce ? 1200 : 4200);
  check(`landing ${tag}: dir/lang`, (await page.evaluate(() => [document.documentElement.dir, document.documentElement.lang].join())) === (lang === "ar" ? "rtl,ar" : "ltr,en"));
  check(`landing ${tag}: effects mode`, (await page.evaluate(() => document.documentElement.dataset.effects)) === (reduce ? "reduced" : "full"));
  check(`landing ${tag}: headline visible`, await page.locator("h1").first().isVisible());
  if (reduce) check(`landing ${tag}: no video, no sandstorm`, (await page.locator("video").count()) === 0 && (await page.getByTestId("sandstorm").evaluate((e) => getComputedStyle(e).display)) === "none");
  await disclaimer(page, `landing ${tag}`);
  await shot(page, `landing_${tag}`);
  if (theme === "dusk" && lang === "en" && !reduce) {
    const H = await page.evaluate(() => document.documentElement.scrollHeight);
    for (const [n, f] of [["palm", 0.2], ["skyline", 0.36], ["roadmap", 0.62], ["cta", 0.97]]) { await page.evaluate((y) => window.scrollTo(0, y), H * f); await sleep(1700); await shot(page, `landing_scroll_${n}`); }
  }
  await ctx.close();
}

// ------------------------------------------------------------------ B. app: samples x tabs x locales
const TABS = ["terms", "penalty", "cashflow", "assistant"];
async function appPass({ theme, lang, reduce, samples, tag }) {
  const ctx = await ctxFor({ theme, lang, reduce }); const page = await ctx.newPage(); watch(page, `app ${tag}`);
  for (const s of samples) for (const tab of TABS) {
    await page.goto(`${BASE}/app/contracts/${SAMPLE[s]}/${tab}`); await sleep(tab === "terms" ? 2300 : 2800);
    check(`app ${tag} ${s}/${tab}: renders content`, await page.locator("h1").first().isVisible() && (await page.locator("[role=alert]:has-text('Something went wrong')").count()) === 0);
    await disclaimer(page, `app ${tag} ${s}/${tab}`);
    await shot(page, `app_${tag}_${s}_${tab}`);
  }
  await ctx.close();
}

console.log("B0. sample C: extraction flow through the UI (stub model), then flags");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "extract C");
  await page.goto(`${BASE}/app/contracts/${C}/terms`); await sleep(1800);
  check("C: not-extracted state offers Extract + cost note", await page.getByRole("button", { name: "Extract with the model" }).isVisible() && /1 LLM call/.test(await page.locator("body").innerText()));
  await shot(page, "app_extract_C_before");
  await page.getByRole("button", { name: "Extract with the model" }).click();
  await page.getByRole("status").filter({ hasText: "Extracting contract terms" }).first().waitFor({ timeout: 4000 }).then(() => check("C: visible progress while extracting", true)).catch(() => check("C: visible progress while extracting", false));
  await shot(page, "app_extract_C_progress");
  await page.getByTestId("extracted-info").waitFor({ timeout: 15000 });
  await sleep(2200); await shot(page, "app_extract_C_after");
  const body = await page.locator("body").innerText();
  check("C: percentage-sum warning shown", /sum to 95%/.test(body));
  check("C: missing-cancellation flag shown", /No cancellation clause found/.test(body));
  check("C: cancellation row highlighted as not found", /Not found in contract/.test(await page.getByTestId("row-cancellation_clause").innerText()));
  check("C: plan total chip shows 95% (alert styled)", /95%/.test(await page.getByTestId("plan-total").innerText()));
  await ctx.close();
}

console.log("B1-B4. app tabs for all 3 samples (EN dusk, AR RTL dusk, EN day, EN reduced)");
await appPass({ theme: "dusk", lang: "en", reduce: false, samples: ["a", "b", "c"], tag: "dusk_en" });
await appPass({ theme: "dusk", lang: "ar", reduce: false, samples: ["a", "b", "c"], tag: "dusk_ar" });
await appPass({ theme: "day", lang: "en", reduce: false, samples: ["a"], tag: "day_en" });
await appPass({ theme: "dusk", lang: "en", reduce: true, samples: ["c"], tag: "reduced_en" });

// ------------------------------------------------------------------ C. behaviours
console.log("C1. chat: refusal, answer with quote, clickable page citation");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "chat");
  await page.goto(`${BASE}/app/contracts/${A}/assistant`); await sleep(1800);
  const ask = async (q) => { await page.getByLabel(/Ask about payments/).fill(q); await page.getByRole("button", { name: "Send" }).click(); };
  await ask("can I cancel and get a refund?");
  const refused = page.getByTestId("msg-refused"); await refused.waitFor({ timeout: 6000 });
  check("chat: cancel/refund refused with 'legal team'", /legal team/.test(await refused.innerText()));
  await ask("What is the handover date?");
  const ans = page.getByTestId("msg-assistant").last(); await ans.waitFor({ timeout: 8000 }); await sleep(2500);
  const txt = await ans.innerText();
  check("chat: handover answer contains the date and the quote", /2027-06-30/.test(txt) && /30 June 2027/.test(txt), txt.slice(0, 120));
  await shot(page, "chat_answer");
  const cite = page.getByTestId("citation").last(); check("chat: citation chip shows page 3", /Page 3/.test(await cite.innerText()));
  await cite.click(); await sleep(900);
  const panel = page.locator("#pdf-panel"); check("chat: citation opens the PDF panel", await panel.isVisible());
  check("chat: PDF panel shows page 3 as an image", /\/page\/3\.png/.test((await panel.locator("img").first().getAttribute("src")) ?? ""));
  await page.getByTestId("highlight").first().waitFor({ timeout: 8000 }).then(() => check("chat: the cited quote is highlighted on the page", true)).catch(() => check("chat: the cited quote is highlighted on the page", false));
  await shot(page, "chat_pdf_panel");
  await ask("Is there a parking allocation?"); await sleep(2800);
  check("chat: outside-contract question says not stated", /not stated in the contract/i.test(await page.getByTestId("chat-log").innerText()));
  await ctx.close();
}

console.log("C2. penalty: UI equals API, 9,863.01 case, no intermediate numbers");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "penalty");
  const fx = await post(`/contracts/${FX}/penalty`, { scenarios: [90] });
  check("API: fixture 1,000,000 / 6% / grace 30 / 90 days = 9863.01", fx.rows[0].penalty === 9863.01, JSON.stringify(fx.rows[0]));
  await page.goto(`${BASE}/app/contracts/${FX}/penalty`); await sleep(2500);
  await page.getByRole("button", { name: /^90 days$/ }).click(); await sleep(2200);
  const ui = (await page.getByTestId("penalty-amount").innerText()).trim();
  check("UI shows AED 9,863.01 for the 90-day preset", ui === "AED 9,863.01", ui);
  await shot(page, "penalty_9863_01");
  await page.goto(`${BASE}/app/contracts/${A}/penalty`); await sleep(2500);
  for (const d of [30, 90, 180, 365, 90, 180]) { await page.getByRole("button", { name: new RegExp(`^${d} days$`) }).click(); await sleep(140); }
  await sleep(2200);
  const apiA = await post(`/contracts/${A}/penalty`, { scenarios: [180] });
  const want = aedFmt(apiA.rows[0].penalty);
  const got1 = (await page.getByTestId("penalty-amount").innerText()).trim(); await sleep(1800);
  const got2 = (await page.getByTestId("penalty-amount").innerText()).trim();
  check("UI amount equals API value after rapid scenario changes", got1 === want && got2 === want, `${got1} | ${got2} | want ${want}`);
  const rows = await page.getByTestId("scenario-row").allInnerTexts();
  const defaults = await post(`/contracts/${A}/penalty`, {});
  check("scenario table equals API rows", defaults.rows.every((r) => rows.some((t) => t.includes(aedFmt(r.penalty)))));
  await page.getByTestId("dial").focus(); await page.keyboard.press("ArrowRight"); await sleep(900);
  check("dial is keyboard accessible (ArrowRight changes days)", (await page.getByTestId("dial").getAttribute("aria-valuenow")) === "181", await page.getByTestId("dial").getAttribute("aria-valuenow"));
  await ctx.close();
}

console.log("C3. cash-flow: KPIs equal API");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "cashflow");
  await page.goto(`${BASE}/app/contracts/${A}/cashflow`); await sleep(3200);
  const cf = await post(`/contracts/${A}/cashflow`, { granularity: "quarter" });
  const k = async (id) => (await page.getByTestId(id).innerText()).trim();
  check("KPI linked equals API", (await k("kpi-linked")) === aedFmt(cf.at_risk.linked_amount, 0), await k("kpi-linked"));
  check("KPI penalty exposure equals API", (await k("kpi-exposure")) === aedFmt(cf.at_risk.penalty_exposure, 0));
  check("KPI at-risk total equals API", (await k("kpi-atrisk")) === aedFmt(cf.at_risk.at_risk_total, 0));
  check("at-risk definition comes from the API", (await page.getByTestId("at-risk-definition").innerText()).trim() === cf.at_risk_definition);
  check("timeline has a node per dated milestone and a payment dot", (await page.getByTestId("timeline-node").count()) === 5 && (await page.getByTestId("payment-dot").count()) === 1);
  check("chart renders", await page.getByTestId("cashflow-chart").locator("svg").first().isVisible());
  await ctx.close();
}

console.log("C4. RTL layout mirror + Western digits by default");
{
  const ctx = await ctxFor({ lang: "ar" }); const page = await ctx.newPage(); watch(page, "rtl");
  await page.goto(`${BASE}/app/contracts/${A}/penalty`); await sleep(2800);
  const side = await page.locator("[data-shell-side]").boundingBox(); const main = await page.locator("[data-split-main]").boundingBox();
  check("RTL: sidebar sits on the right of the content", side.x > main.x, `${side.x} vs ${main.x}`);
  const amt = await page.getByTestId("penalty-amount").innerText();
  check("AR: figures use Western digits by default", /[0-9]/.test(amt) && !/[٠-٩]/.test(amt), amt);
  await page.getByLabel("الأرقام الهندية").check().catch(async () => { await page.getByText("الأرقام الهندية").click(); }); await sleep(900);
  check("AR: Arabic-Indic digits only after opting in", /[٠-٩]/.test(await page.getByTestId("penalty-amount").innerText()));
  await ctx.close();
}

console.log("C5. route transition, toggles, uploads, accuracy, 404");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "misc");
  await page.goto(`${BASE}/`); await sleep(3500);
  let seen = false; const poll = setInterval(async () => { try { if ((await page.getByTestId("sandstorm").evaluate((e) => getComputedStyle(e).display)) === "block") seen = true; } catch { /* navigating */ } }, 60);
  await page.getByRole("button", { name: "Open the app" }).first().click(); await page.waitForURL(/\/app$/, { timeout: 6000 }); await sleep(900); clearInterval(poll);
  check("route transition: sandstorm overlay shown, then app opened", seen && /\/app$/.test(page.url()));
  await page.getByRole("button", { name: "sample_a.pdf" }).click(); await sleep(1800);
  // upload: not a real pdf
  await page.locator("input[type=file]").setInputFiles({ name: "evil.pdf", mimeType: "application/pdf", buffer: Buffer.from("MZ this is not a pdf") }); await sleep(1500);
  check("upload: fake PDF rejected with the server's message", /Only PDF files are accepted|could not be read as a PDF/.test(await page.locator("body").innerText()));
  // upload: valid pdf the stub model can't read -> visible failure
  if (fs.existsSync("/tmp/spa-e2e/other.pdf")) {
    await page.locator("input[type=file]").setInputFiles("/tmp/spa-e2e/other.pdf"); await sleep(4500);
    check("upload: extraction failure is shown (no silent hang)", /Upload failed/.test(await page.locator("body").innerText()));
  }
  await shot(page, "app_upload_states");
  await page.getByRole("button", { name: /Reduce effects/ }).click(); await sleep(300);
  check("toggle: Reduce effects switches the mode", (await page.evaluate(() => document.documentElement.dataset.effects)) === "reduced");
  await page.reload(); await sleep(1500);
  check("toggle: preference persists after reload", (await page.evaluate(() => document.documentElement.dataset.effects)) === "reduced");
  await page.goto(`${BASE}/app/accuracy`); await sleep(2500);
  check("accuracy: page loads with golden-set note", await page.getByTestId("golden-note").isVisible());
  await disclaimer(page, "accuracy"); await shot(page, "accuracy");
  await page.goto(`${BASE}/does-not-exist`); await sleep(1200);
  check("404 page renders with disclaimer", /not found/i.test(await page.locator("h1").innerText()) && await page.getByTestId("disclaimer").isVisible());
  await ctx.close();
}

console.log("C6. mobile viewport (lite effects tier): landing + app");
{
  const ctx = await browser.newContext({ viewport: { width: 412, height: 823 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  await ctx.addInitScript(() => { localStorage.setItem("spa.reduce", "0"); });
  const page = await ctx.newPage(); watch(page, "mobile");
  await page.goto(`${BASE}/`); await sleep(3000);
  check("mobile: lite tier (no smooth scroll / WebGL / video)", (await page.evaluate(() => document.documentElement.dataset.effects)) === "lite" && (await page.locator("video").count()) === 0);
  check("mobile: no horizontal overflow on landing", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await disclaimer(page, "mobile landing"); await shot(page, "mobile_landing");
  await page.goto(`${BASE}/app/contracts/${A}/terms`); await sleep(2600);
  check("mobile: no horizontal overflow in the app", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  check("mobile: contracts list is a collapsed panel once a contract is open", (await page.locator("details.card").first().evaluate((d) => d.open)) === false);
  await disclaimer(page, "mobile app"); await shot(page, "mobile_app_terms");
  await ctx.close();
}

console.log("C7. disclaimer is dismissible, restorable and remembered");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "banner");
  await page.goto(`${BASE}/app/contracts/${A}/terms`); await sleep(1800);
  check("banner shown by default", await page.getByTestId("disclaimer").isVisible());
  await page.getByTestId("disclaimer-dismiss").click(); await sleep(300);
  check("banner can be dismissed", (await page.getByTestId("disclaimer").count()) === 0 && await page.getByTestId("disclaimer-show").isVisible());
  check("dismissed banner frees the bottom padding", (await page.evaluate(() => getComputedStyle(document.body).paddingBottom)) === "0px");
  await page.reload(); await sleep(1500);
  check("dismissal is remembered after reload", (await page.getByTestId("disclaimer").count()) === 0 && await page.getByTestId("disclaimer-show").isVisible());
  await page.getByTestId("disclaimer-show").click(); await sleep(300);
  check("banner can be restored with one click", await page.getByTestId("disclaimer").isVisible());
  await ctx.close();
}

console.log("C8. skyline: tower lights up step by step with cards on alternating sides");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "skyline");
  await page.goto(`${BASE}/`); await sleep(4500);
  const top = await page.evaluate(() => document.getElementById("skyline").parentElement.offsetTop);
  // scroll like a user (wheel increments), not by teleporting: scroll-snapping and smoothing behave differently on jumps
  const wheelTo = async (y) => { for (let i = 0; i < 260; i++) { const cur = await page.evaluate(() => window.scrollY); if (Math.abs(cur - y) < 60) break; await page.mouse.wheel(0, Math.sign(y - cur) * Math.min(220, Math.abs(y - cur))); await sleep(28); } await sleep(1800); };
  const state = () => page.evaluate(() => {
    const tower = document.querySelector("#burj [data-tier=\"0\"]").getBoundingClientRect(); const cx = tower.left + tower.width / 2;
    const cards = [...document.querySelectorAll("[data-feature]")].map((c) => { const r = c.getBoundingClientRect(); return { visible: +getComputedStyle(c).opacity > 0.9 && getComputedStyle(c).visibility !== "hidden", side: r.left + r.width / 2 < cx ? "left" : "right", y: Math.round(r.top + r.height / 2) }; });
    const lit = (b) => [...document.querySelectorAll(`#burj [data-win][data-band="${b}"]`)].filter((w) => +getComputedStyle(w).opacity > 0.5).length;
    return { cards, lit: [0, 1, 2, 3].map(lit) };
  });
  await wheelTo(top + 5);
  const s0 = await state();
  await wheelTo(top + 900 * 3.8 * 0.4);
  const s1 = await state();
  await wheelTo(top + 900 * 3.8 * 0.99);
  const s2 = await state();
  await shot(page, "skyline_final");   // the finished scene: all four bands lit, all four steps shown
  const reachedEnd = await page.evaluate(() => window.scrollY);
  await wheelTo(top + 900 * 3.8 + 700);   // keep scrolling: the section must let go (no snap-back trap)
  const after = await page.evaluate(() => window.scrollY);
  check("skyline: scrolling past the end is not pulled back by snapping", after > top + 900 * 3.8 + 300, `${reachedEnd} -> ${after}`);
  check("skyline: nothing lit and no cards at the start", s0.lit.every((n) => n === 0) && s0.cards.every((c) => !c.visible), JSON.stringify(s0));
  check("skyline: mid-scroll lights lower bands only, cards 1-2 shown", s1.lit[0] > 0 && s1.lit[3] === 0 && s1.cards[0].visible && !s1.cards[3].visible, JSON.stringify(s1));
  check("skyline: at the end all 4 bands are lit and all 4 cards shown", s2.lit.every((n) => n > 0) && s2.cards.every((c) => c.visible), JSON.stringify(s2));
  check("skyline: cards alternate left / right of the tower", s2.cards.map((c) => c.side).join() === "left,right,left,right", s2.cards.map((c) => c.side).join());
  check("skyline: step 1 is lowest and step 4 highest (matches the tower bands)", s2.cards[0].y > s2.cards[1].y && s2.cards[1].y > s2.cards[2].y && s2.cards[2].y > s2.cards[3].y, s2.cards.map((c) => c.y).join());
  await ctx.close();
}

console.log("C9. Palm animation is time-based (scroll speed cannot affect it); cursor is a plain orange arrow");
{
  const ctx = await ctxFor();
  const measure = async (mode) => {
    const page = await ctx.newPage(); watch(page, `palm ${mode}`);
    await page.goto(`${BASE}/`); await sleep(4500);
    const pinned = await page.evaluate(() => /pin-spacer/.test(document.getElementById("palm").parentElement.className));
    // progress proxy: mean frond scale (0..1) via the SVG transform API, sampled every animation frame
    await page.evaluate(() => { window.__s = []; const fr = [...document.querySelectorAll("#palm .frond")]; const t0 = performance.now(); const tick = () => { const now = performance.now(); let sc = 0; for (const e of fr) sc += e.transform.baseVal.numberOfItems ? e.transform.baseVal.consolidate().matrix.a : 1; window.__s.push([now - t0, sc / fr.length]); if (now - t0 < 12000) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
    // approach the Palm the way a user does (scroll toward it, then STOP); settling then frames it, which starts the animation
    const frame = await page.evaluate(() => Math.round(document.getElementById("palm").getBoundingClientRect().top + window.scrollY));
    if (mode === "flick") for (let i = 0; i < 60 && (await page.evaluate(() => window.scrollY)) < frame - 200; i++) { await page.mouse.wheel(0, 170); await sleep(22); }
    else for (let i = 0; i < 120 && (await page.evaluate(() => window.scrollY)) < frame - 80; i++) { await page.mouse.wheel(0, 60); await sleep(55); }
    await sleep(9500);
    const smp = await page.evaluate(() => window.__s); const v = smp.map((x) => x[1]);
    let maxStep = 0; for (let i = 1; i < v.length; i++) maxStep = Math.max(maxStep, Math.abs(v[i] - v[i - 1]));
    const first = smp.find((x) => x[1] > 0.02)?.[0], done = smp.find((x) => x[1] > 0.99)?.[0];
    // scroll far away and back: it must stay drawn (no replay, no flicker)
    await page.evaluate(() => window.scrollTo(0, 0)); await sleep(1500);
    await page.evaluate(() => window.scrollTo(0, document.getElementById("palm").getBoundingClientRect().top + window.scrollY)); await sleep(1500);
    const after = await page.evaluate(() => { const fr = [...document.querySelectorAll("#palm .frond")]; return fr.reduce((a, e) => a + e.transform.baseVal.consolidate().matrix.a, 0) / fr.length; });
    await page.close();
    return { pinned, dur: done - first, maxStep, final: v.at(-1), after };
  };
  const slow = await measure("slow"); const flick = await measure("flick");
  check("palm: section is not pinned (no pin-spacer)", !slow.pinned && !flick.pinned);
  check("palm: growth takes about the same time whether you arrive by slow scrolling or a hard flick", Math.abs(slow.dur - flick.dur) < 400 && slow.dur > 1000 && slow.dur < 2600, `${Math.round(slow.dur)} ms vs ${Math.round(flick.dur)} ms`);
  check("palm: no frame advances the growth by more than 5%", slow.maxStep <= 0.05 && flick.maxStep <= 0.05, `${(slow.maxStep * 100).toFixed(1)}% / ${(flick.maxStep * 100).toFixed(1)}%`);
  check("palm: fully grown, and stays grown after scrolling away and back", slow.final > 0.98 && flick.final > 0.98 && slow.after > 0.98 && flick.after > 0.98, `${slow.after.toFixed(2)} / ${flick.after.toFixed(2)}`);
  const page = await ctx.newPage(); watch(page, "cursor");
  await page.goto(`${BASE}/`); await sleep(3000);
  const cur = await page.evaluate(() => ({ body: getComputedStyle(document.body).cursor.startsWith("url("), btn: getComputedStyle(document.querySelector("button")).cursor.startsWith("url("), custom: document.body.classList.contains("has-custom-cursor") }));
  check("cursor: body and buttons use the orange arrow image, no custom ring/dot", cur.body && cur.btn && !cur.custom, JSON.stringify(cur));
  await page.goto(`${BASE}/app/contracts/${A}/assistant`); await sleep(2200);
  check("cursor: text fields keep the text caret", (await page.locator("form input").evaluate((e) => getComputedStyle(e).cursor)) === "text");
  await ctx.close();
}

console.log("C10. mobile responsiveness: 6 viewports x 7 routes (overflow, header, tap targets, card tables, menu)");
{
  const VPS = [["320x640", 320, 640], ["360x740", 360, 740], ["390x844", 390, 844], ["430x932", 430, 932], ["768x1024 tablet", 768, 1024], ["740x360 landscape", 740, 360]];
  const ROUTES = [["landing", "/"], ["app home", "/app"], ["terms", `/app/contracts/${A}/terms`], ["penalty", `/app/contracts/${A}/penalty`], ["cashflow", `/app/contracts/${A}/cashflow`], ["assistant", `/app/contracts/${A}/assistant`], ["accuracy", "/app/accuracy"]];
  const probe = () => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    header: [...document.querySelectorAll("[data-testid=topbar] button, [data-testid=topbar] a")].filter((e) => e.getBoundingClientRect().width > 0).filter((e) => { const r = e.getBoundingClientRect(); return r.right > window.innerWidth + 1 || r.left < -1; }).length,
    small: [...document.querySelectorAll("a, button, input, select, summary, [role=tab], [role=slider]")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden" && (r.height < 32 || r.width < 32) && !e.classList.contains("sr-only") && !["file", "checkbox", "range"].includes(e.type); }).length,
    cutOff: [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); if (!(r.width > 0 && r.right > window.innerWidth + 1) || getComputedStyle(e).position === "fixed") return false; for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") return false; } return true; }).length,
    tableScroll: [...document.querySelectorAll("table.rtable")].filter((t) => t.parentElement.scrollWidth > t.parentElement.clientWidth + 1).length,
  });
  const problems = [];
  for (const [vn, w, h] of VPS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
    await ctx.addInitScript(() => { if (!localStorage.getItem("seeded")) { localStorage.setItem("seeded", "1"); localStorage.setItem("spa.reduce", "0"); } });
    for (const [rn, path] of ROUTES) {
      const page = await ctx.newPage(); watch(page, `mobile ${vn} ${rn}`);
      await page.goto(BASE + path); await sleep(rn === "landing" ? 3200 : 2400);
      const m = await page.evaluate(probe);
      const bad = [m.overflow > 1 && `overflow ${m.overflow}px`, m.header && `${m.header} header control(s) off-screen`, m.small && `${m.small} tap target(s) < 32px`, m.cutOff && `${m.cutOff} element(s) cut off`, w <= 640 && m.tableScroll && `${m.tableScroll} table(s) still scroll sideways`].filter(Boolean);
      if (bad.length) problems.push(`${vn} ${rn}: ${bad.join(", ")}`);
      await page.close();
    }
    await ctx.close();
  }
  check("mobile: no overflow, off-screen header controls, tiny tap targets or cut-off elements on any route/viewport", problems.length === 0, problems.slice(0, 6).join(" | "));

  // the menu: open, contents, language switch, escape, navigation
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await ctx.addInitScript(() => { if (!localStorage.getItem("seeded")) { localStorage.setItem("seeded", "1"); localStorage.setItem("spa.reduce", "0"); } });
  const page = await ctx.newPage(); watch(page, "mobile menu");
  await page.goto(`${BASE}/app`); await sleep(2200);
  check("mobile: header shows brand, theme toggle and a menu button only", (await page.locator("[data-testid=topbar] button").count()) === 2 && (await page.getByRole("link", { name: "Accuracy" }).count()) === 0);
  await page.getByTestId("menu-button").click(); await sleep(300);
  check("mobile: menu opens with navigation, language and reduce-effects", await page.getByTestId("menu-panel").isVisible() && await page.getByRole("link", { name: "Accuracy" }).isVisible() && await page.getByRole("button", { name: /Reduce effects/ }).isVisible());
  await page.keyboard.press("Escape"); await sleep(200);
  check("mobile: Escape closes the menu", (await page.getByTestId("menu-panel").count()) === 0);
  await page.getByTestId("menu-button").click(); await page.getByRole("link", { name: "Accuracy" }).click(); await page.waitForURL(/accuracy/, { timeout: 5000 }); await sleep(800);
  check("mobile: choosing a menu link navigates and closes the menu", /accuracy/.test(page.url()) && (await page.getByTestId("menu-panel").count()) === 0);
  await page.getByTestId("menu-button").click(); await page.getByRole("button", { name: "Language" }).click(); await sleep(700);
  check("mobile: language switch from the menu flips the page to RTL", (await page.evaluate(() => document.documentElement.dir)) === "rtl");
  await page.goto(`${BASE}/app/contracts/${A}/terms`); await sleep(2500);
  check("mobile: contracts list is collapsed once a contract is open; tabs form a 2x2 grid", (await page.locator("details.card").first().evaluate((d) => d.open)) === false && (await page.locator(".tabs").evaluate((t) => getComputedStyle(t).display)) === "grid");
  await shot(page, "mobile_ar_terms");
  await ctx.close();
}

console.log("C11. scene framing + frame settling on Windows-like and macOS-like windows; themed scrollbar");
{
  const CONFIGS = [["Windows 1536x730 (125% scaling)", 1536, 730, false], ["Windows 1920x945", 1920, 945, false], ["macOS 1440x780", 1440, 780, true]];
  for (const [name, w, h, mac] of CONFIGS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, userAgent: mac ? "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36" : undefined });
    await ctx.addInitScript((isMac) => { localStorage.setItem("spa.reduce", "0"); if (isMac) Object.defineProperty(navigator, "platform", { get: () => "MacIntel" }); }, mac);
    const page = await ctx.newPage(); watch(page, `frame ${name}`);
    await page.goto(`${BASE}/`); await sleep(4500);
    let startedAt = null, polling = true;
    const poll = (async () => { while (polling) { try { const r = await page.evaluate(() => { const fr = [...document.querySelectorAll("#palm .frond")]; const sc = fr.reduce((a, e) => a + (e.transform.baseVal.numberOfItems ? e.transform.baseVal.consolidate().matrix.a : 1), 0) / fr.length; return { sc, top: document.getElementById("palm").getBoundingClientRect().top }; }); if (startedAt === null && r.sc > 0.02) startedAt = r.top; } catch { /* navigating */ } await sleep(30); } })();
    await page.mouse.move(w / 2, h / 2); await page.mouse.wheel(0, 100); await sleep(90);
    const early = await page.evaluate(() => Math.round(window.scrollY));
    await sleep(6500);
    const read = () => page.evaluate(() => { const r = (q) => { const e = document.querySelector(q); const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom) }; }; const cs = getComputedStyle(document.documentElement); return { palm: r("#palm"), copy: r(".palm-copy"), svg: r(".palm-svg"), sky: r("#skyline"), it: parseFloat(cs.getPropertyValue("--inset-top")), ib: parseFloat(cs.getPropertyValue("--inset-bottom")), vh: innerHeight }; });
    const a = await read();
    await page.mouse.wheel(0, 140); await sleep(3500);
    const c = await read();
    polling = false; await poll;
    check(`${name}: scrolling is free (no teleport on the first wheel tick)`, early < 250, `scrollY ${early}`);
    check(`${name}: scrolling settles with the Palm scene framed at the viewport top`, Math.abs(a.palm.top) <= 3, `top ${a.palm.top}`);
    check(`${name}: Palm text and illustration sit inside the area between header and banner`, a.copy.top >= a.it - 1 && a.svg.top >= a.it - 1 && a.copy.bottom <= a.vh - a.ib + 1 && a.svg.bottom <= a.vh - a.ib + 1, `copy ${a.copy.top}-${a.copy.bottom} svg ${a.svg.top}-${a.svg.bottom} safe ${Math.round(a.it)}-${Math.round(a.vh - a.ib)}`);
    check(`${name}: Palm animation starts only once framed`, startedAt !== null && startedAt <= 0.16 * a.vh, `palm top ${startedAt === null ? "n/a" : Math.round(startedAt)}px at start`);
    check(`${name}: a small further scroll settles on the skyline frame`, Math.abs(c.sky.top) <= 3, `top ${c.sky.top}`);
    await ctx.close();
  }
  for (const theme of ["dusk", "day"]) {
    const ctx = await ctxFor({ theme }); const page = await ctx.newPage(); watch(page, `scrollbar ${theme}`);
    await page.goto(`${BASE}/app/accuracy`); await sleep(2200);
    const sb = await page.evaluate(() => ({ w: getComputedStyle(document.documentElement, "::-webkit-scrollbar").width, r: getComputedStyle(document.documentElement, "::-webkit-scrollbar-thumb").borderRadius, g: getComputedStyle(document.documentElement, "::-webkit-scrollbar-thumb").backgroundImage.startsWith("linear-gradient") }));
    check(`scrollbar (${theme}): themed gradient thumb, rounded, 13px`, sb.w === "13px" && sb.r === "999px" && sb.g, JSON.stringify(sb));
    await ctx.close();
  }
}

// ------------------------------------------------------------------ E. trust and intelligence pages
console.log("E. evidence, gap, probabilistic, obligations, cross-check, playbook, ERP, review, accuracy");
const D = idOf("sample_d_rera.pdf"), RV = idOf("fixture_review_case.pdf");
const num = (t) => Number(String(t).replace(/[^0-9.\-]/g, ""));
const get = async (path) => (await fetch(`${BASE}/api${path}`)).json();
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "trust EN");
  // --- E1 evidence highlight + grounding chips + currency + jurisdiction
  await page.goto(`${BASE}/app/contracts/${D}/terms`); await sleep(2600);
  check("E1 terms(D): amounts are shown in INR, not AED", /INR\s*8,450,000/.test(await page.getByTestId("value-price").innerText()), await page.getByTestId("value-price").innerText());
  const chips = await page.getByTestId("grounding-chip").evaluateAll((els) => els.map((e) => e.dataset.status));
  check("E1 terms(D): every extracted field carries a grounding chip (grounded or not stated)", chips.length >= 10 && chips.every((c) => ["grounded", "not_stated"].includes(c)), chips.join());
  check("E1 terms(D): jurisdiction detected as India (RERA) with its evidence", /in_rera|India/.test(await page.locator("#jur option:checked").innerText()) || /in_rera/.test(await page.locator("#jur").evaluate((e) => e.options[0].text)));
  await page.getByTestId("row-price").getByRole("button").first().click();
  await page.getByTestId("highlight").first().waitFor({ timeout: 8000 }).then(() => check("E1: clicking a field's page opens the PDF with the exact span highlighted", true)).catch(() => check("E1: clicking a field's page opens the PDF with the exact span highlighted", false));
  const hb = await page.getByTestId("highlight").first().boundingBox();
  const vb = await page.getByTestId("page-viewer").boundingBox();
  check("E1: highlight box sits inside the rendered page", hb && vb && hb.width > 20 && hb.height > 5, JSON.stringify(hb));
  await shot(page, "trust_evidence_highlight_D");
  await page.goto(`${BASE}/app/contracts/${D}/terms`); await sleep(1800);
  await page.getByTestId("value-price").scrollIntoViewIfNeeded();

  // --- E2 statute gap
  const gapApi = await post(`/contracts/${D}/statute-gap`, { delay_days: 180, as_of_date: "2026-12-31" });
  await page.goto(`${BASE}/app/contracts/${D}/gap`); await sleep(3000);
  const uiStat = num(await page.getByTestId("gap-statute").innerText()), uiCon = num(await page.getByTestId("gap-contract").innerText()), uiGap = num(await page.getByTestId("gap-shortfall").innerText());
  check("E2 gap(D): statutory amount equals the API value exactly", Math.abs(uiStat - gapApi.statutory.amount) < 0.005, `${uiStat} vs ${gapApi.statutory.amount}`);
  check("E2 gap(D): contractual amount equals the API value exactly", Math.abs(uiCon - gapApi.contractual.penalty) < 0.005, `${uiCon} vs ${gapApi.contractual.penalty}`);
  check("E2 gap(D): shortfall counter settles exactly on statutory - contractual", Math.abs(uiGap - gapApi.shortfall) < 0.005 && Math.abs(uiGap - (uiStat - uiCon)) < 0.011, `${uiGap}`);
  check("E2 gap(D): unreviewed-legal-logic badge and illustrative-rate warning are shown", (await page.getByTestId("unreviewed-badge").count()) >= 1 && await page.getByTestId("illustrative-rates").isVisible());
  check("E2 gap(D): input table lists inputs with evidence links", (await page.getByTestId("gap-inputs").locator("tr").count()) >= 8 && (await page.getByTestId("gap-inputs").getByTestId("evidence-link").count()) >= 4);
  check("E2 gap(D): findings flag the one-sided clause with severity", (await page.getByTestId("gap-findings").locator("li").count()) >= 1);
  await page.getByTestId("gap-inputs").getByTestId("evidence-link").first().click(); await page.getByTestId("highlight").first().waitFor({ timeout: 8000 }).then(() => check("E2 gap(D): an input's evidence link opens the highlighted PDF span", true)).catch(() => check("E2 gap(D): an input's evidence link opens the highlighted PDF span", false));
  await shot(page, "trust_gap_D");
  await page.getByTestId("gap-days").fill("0"); await sleep(1200);
  check("E2 gap(D): zero delay gives a zero shortfall", num(await page.getByTestId("gap-shortfall").innerText()) === 0);
  await page.goto(`${BASE}/app/contracts/${A}/gap`); await sleep(2600);
  check("E2 gap(A, Dubai): clear 'cannot compute' reason and badge, no invented number", await page.getByTestId("gap-cannot").isVisible() && (await page.getByTestId("gap-shortfall").count()) === 0 && (await page.getByTestId("unreviewed-badge").count()) >= 1);
  await shot(page, "trust_gap_A_cannot");

  // --- E3 probabilistic view
  await page.goto(`${BASE}/app/contracts/${D}/penalty`); await sleep(3500);
  check("E3 penalty(D): probabilistic view is labelled assumption-driven", await page.getByTestId("mc-assumption").isVisible() && /not a prediction/i.test(await page.getByTestId("mc").innerText()));
  await page.getByTestId("mc-family").selectOption("fixed"); await page.getByTestId("mc-days").fill("180"); await page.getByTestId("mc-run").click(); await sleep(2500);
  const mcRows = await page.getByTestId("mc-table").locator("tbody tr").allInnerTexts();
  const stat50 = num(mcRows.find((r) => /Statutory/.test(r)).split("\t")[2]);
  check("E3 penalty(D): fixed 180-day distribution reproduces the deterministic statutory amount", Math.abs(stat50 - gapApi.statutory.amount) < 0.005, `${stat50} vs ${gapApi.statutory.amount}`);
  check("E3: probabilities shown", /%/.test(await page.getByTestId("mc-pgrace").innerText()));
  await page.getByTestId("mc-family").selectOption("triangular"); await page.getByTestId("mc-run").click(); await sleep(2500);
  const t1 = await page.getByTestId("mc-table").innerText(); await page.getByTestId("mc-run").click(); await sleep(2000);
  check("E3: same seed gives the same table (reproducible)", t1 === (await page.getByTestId("mc-table").innerText()));
  await page.getByTestId("mc-portfolio").click(); await page.getByTestId("mc-portfolio-table").waitFor({ timeout: 10000 });
  const totals = await page.getByTestId("mc-total").allInnerTexts();
  check("E3: portfolio rollup keeps currencies separate (AED and INR rows)", totals.some((x) => /AED/.test(x)) && totals.some((x) => /INR/.test(x)), totals.join("|"));
  await shot(page, "trust_montecarlo_D", true);

  // --- E4 obligations
  await page.goto(`${BASE}/app/watch`); await sleep(2200);
  await page.getByTestId("obl-asof").fill("2025-03-10"); await sleep(1500);
  await page.getByRole("button", { name: "Recompute alerts" }).click(); await sleep(1500);
  const n0 = await page.getByTestId("alert").count();
  check("E4 watch: alerts feed lists due-soon items (in-app only)", n0 >= 1 && /In-app feed only/.test(await page.locator("body").innerText()), `${n0} alerts`);
  check("E4 watch: timeline and obligation rows are visible", await page.getByTestId("obl-timeline").isVisible() && (await page.getByTestId("obl-row").count()) >= 5);
  await page.getByTestId("ack").first().click(); await sleep(1200);
  check("E4 watch: acknowledging removes the alert from the feed", (await page.getByTestId("alert").count()) === n0 - 1, `${n0} -> ${await page.getByTestId("alert").count()}`);
  await page.getByTestId("obl-status").selectOption("due_soon"); await sleep(1200);
  check("E4 watch: event filter narrows the table", (await page.getByTestId("obl-row").evaluateAll((r) => r.every((x) => x.dataset.event === "due_soon"))));
  await shot(page, "trust_watch");
  await page.goto(`${BASE}/app/contracts/${A}/obligations`); await sleep(2600);
  check("E4 per-contract: calendar view and evidence links", await page.getByTestId("obl-calendar").isVisible() && (await page.getByTestId("evidence-link").count()) >= 1);

  // --- E5 cross-document check
  await page.goto(`${BASE}/app/crosscheck`); await sleep(2500);
  check("E5 cross-check: sample set labelled synthetic", await page.getByTestId("cross-synthetic").isVisible());
  await page.getByTestId("cross-read").click(); await page.getByTestId("conflict").first().waitFor({ timeout: 15000 }).catch(() => {});
  await sleep(800);
  check("E5 cross-check set_1: both planted conflicts found (price, handover)", (await page.getByTestId("conflict").count()) === 2, `${await page.getByTestId("conflict").count()}`);
  check("E5 cross-check: planted-error precision and recall are shown (1.00 / 1.00)", /precision 1\.00, recall 1\.00/.test(await page.getByTestId("cross-score").innerText()));
  check("E5 cross-check: graph draws conflict edges in the alert colour", (await page.getByTestId("conflict-edge").count()) >= 1 && (await page.getByTestId("graph-doc").count()) === 4);
  await page.getByTestId("conflict").first().click(); await sleep(1500);
  check("E5 cross-check: clicking a conflict shows two documents side by side", (await page.getByTestId("side-doc").count()) === 2);
  await page.getByTestId("highlight").first().waitFor({ timeout: 8000 }).then(() => check("E5 cross-check: the conflicting value is highlighted in the PDF", true)).catch(() => check("E5 cross-check: the conflicting value is highlighted in the PDF", false));
  await shot(page, "trust_crosscheck", true);

  // --- E6 playbook
  await page.goto(`${BASE}/app/contracts/${C}/playbook`); await sleep(2800);
  check("E6 playbook(C): flagged as example content, internal view", await page.getByTestId("pb-example").isVisible());
  const sumFail = page.locator("[data-testid=pb-card]", { hasText: "Payment plan sums to 100%" });
  check("E6 playbook(C): the 95% plan fails with an approved-clause redline", /Fail/.test(await sumFail.innerText()) && (await sumFail.getByTestId("redline").count()) === 1);
  check("E6 playbook: qualitative rules are 'not run' until the specialist LLM is invoked", /not run:\s*6/i.test(await page.getByTestId("pb-summary").innerText()));
  await page.getByTestId("pb-run").click(); await sleep(2500);
  check("E6 playbook: running the clause specialists grounds and fills the qualitative rules", !/not run:\s*[1-9]/i.test(await page.getByTestId("pb-summary").innerText()));
  await shot(page, "trust_playbook_C", true);

  // --- E7 ERP
  await page.goto(`${BASE}/app/contracts/${A}/erp`); await sleep(2200);
  check("E7 erp: placeholder warning is visible", await page.getByTestId("erp-placeholder").isVisible());
  await page.getByTestId("erp-preview").click(); await page.getByTestId("erp-table").waitFor({ timeout: 8000 });
  check("E7 erp: dry-run preview has rows and validates", (await page.getByTestId("erp-table").locator("tbody tr").count()) >= 5 && /Valid/.test(await page.getByTestId("erp-valid").innerText()));
  const dl = page.waitForEvent("download"); await page.getByTestId("erp-csv").click(); const file = await dl;
  check("E7 erp: CSV downloads", /\.csv$/.test(file.suggestedFilename()));
  await page.getByTestId("erp-push").click(); await page.getByTestId("erp-confirm-check").check(); await page.getByTestId("erp-confirm-push").click(); await sleep(1200);
  check("E7 erp: live push is refused while disabled, with a clear reason (after an explicit confirmation step)", /disabled/i.test(await page.getByTestId("erp-push-error").innerText()));
  await shot(page, "trust_erp_A");

  // --- E8 review queue
  await page.goto(`${BASE}/app/review`); await sleep(2200);
  check("E8 review: the partially-grounded price is queued", (await page.locator("[data-testid=review-item][data-field=price]").count()) === 1);
  await page.getByTestId("rv-correct").click(); await page.getByTestId("rv-value").fill("1250000"); await page.getByTestId("rv-save").click(); await sleep(1500);
  check("E8 review: after a correction the item leaves the queue", (await page.locator("[data-testid=review-item][data-field=price]").count()) === 0);
  await page.goto(`${BASE}/app/contracts/${RV}/terms`); await sleep(2400);
  check("E8 review: the corrected field shows as human verified", (await page.getByTestId("row-price").getByTestId("grounding-chip").getAttribute("data-status")) === "human");
  const hist = await get(`/contracts/${RV}/reviews`);
  check("E8 review: the decision is stored with a timestamp", hist.decisions.length === 1 && !!hist.decisions[0].at);

  // --- E9 accuracy
  await page.goto(`${BASE}/app/accuracy`); await sleep(2400);
  check("E9 accuracy: states the golden-set size and that no real documents exist yet", /4 documents \(4 synthetic, 0 real\)|No evaluation run yet/.test(await page.getByTestId("golden-note").innerText()) && /say nothing|No real documents/.test(await page.getByTestId("golden-note").innerText()));
  await page.getByTestId("acc-run").click(); await page.getByTestId("run-row").first().waitFor({ timeout: 15000 });
  await sleep(1500);
  check("E9 accuracy: a run appears in the history, labelled as a test stub", (await page.getByTestId("run-row").count()) >= 1 && (await page.getByTestId("stub-badge").count()) >= 1);
  await page.getByTestId("acc-run").click(); await sleep(3500);
  check("E9 accuracy: a second run is compared with the first (history grows)", (await page.getByTestId("run-row").count()) >= 2);
  await page.getByTestId("acc-tab-engines").click(); await sleep(1500);
  const rows = await page.getByTestId("bake-row").allInnerTexts();
  check("E9 engines: unconfigured engines are reported 'not configured', never faked", rows.some((r) => /azure_docint/.test(r) && /not configured/.test(r)) && rows.some((r) => /docling/.test(r) && /not configured/.test(r)));
  check("E9 engines: comparison states that results apply only to our golden set", /only to our golden set/.test(await page.getByTestId("bake-note").innerText()));
  await shot(page, "trust_accuracy_engines");
  await ctx.close();
}

// every new page for all samples, EN and AR: loads, shows the disclaimer, no console errors (checked at the end)
for (const lang of ["en", "ar"]) {
  const ctx = await ctxFor({ lang }); const page = await ctx.newPage(); watch(page, `trust pages ${lang}`);
  for (const [name, id] of [["a", A], ["b", B], ["c", C], ["d", D]]) for (const tab of ["gap", "obligations", "playbook", "erp"]) {
    await page.goto(`${BASE}/app/contracts/${id}/${tab}`); await sleep(2300);
    check(`new page ${lang} ${name}/${tab}: renders`, await page.locator("h2").first().isVisible() && (await page.locator("[role=alert]:has-text('Something went wrong')").count()) === 0);
    await disclaimer(page, `new page ${lang} ${name}/${tab}`);
    if (name === "d" || name === "a") await shot(page, `trust_${lang}_${name}_${tab}`);
  }
  for (const route of ["watch", "crosscheck", "review", "accuracy"]) {
    await page.goto(`${BASE}/app/${route}`); await sleep(2300);
    check(`new page ${lang} ${route}: renders`, await page.locator("h1, h2").first().isVisible());
    await disclaimer(page, `new page ${lang} ${route}`);
    await shot(page, `trust_${lang}_${route}`);
  }
  if (lang === "ar") check("AR: native-review note is shown", await page.getByTestId("ar-review").isVisible());
  await ctx.close();
}

// ------------------------------------------------------------------ D. FPS (software-rendered headless: indicative only)
console.log("D. frame-rate probe on the landing page");
{
  const ctx = await ctxFor(); const page = await ctx.newPage(); watch(page, "fps");
  await page.goto(`${BASE}/`); await sleep(4500);
  const fps = await page.evaluate(async () => {
    const H = document.documentElement.scrollHeight - innerHeight; let frames = 0; const t0 = performance.now();
    await new Promise((res) => { const tick = (t) => { frames++; const p = Math.min(1, (t - t0) / 6000); scrollTo(0, p * H); p < 1 ? requestAnimationFrame(tick) : res(); }; requestAnimationFrame(tick); });
    return frames / ((performance.now() - t0) / 1000);
  });
  console.log(`  landing scroll probe: ${fps.toFixed(1)} fps (headless, software GL, no GPU)`); results.push({ name: "fps probe (informational)", ok: true, detail: `${fps.toFixed(1)} fps` });
  await ctx.close();
}

await browser.close();

// ------------------------------------------------------------------ summary
// the deliberate fake-PDF upload (step C5) makes the server answer 415 on purpose; the browser logs it as a resource error
const real = consoleErrors.filter((e) => !/GL Driver|GPU stall/.test(e) && !(e.startsWith("misc:") && /415/.test(e)) && !(e.startsWith("trust EN:") && /409/.test(e)));
check("no console errors or page errors anywhere", real.length === 0, real.slice(0, 5).join(" || "));
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) { console.log("FAILED:"); failed.forEach((f) => console.log(` - ${f.name} ${f.detail}`)); }
fs.writeFileSync("docs/e2e-results.json", JSON.stringify({ passed: results.length - failed.length, total: results.length, failed, results }, null, 2));
process.exit(failed.length ? 1 : 0);

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
  check("chat: PDF opened at page 3", /#page=3/.test((await panel.locator("iframe").getAttribute("src")) ?? ""));
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
  check("accuracy: shows API results", /\d+(\.\d)?%/.test(await page.getByTestId("acc-values").innerText()) && (await page.getByTestId("acc-row").count()) >= 10);
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
const real = consoleErrors.filter((e) => !/GL Driver|GPU stall/.test(e) && !(e.startsWith("misc:") && /415/.test(e)));
check("no console errors or page errors anywhere", real.length === 0, real.slice(0, 5).join(" || "));
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) { console.log("FAILED:"); failed.forEach((f) => console.log(` - ${f.name} ${f.detail}`)); }
fs.writeFileSync("docs/e2e-results.json", JSON.stringify({ passed: results.length - failed.length, total: results.length, failed, results }, null, 2));
process.exit(failed.length ? 1 : 0);

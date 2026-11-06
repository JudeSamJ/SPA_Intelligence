// Records a Playwright video of the landing page scroll (for demos). Output: docs/landing-scroll.webm (+ .gif via ffmpeg).
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const BASE = process.env.BASE ?? "http://127.0.0.1:8000";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: "docs/.video", size: { width: 1280, height: 720 } } });
await ctx.addInitScript(() => { localStorage.setItem("spa.reduce", "0"); localStorage.setItem("spa.theme", "dusk"); localStorage.setItem("spa.lang", "en"); });
const page = await ctx.newPage();
await page.goto(BASE); await sleep(4500);               // hero intro: split-text, scramble, dhow, glitch burst
await page.mouse.move(640, 360);
for (let i = 0; i < 70; i++) { await page.mouse.move(300 + i * 9, 300 + Math.sin(i / 5) * 90); await page.mouse.wheel(0, 150); await sleep(260); }
await sleep(1200);
await page.getByRole("button", { name: "Open the app" }).last().click();   // sandstorm route transition
await sleep(3200);
await page.close(); await ctx.close(); await browser.close();
const f = fs.readdirSync("docs/.video").find((x) => x.endsWith(".webm"));
fs.renameSync(`docs/.video/${f}`, "docs/landing-scroll.webm"); fs.rmdirSync("docs/.video");
console.log("wrote docs/landing-scroll.webm");

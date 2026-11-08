const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await p.goto('http://localhost:8124/app', { waitUntil: 'networkidle' }); await p.waitForTimeout(1000);
  await p.locator('input[type=file]').setInputFiles('/tmp/scan2.pdf');
  const seen = []; const t0 = Date.now();
  while (Date.now() - t0 < 60000) {
    const card = p.locator('[data-flip-id]', { hasText: 'scan2.pdf' }).first();
    const txt = await card.innerText().catch(() => '');
    const m = ['Reading scanned pages', 'Queued', 'Extracting', 'Extracted', 'Failed'].find(s => txt.includes(s));
    if (m && seen[seen.length - 1] !== m) seen.push(m);
    if (m === 'Extracted' || m === 'Failed') break;
    await p.waitForTimeout(150);
  }
  console.log('status chip sequence:', seen.join(' -> '));
  console.log(seen.includes('Reading scanned pages') ? 'PASS  the UI shows "Reading scanned pages…" while OCR runs' : 'FAIL  OCR state never shown');
  await p.waitForTimeout(1500);
  // open a value's page chip to see the highlight on the scanned page
  const row = p.locator('tr', { hasText: 'Handover' }).first();
  await row.getByRole('button').first().click().catch(() => {});
  await p.waitForTimeout(3500);
  await p.screenshot({ path: '/tmp/ocr_highlight.png' });
  await b.close();
})();

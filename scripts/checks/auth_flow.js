const { chromium } = require('playwright');
const BASE = 'http://localhost:8000';
const PW = 'correct-horse-battery';
const ok = (n, c, d = '') => console.log(`${c ? 'PASS' : 'FAIL'}  ${n} ${d}`);
async function login(page, email) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PW);
  await page.getByTestId('email-submit').click();
}
(async () => {
  const b = await chromium.launch();
  const errs = [];
  const mk = async (name) => { const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } }); const p = await ctx.newPage(); p.on('pageerror', e => errs.push(name + ': ' + e.message)); p.on('console', m => { if (m.type() === 'error' && !/40[13]|409/.test(m.text())) errs.push(name + ': ' + m.text().slice(0, 140)); }); return p; };

  // 1. anonymous visit to /app lands on the login page with the email form
  const anon = await mk('anon');
  await anon.goto(`${BASE}/app`, { waitUntil: 'networkidle' }); await anon.waitForTimeout(1500);
  ok('anonymous /app redirects to /login', anon.url().includes('/login'));
  ok('email form shown', await anon.getByTestId('email-form').isVisible());
  await anon.screenshot({ path: '/tmp/a_login.png' });
  // wrong password
  await anon.getByLabel('Email').fill('rita@co.com'); await anon.getByLabel('Password').fill('wrong-wrong-wrong'); await anon.getByTestId('email-submit').click();
  await anon.getByTestId('email-error').waitFor(); ok('wrong password shows an error', /not correct/.test(await anon.getByTestId('email-error').innerText()));

  // 2. rita (no role) signs in: waiting page, no data
  const rita = await mk('rita');
  await login(rita, 'rita@co.com'); await rita.getByTestId('pending-page').waitFor();
  ok('new user sees the waiting page', true); await rita.screenshot({ path: '/tmp/a_pending.png' });
  const r403 = await rita.evaluate(async () => (await fetch('/api/contracts')).status);
  ok('pending user gets 403 from the API', r403 === 403, String(r403));

  // 3. admin signs in, sees Users, approves rita as staff and links bella as a buyer
  const boss = await mk('boss');
  await login(boss, 'boss@co.com'); await boss.waitForURL(/\/app/); await boss.waitForTimeout(1500);
  ok('admin sees Users, Review and Buyers links', await boss.getByRole('link', { name: 'Users' }).first().isVisible() && await boss.getByRole('link', { name: 'Buyers' }).first().isVisible());
  await boss.getByRole('link', { name: 'Users' }).first().click(); await boss.getByTestId('user-row').first().waitFor();
  await boss.screenshot({ path: '/tmp/a_users.png' });
  await boss.getByLabel('Role for rita@co.com').selectOption('staff'); await boss.waitForTimeout(800);
  ok('rita now has the staff role in the list', (await boss.getByLabel('Role for rita@co.com').inputValue()) === 'staff');
  await boss.getByRole('link', { name: 'Buyers' }).first().click(); await boss.getByTestId('buyer-form').waitFor();
  await boss.getByTestId('buyer-form').locator('select').first().selectOption({ index: 0 });
  await boss.getByTestId('buyer-form').getByLabel('Email or phone').fill('bella@buyer.com'); await boss.getByTestId('buyer-add').click(); await boss.getByTestId('buyer-row').waitFor();
  ok('buyer linked to a contract', /bella@buyer.com/.test(await boss.getByTestId('buyer-row').first().innerText()));

  // 4. rita (now staff) reloads: app opens, but no Review/Buyers/Users links, and writes are refused
  await rita.reload({ waitUntil: 'networkidle' }); await rita.waitForTimeout(1500);
  ok('staff sees the app', !(await rita.getByTestId('pending-page').count()));
  ok('staff has no Review, Buyers or Users links', (await rita.getByRole('link', { name: 'Buyers' }).count()) === 0 && (await rita.getByRole('link', { name: 'Users' }).count()) === 0 && (await rita.getByRole('link', { name: 'Review queue' }).count()) === 0);
  const w = await rita.evaluate(async () => (await fetch('/api/buyers', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'spa' }, body: JSON.stringify({ contract_id: 'a'.repeat(64), identity: 'x@y.co' }) })).status);
  ok('staff cannot change data (403)', w === 403, String(w));
  await rita.screenshot({ path: '/tmp/a_staff.png' });

  // 5. bella (buyer) signs in: only her contract chat
  const bella = await mk('bella');
  await login(bella, 'bella@buyer.com'); await bella.getByTestId('buyer-home').waitFor();
  ok('buyer lands on the contract chat', true);
  ok('buyer sees no staff navigation', (await bella.getByRole('link', { name: 'Obligations' }).count()) === 0 && (await bella.getByRole('link', { name: 'Review queue' }).count()) === 0);
  await bella.getByLabel('Ask about your contract').fill('Can I cancel and get a refund?'); await bella.getByRole('button', { name: 'Send' }).click();
  await bella.getByTestId('msg-refused').waitFor(); ok('legal question is referred to the legal team', /legal team/.test(await bella.getByTestId('msg-refused').innerText()));
  await bella.getByLabel('Ask about your contract').fill('When is my handover date?'); await bella.getByRole('button', { name: 'Send' }).click();
  await bella.getByTestId('msg-assistant').waitFor({ timeout: 15000 }); const ans = await bella.getByTestId('msg-assistant').innerText(); ok('buyer gets a cited answer', /page|p\.|\bp\b/i.test(ans) || /2027/.test(ans), ans.slice(0, 80).replace(/\n/g, ' '));
  await bella.screenshot({ path: '/tmp/a_buyer.png' });
  const b403 = await bella.evaluate(async () => [(await fetch('/api/contracts')).status, (await fetch('/api/users')).status, (await fetch('/api/buyers')).status]);
  ok('buyer is refused every staff API', b403.every(s => s === 403), b403.join(','));

  // 6. removing rita's role takes effect on her very next request
  await boss.getByRole('link', { name: 'Users' }).first().click(); await boss.getByTestId('user-row').first().waitFor();
  await boss.getByLabel('Role for rita@co.com').selectOption(''); await boss.waitForTimeout(800);
  const after = await rita.evaluate(async () => (await fetch('/api/contracts')).status);
  ok('removing a role cuts access at once', after === 403, String(after));

  // 7. sign out
  await boss.getByTestId('user-menu-button').click(); await boss.getByTestId('sign-out').click(); await boss.waitForURL(/login/);
  ok('sign out returns to the login page', true);
  console.log('console/page errors:', errs.length ? errs : 'none');
  await b.close();
})().catch(e => { console.error('SCRIPT ERROR', e.message); process.exit(1); });

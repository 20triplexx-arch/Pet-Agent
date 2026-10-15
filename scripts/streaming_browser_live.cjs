// Synthetic data only. The server installs the shared free-only test budget.
const { chromium, devices } = require('../frontend/node_modules/@playwright/test');
const fs = require('fs');
const path = require('path');
async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const kind of ['desktop', 'mobile']) {
      const context = await browser.newContext(kind === 'mobile' ? { ...devices['iPhone 13'], defaultBrowserType: undefined } : { viewport: { width: 1440, height: 1000 } });
      const page = await context.newPage();
      const login = await page.request.post('http://127.0.0.1:8013/api/v1/login/access-token', { form: { username: 'synthetic-eval@example.com', password: 'SyntheticEval2026!' } });
      const token = (await login.json()).access_token;
      if (!token) throw new Error('Synthetic login failed');
      await page.addInitScript(t => sessionStorage.setItem('chongban_token', t), token);
      await page.goto('http://127.0.0.1:8013/chat');
      await page.getByLabel('模型选择').selectOption('alibaba');
      for (const depth of ['brief', 'detailed']) {
        if (depth === 'detailed') await page.getByRole('button', { name: '新对话', exact: true }).click();
        await page.getByRole('button', { name: '补充资料', exact: true }).click();
        await page.getByLabel('回答深度').selectOption(depth);
        await page.getByRole('button', { name: '回到提问', exact: true }).click();
        await page.getByLabel('提问内容').fill(depth === 'brief' ? '猫不愿进航空箱，平时如何练习？' : '猫抓沙发怎么办？请深入说明选择依据、适用条件、执行步骤和如何观察进展。');
        await page.evaluate(() => {
          window.__chatTimes = { start: performance.now() };
          window.__chatObserver = new MutationObserver(() => {
            const t = window.__chatTimes;
            if (!t.first && document.querySelector('.generating .answer-section')) t.first = performance.now()-t.start;
          });
          window.__chatObserver.observe(document.body, { subtree: true, childList: true, characterData: true });
        });
        const before = await page.locator('.message.assistant:not(.generating)').count();
        const response = page.waitForResponse(r => r.url().endsWith('/api/v1/chat/stream') && r.request().method() === 'POST');
        await page.getByRole('button', { name: '发送', exact: true }).click();
        await response;
        await page.locator('.generating').waitFor({ state: 'detached', timeout: 60000 });
        const timing = await page.evaluate(() => { window.__chatObserver.disconnect(); return { first_ms: window.__chatTimes.first || null, complete_ms: performance.now()-window.__chatTimes.start }; });
        const final = await page.locator('.message.assistant:not(.generating)').count() > before;
        const record = { kind, depth, ...timing, final, status: final ? 200 : 'application_error' };
        results.push(record);
        await page.screenshot({ path: path.join(__dirname, '..', '.impeccable/review', `chat-stream-live-${kind}-${depth}.png`), fullPage: false });
      }
      await context.close();
    }
  } finally {
    await browser.close();
    const session = JSON.parse(fs.readFileSync(path.join(__dirname, '../artifacts/streaming-browser-live-session.json')));
    fs.writeFileSync(path.join(__dirname, '../artifacts/streaming-browser-live-result.json'), JSON.stringify({ synthetic: true, model: session.model, results }, null, 2));
  }
  if (results.length !== 4 || results.some(r => !r.final)) process.exitCode = 1;
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });

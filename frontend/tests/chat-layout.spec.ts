import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page) {
  const email = `layout-${crypto.randomUUID()}@example.com`, password = crypto.randomUUID();
  await page.request.post('/api/v1/users/signup', { data: { email, password } });
  const login = await page.request.post('/api/v1/login/access-token', { form: { username: email, password } });
  const token = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}`, 'Idempotency-Key': crypto.randomUUID() };
  const pet = await (await page.request.post('/api/v1/pets', { headers, data: { name: '滚动验收猫', species: 'cat', estimated_age_months: 24 } })).json();
  await page.addInitScript(value => { sessionStorage.setItem('chongban_token', value.token); sessionStorage.setItem('chongban_pet', value.pet); }, { token, pet: pet.id });
  return { headers, pet };
}

test('unread paragraphs and final survive history refresh while reading older messages', async ({ page }) => {
  const { headers, pet } = await setup(page);
  let conversation: string | null = null;
  for (const text of ['猫抓沙发怎么办？', '猫到家准备什么？', '猫刷牙如何开始？', '猫日常清洁怎么安排？']) {
    const answer = await page.request.post('/api/v1/chat', { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data: { pet_id: pet.id, conversation_id: conversation, text } });
    expect(answer.ok()).toBeTruthy();
    conversation = (await answer.json()).conversation_id;
  }
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input) !== '/api/v1/chat/stream') return original(input, init);
      const encoder = new TextEncoder();
      return new Response(new ReadableStream({ start(controller) {
        (window as unknown as { deliver: (event: string, data: unknown) => void }).deliver = (event, data) => {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
          if (event === 'final') controller.close();
        };
        controller.enqueue(encoder.encode('event: accepted\ndata: {}\n\n'));
      } }), { headers: { 'content-type': 'text/event-stream' } });
    };
  });
  await page.goto('/chat');
  await expect(page.locator('.message')).toHaveCount(8);
  await page.getByLabel('提问内容').fill('猫抓沙发如何调整？');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.locator('.generating')).toBeVisible();
  const messages = page.locator('.messages');
  const scrollUp = async () => {
    await messages.evaluate(el => { el.scrollTo({ top: 0, behavior: 'instant' }); el.dispatchEvent(new Event('scroll')); });
    await expect.poll(() => messages.evaluate(el => el.scrollTop)).toBeLessThan(1);
  };
  await scrollUp();
  await page.evaluate(() => (window as unknown as { deliver: (e: string, d: unknown) => void }).deliver('section', { index: 0, text: '先提供稳定的替代抓挠位置。', sources: [], question_ids: [1] }));
  const latest = page.getByRole('button', { name: '查看最新回复', exact: true });
  await expect(latest).toBeVisible();
  expect(await messages.evaluate(el => el.scrollTop)).toBeLessThan(1);
  await latest.click();
  await expect(latest).toHaveCount(0);
  await page.evaluate(() => (window as unknown as { deliver: (e: string, d: unknown) => void }).deliver('section', { index: 1, text: '观察是否主动使用替代抓挠位置。'.repeat(30), sources: [], question_ids: [1] }));
  await expect(page.locator('.answer-section')).toHaveCount(2);
  await page.evaluate(() => (window as unknown as { deliver: (e: string, d: unknown) => void }).deliver('section', { index: 2, text: '结合反应继续调整。', sources: [], question_ids: [1] }));
  await expect(page.locator('.answer-section')).toHaveCount(3);
  await expect(latest).toHaveCount(0);
  await scrollUp();
  const final = await (await page.request.post('/api/v1/chat', { headers: { ...headers, 'Idempotency-Key': crypto.randomUUID() }, data: { pet_id: pet.id, conversation_id: conversation, text: '猫抓沙发如何调整？' } })).json();
  const refreshed = page.waitForResponse(response => response.url().endsWith(`/conversations/${conversation}/messages`) && response.request().method() === 'GET');
  await page.evaluate(value => (window as unknown as { deliver: (e: string, d: unknown) => void }).deliver('final', value), final);
  await refreshed;
  await expect(page.locator('.generating')).toHaveCount(0);
  await expect(page.locator('.message')).toHaveCount(10);
  await expect(latest).toBeVisible();
  expect(await messages.evaluate(el => el.scrollTop)).toBeLessThan(1);
  await latest.click();
  await expect(latest).toHaveCount(0);
});

test('composer and stop stay above navigation at short and tall viewports', async ({ page }, info) => {
  await setup(page);
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input) !== '/api/v1/chat/stream') return original(input, init);
      const encoder = new TextEncoder();
      return new Response(new ReadableStream({ start(controller) {
        controller.enqueue(encoder.encode('event: accepted\ndata: {}\n\n'));
        init?.signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')));
      } }), { headers: { 'content-type': 'text/event-stream' } });
    };
  });
  for (const viewport of [{ width: 390, height: 664 }, { width: 390, height: 844 }, { width: 1280, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/chat');
    await expect(page.getByLabel('模型选择')).toBeEnabled();
    await page.evaluate(() => document.fonts.ready);
    const send = await page.getByRole('button', { name: '发送', exact: true }).boundingBox();
    expect(send!.y + send!.height).toBeLessThanOrEqual(viewport.height - (viewport.width < 768 ? 72 : 0));
    expect((await page.locator('.messages').boundingBox())!.height).toBeGreaterThan(40);
    await expect(page.getByLabel('提问内容')).toBeInViewport();
    await page.getByLabel('提问内容').fill('猫抓沙发怎么办？');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    const stop = page.getByRole('button', { name: '停止生成', exact: true });
    await expect(stop).toBeInViewport();
    const bounds = await stop.boundingBox();
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height - (viewport.width < 768 ? 72 : 0));
    const messageBounds = (await page.locator('.messages').boundingBox())!;
    expect(bounds!.y).toBeGreaterThanOrEqual(messageBounds.y);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(messageBounds.y + messageBounds.height);
    const busySend = (await page.getByRole('button', { name: '发送', exact: true }).boundingBox())!;
    expect(busySend.y + busySend.height).toBeLessThanOrEqual(viewport.height - (viewport.width < 768 ? 72 : 0));
    await page.screenshot({ path: info.outputPath(`composer-${viewport.width}-${viewport.height}.png`) });
    await stop.click();
    await expect(page.locator('.generating')).toHaveCount(0);
  }
});

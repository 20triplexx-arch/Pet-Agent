import { test, expect } from "@playwright/test";

const options = [
  { id: "demo", name: "本地演示", label: "演示模式 · 本地", provider: null, available: true, mode: "demo" },
  { id: "alibaba", name: "qwen3.7-flash", label: "阿里千问 · qwen3.7-flash", provider: "alibaba", available: true, mode: "live" },
  { id: "deepseek", name: "deepseek-flash", label: "DeepSeek · deepseek-flash", provider: "deepseek", available: true, mode: "live" },
];

test("Alibaba default, full validated reply, depth and sources", async ({ page }) => {
  const login = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await login.json()).access_token);
  await page.route("**/api/v1/chat/models", route => route.fulfill({ json: { default_id: "alibaba", options } }));
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/v1/chat{,/stream}", route => {
    requests.push(route.request().postDataJSON());
    const metadata = { mode: "live", model_used: "qwen3.7-flash", sources: [{ id: "cat-scratching", title: "猫的抓挠行为", url: "https://icatcare.org/advice/", organization: "iCatCare", sections: ["适用条件"], evidence: [{ heading: "适用条件", text: "提供稳定的替代抓挠位置，观察实际反应。" }] }] };
    return route.fulfill({ json: { conversation_id: "alibaba-fixture", answer: "先提供稳定的替代抓挠位置，再按反应调整。", ...metadata,
      message: { id: "alibaba-answer", role: "assistant", content: "先提供稳定的替代抓挠位置，再按反应调整。", metadata_json: metadata } } });
  });
  await page.goto("/chat");
  await expect(page.getByLabel("模型选择")).toHaveValue("alibaba");
  await expect(page.locator('option[value="alibaba"]')).toHaveText("阿里千问 · qwen3.7-flash");
  await page.getByRole("button", { name: "补充资料", exact: true }).click();
  await page.getByLabel("回答深度").selectOption("detailed");
  await page.getByLabel("提问内容").fill("猫抓沙发怎么办？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("qwen3.7-flash");
  await expect(page.locator(".message.assistant").last()).toContainText("替代抓挠位置");
  expect(requests[0]).toMatchObject({ model_id: "alibaba", answer_depth: "detailed" });
  await expect(page.locator(".message.assistant").last()).toContainText("猫的抓挠行为");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByLabel("模型选择").selectOption("deepseek");
  await page.reload();
  await expect(page.getByLabel("模型选择")).toHaveValue("deepseek");
});

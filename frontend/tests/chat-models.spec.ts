import { test, expect, type Page } from "@playwright/test";

async function login(page: Page) {
  const response = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await response.json()).access_token);
  await page.goto("/chat");
  await expect(page.getByLabel("模型选择")).toBeEnabled();
}

async function capture(page: Page, name: string) {
  await page.evaluate(async () => { await document.fonts.ready; if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/chat-model-${name}.png`, fullPage: true, animations: "disabled" });
}

test("server catalog, moved depth and local answer remain clear at target sizes", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: 900 });
  await login(page);
  await expect(page.getByLabel("模型选择")).toHaveValue("demo");
  await expect(page.locator('.chat-model-control option[value="deepseek"]')).toHaveJSProperty("disabled", true);
  await expect(page.locator(".chat-compose-controls")).not.toContainText("深度");
  await expect(page.getByLabel("回答深度")).toBeHidden();
  await page.getByLabel("提问内容").fill("猫日常喂食要注意什么？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("演示模式");
  await expect(page.locator("#chat-model-note")).toContainText("不调用外部模型");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await capture(page, info.project.name);
  if (info.project.name === "desktop") {
    await page.setViewportSize({ width: 1031, height: 1244 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await capture(page, "user-1031");
    await page.setViewportSize({ width: 1280, height: 900 });
  }
  await page.getByRole("button", { name: "补充资料", exact: true }).click();
  await page.getByLabel("回答深度").selectOption("detailed");
  await page.getByLabel("回答深度").scrollIntoViewIfNeeded();
  await page.evaluate(() => { const area = document.querySelector(".chat-depth-setting")!; window.scrollTo({ top: window.scrollY + area.getBoundingClientRect().top - 200, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/chat-model-depth-${info.project.name}.png`, fullPage: false, animations: "disabled" });
});

test("selected model travels in request, retry is unchanged and selection survives pet switch", async ({ page }) => {
  await page.route("**/api/v1/chat/models", route => route.fulfill({ json: { default_id: "demo", options: [
    { id: "demo", name: "本地演示", label: "演示模式 · 本地", provider: null, available: true, mode: "demo" },
    { id: "deepseek", name: "mock-selected-model", label: "接口模拟 · mock-selected-model", provider: "deepseek", available: true, mode: "live" },
  ] } }));
  await login(page);
  const requests: { id: string | undefined; body: Record<string, unknown> }[] = [];
  await page.route("**/api/v1/chat{,/stream}", route => {
    requests.push({ id: route.request().headers()["idempotency-key"], body: route.request().postDataJSON() });
    if (requests.length === 1 || requests.length === 3) return route.fulfill({ status: 503, json: { detail: "模拟接口失败，本次未完成。" } });
    const metadata = { mode: "live", sources: [], model_used: "mock-selected-model" };
    return route.fulfill({ json: { conversation_id: "test-model", answer: "模型选择接口模拟回答", ...metadata, message: { id: "test-model-answer", role: "assistant", content: "模型选择接口模拟回答", metadata_json: metadata } } });
  });
  await page.getByLabel("模型选择").selectOption("deepseek");
  await page.getByLabel("提问内容").fill("猫喂食建议");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("模拟接口失败，本次未完成。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("提问内容")).toHaveValue("猫喂食建议");
  await page.getByRole("button", { name: "重试本次请求", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("mock-selected-model");
  expect(requests[0].body.model_id).toBe("deepseek");
  expect(requests[1]).toEqual(requests[0]);
  await page.getByLabel("当前宠物").selectOption({ label: "豆包 · 狗" });
  await expect(page.getByLabel("模型选择")).toHaveValue("deepseek");
  await expect(page.getByLabel("提问内容")).toHaveValue("");
  await page.reload();
  await expect(page.getByLabel("模型选择")).toHaveValue("deepseek");
  await page.getByLabel("提问内容").fill("狗日常饮食建议");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("模拟接口失败，本次未完成。", { exact: true })).toBeVisible();
  await page.getByLabel("模型选择").selectOption("demo");
  await expect(page.getByRole("button", { name: "重试本次请求", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("提问内容")).toHaveValue("狗日常饮食建议");
});

test("catalog failure offers local demo and manual recovery without fake model result", async ({ page }) => {
  let count = 0;
  await page.route("**/api/v1/chat/models", async route => { if (++count === 1) await route.fulfill({ status: 503, json: { detail: "模拟列表读取失败" } }); else await route.continue(); });
  await login(page);
  await expect(page.getByRole("alert")).toContainText("模型列表读取失败");
  await page.getByLabel("模型选择").selectOption("demo");
  await page.getByLabel("提问内容").fill("猫护理要注意什么？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("演示模式");
  await page.getByRole("button", { name: "重读模型列表", exact: true }).click();
  await expect(page.getByRole("button", { name: "重读模型列表", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("模型选择")).toHaveValue("demo");
});

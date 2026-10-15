import { test, expect } from "@playwright/test";

test("配置缺失清楚显示，问答失败保留输入并可重试", async ({ page }) => {
  const login = await page.request.post("/api/v1/login/access-token", {
    form: { username: "demo@example.com", password: "Chongban2026!" },
  });
  const { access_token } = await login.json();
  await page.addInitScript((token) => sessionStorage.setItem("chongban_token", token), access_token);
  await page.route("**/api/v1/status", (route) => route.fulfill({
    json: { mode: "configuration_error", model: "deepseek-flash", reminder_delivery: "in_app_only" },
  }));
  await page.goto("/settings");
  await expect(page.getByText("模型配置待补充", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("真实模式已选择，但服务端密钥未配置。", { exact: false })).toBeVisible();
  await page.goto("/chat");
  await page.route("**/api/v1/chat{,/stream}", (route) => route.fulfill({
    status: 503, json: { detail: "模型请求失败，本次未完成。" },
  }));
  await page.getByLabel("提问内容").fill("喂食建议");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("模型请求失败，本次未完成。", { exact: true })).toBeVisible();
  await expect(page.getByLabel("提问内容")).toHaveValue("喂食建议");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
});

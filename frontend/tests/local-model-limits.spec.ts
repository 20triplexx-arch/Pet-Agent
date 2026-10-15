import { test, expect } from "@playwright/test";

test("settings distinguishes unlimited local calls from exhausted bounded quota", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: 900 });
  const login = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await login.json()).access_token);
  const user = await page.request.get("/api/v1/users/me", { headers: { Authorization: `Bearer ${(await login.json()).access_token}` } });
  const userData = await user.json();
  await page.route("**/api/v1/users/me", route => route.fulfill({ json: { ...userData, full_name: "界面测试" } }));
  let unlimited = true;
  await page.route("**/api/v1/usage/quota", route => route.fulfill({ json: {
    limits_enabled: !unlimited, daily_limit: unlimited ? null : 20, remaining_turns: unlimited ? null : 0,
    request_limit: unlimited ? null : 4, tool_calls_limit: unlimited ? null : 8,
    attempted_turns: unlimited ? 26 : 20, failed_turns: 2, timezone: "Asia/Shanghai", note: "界面测试响应",
  } }));
  await page.goto("/settings");
  const quota = page.locator(".model-quota");
  await expect(quota).toContainText("本地不限次数");
  await expect(quota).toContainText("26 次");
  await expect(quota).not.toContainText("剩余");
  await expect(quota).toContainText("实际 API 费用以服务商账单为准");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/local-limits-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  unlimited = false;
  await page.reload();
  await expect(quota).toContainText("20 / 20 次，剩余 0 次");
  await expect(quota).not.toContainText("不限次数");
  await page.evaluate(async () => { await document.fonts.ready; window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/local-limits-bounded-${info.project.name}.png`, fullPage: true, animations: "disabled" });
});

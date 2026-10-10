import { test, expect, type Page } from "@playwright/test";
async function login(page: Page) {
  const email =
    "ui-" +
    Date.now() +
    "-" +
    Math.random().toString(16).slice(2) +
    "@example.com";
  const password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", {
    data: { email, password, full_name: "浏览器测试" },
  });
  const result = await page.request.post("/api/v1/login/access-token", {
    form: { username: email, password },
  });
  const authorization = "Bearer " + (await result.json()).access_token;
  for (const pet of [
    { name: "奶糖", species: "cat", estimated_age_months: 8 },
    { name: "豆包", species: "dog", estimated_age_months: 36 },
  ]) {
    await page.request.post("/api/v1/pets", {
      headers: {
        Authorization: authorization,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: pet,
    });
  }
  await page.goto("/");
  await page.screenshot({ path: "../.impeccable/review/login-" + (page.viewportSize()!.width < 600 ? "mobile" : "desktop") + ".png", fullPage: true });
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "陪伴，是每天的小小用心" }),
  ).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "奶糖 · 猫" });
}
async function navigate(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByLabel("当前宠物")).toBeVisible();
}
test("猫狗档案和对话一起切换，来源与风险提示", async ({ page }) => {
  await login(page);
  await navigate(page, "/chat");
  await page.getByLabel("提问内容").fill("它的年龄适合怎样喂食？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("奶糖");
  await expect(page.locator(".message.assistant").last()).toContainText(
    "8 个月",
  );
  await expect(page.locator(".sources a").first()).toHaveAttribute(
    "href",
    /vet.cornell.edu/,
  );
  await page.getByLabel("当前宠物").selectOption({ label: "豆包 · 狗" });
  await expect(page.locator(".message")).toHaveCount(0);
  await page.getByLabel("提问内容").fill("喂食有什么建议");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("豆包");
  await expect(page.locator(".message.assistant").last()).not.toContainText(
    "奶糖",
  );
  await page.getByLabel("提问内容").fill("它呼吸困难");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.urgent").last()).toContainText(
    "请立即联系兽医",
  );
  await expect(page.locator(".urgent-title").last()).toBeVisible();
});
test("生成编辑保存计划，站内提醒打卡和历史", async ({ page }) => {
  await login(page);
  await navigate(page, "/plans");
  await page.getByRole("button", { name: "生成 / 重新调整草稿" }).click();
  await page.getByLabel("计划名称", { exact: true }).fill("浏览器验证计划");
  await page.getByLabel("任务名称 1", { exact: true }).fill("浏览器饮水检查");
  await page.getByRole("button", { name: "保存计划", exact: true }).click();
  await expect(page.locator(".saved-plan").last()).toContainText(
    "浏览器验证计划",
  );
  await page.getByLabel("待办事项").fill("浏览器即时打卡");
  await page.getByLabel("到期当地时间").fill("2026-01-01T08:00");
  await page.getByRole("button", { name: "创建提醒", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "完成 浏览器即时打卡", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "完成 浏览器即时打卡", exact: true })
    .click();
  await expect(page.getByText("本周期已打卡")).toBeVisible();
  await navigate(page, "/logs");
  await expect(
    page.locator(".journal-row").filter({ hasText: "浏览器即时打卡" }),
  ).toBeVisible();
});
test("档案建立编辑、记录体重并显示趋势", async ({ page }) => {
  await login(page);
  await navigate(page, "/pets");
  await page.getByRole("button", { name: "新增宠物", exact: true }).click();
  const name = "小白" + Date.now();
  await page.getByLabel("名称", { exact: true }).fill(name);
  await page.getByLabel("估计年龄（月，生日未知时）").fill("10");
  await page.getByRole("button", { name: "保存档案", exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: name + " · 猫" });
  await navigate(page, "/logs");
  await page.getByLabel("体重公斤").fill("4.25");
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(page.locator(".weight-current")).toContainText("4.25");
  await expect(page.locator(".journal-list")).toContainText("4.25 kg");
  await navigate(page, "/pets");
  await page
    .locator(".pet-cards .panel")
    .filter({ hasText: name })
    .getByRole("button", { name: "编辑", exact: true })
    .click();
  await page.getByLabel("当前饮食").fill("已更新的主食");
  await page.getByRole("button", { name: "保存档案", exact: true }).click();
  await expect(
    page.locator(".pet-cards .panel").filter({ hasText: name }),
  ).toContainText("已更新的主食");
});
test("知识搜索、收藏与真实来源详情", async ({ page }) => {
  await login(page);
  await navigate(page, "/knowledge");
  await page.getByLabel("搜索知识").fill("喂食");
  await expect(page.locator(".knowledge-grid .panel")).toHaveCount(1);
  await page
    .getByRole("link", { name: "猫的饮食：先看生命阶段与体况", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "猫的饮食：先看生命阶段与体况" }),
  ).toBeVisible();
  await expect(
    page.getByText("审核状态：编辑摘要，未经兽医审核"),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "查看专业来源原文 ↗" }),
  ).toHaveAttribute("href", /vet.cornell.edu/);
  await page.getByRole("button", { name: "收藏", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "已收藏", exact: true }),
  ).toBeVisible();
});
test("失败重试保持幂等键，创建提醒不重复", async ({ page }) => {
  await login(page);
  await navigate(page, "/plans");
  let seenKey: string | undefined;
  let count = 0;
  await page.route("**/api/v1/pets/*/reminders", async (route) => {
    count++;
    const key = route.request().headers()["idempotency-key"];
    if (count === 1) {
      seenKey = key;
      const res = await route.fetch();
      expect(res.ok()).toBeTruthy();
      await route.abort("failed");
    } else {
      expect(key).toBe(seenKey);
      await route.continue();
    }
  });
  const title = "重试唯一提醒" + Date.now();
  await page.getByLabel("待办事项").fill(title);
  await page.getByLabel("到期当地时间").fill("2026-01-01T10:00");
  await page.getByRole("button", { name: "创建提醒", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await page.getByRole("button", { name: "重试本次请求" }).click();
  await expect(page.locator(".todo").filter({ hasText: title })).toHaveCount(1);
});
test("七类页面在当前视口无横向溢出", async ({ page }, testInfo) => {
  await login(page);
  await expect(page.getByRole("navigation", { name: "主要导航" })).toBeVisible();
  for (const path of [
    "/",
    "/pets",
    "/chat",
    "/knowledge",
    "/plans",
    "/logs",
    "/settings",
  ]) {
    await navigate(page, path);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await expect(page.locator("h1")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "../.impeccable/review/" + (path === "/" ? "home" : path.slice(1)) + "-" + testInfo.project.name + ".png", fullPage: true });
  }
  await navigate(page, "/");
  await page.screenshot({
    path: "test-results/home-" + testInfo.project.name + ".png",
    fullPage: true,
  });
});

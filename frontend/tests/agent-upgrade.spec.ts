import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page) {
  const email = `care-${crypto.randomUUID()}@example.com`;
  const password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", {
    data: { email, password, full_name: "升级测试" },
  });
  const login = await page.request.post("/api/v1/login/access-token", {
    form: { username: email, password },
  });
  const headers = {
    Authorization: `Bearer ${(await login.json()).access_token}`,
    "Idempotency-Key": crypto.randomUUID(),
  };
  const pets = [];
  for (const data of [
    { name: "栗子", species: "cat", estimated_age_months: 36, neutered: true },
    { name: "团团", species: "dog", estimated_age_months: 48, neutered: true },
  ]) {
    const r = await page.request.post("/api/v1/pets", {
      data,
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
    });
    pets.push(await r.json());
  }
  await page.request.post(`/api/v1/pets/${pets[0].id}/logs`, {
    headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
    data: {
      kind: "weight",
      value: 4,
      occurred_at: new Date(Date.now() - 60000).toISOString(),
    },
  });
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "今天，好好陪伴" }),
  ).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "栗子 · 猫" });
  return { pets, headers };
}

async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
}

async function settleCapture(page: Page) {
  await page.evaluate(async () => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur();
    window.scrollTo(0, 0);
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
}

test("营养资料、预览调整保存及切换清空草稿", async ({ page }, info) => {
  await setup(page);
  await page.goto("/nutrition");
  await expect(
    page.getByRole("heading", { name: "本次营养资料" }),
  ).toBeVisible();
  await page.getByLabel("生命阶段", { exact: true }).selectOption("adult");
  await page.getByLabel("体况评分 BCS（1—9）").fill("5");
  await page.getByLabel("肌肉状况", { exact: true }).selectOption("normal");
  await page.getByLabel("体况评估日期").fill("2026-10-01");
  await page.getByLabel("体况填写者").selectOption("owner");
  await page.getByLabel("活动水平", { exact: true }).selectOption("normal");
  await page.getByLabel("当前健康状态").selectOption("healthy");
  await page.getByLabel("孕期 / 哺乳期").selectOption("no");
  await page.getByLabel("我已核对最新体重及日期，适用于本次评估").check();
  await page.getByRole("button", { name: "添加食物" }).click();
  await page.getByLabel("食物名称").fill("界面测试主粮");
  await page.getByLabel("包装热量").fill("400");
  await page.getByLabel("当前每日摄入（g）").fill("60");
  await page.getByLabel("全价主粮确认").selectOption("true");
  await page.getByLabel("所有零食已列入；没有零食也已确认").check();
  await page.getByLabel("确认按当前主粮热量比例分配，不生成新食谱").check();
  await page.getByRole("button", { name: "评估并预览方案" }).click();
  await expect(
    page.getByRole("heading", { name: "你的喂食参考" }),
  ).toBeVisible();
  await page.getByLabel("确认每日总热量目标（kcal）").fill("250");
  await page.getByLabel("餐次时间（逗号分隔）").fill("07:30,19:30");
  await page
    .locator(".nutrition-result summary")
    .filter({ hasText: "计算依据" })
    .click();
  await noOverflow(page);
  await settleCapture(page);
  await page.screenshot({
    path: `../.impeccable/review/nutrition-${info.project.name}.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "保存资料与营养方案", exact: true })
    .click();
  await expect(page.locator(".care-saved")).toContainText("每日约 62.5 g");
  await page.getByRole("link", { name: "查看计划与打卡" }).click();
  await expect(page.locator(".saved-plan")).toContainText(
    "本餐：界面测试主粮 约 31.2 g",
  );
  await page
    .locator(".saved-plan")
    .getByRole("button", { name: "编辑", exact: true })
    .click();
  await expect(page).toHaveURL(/\/nutrition$/);
  await expect(page.getByLabel("食物名称")).toHaveValue("界面测试主粮");
  await page.getByLabel("当前每日摄入（g）").fill("65");
  await page.getByLabel("当前宠物").selectOption({ label: "团团 · 狗" });
  await expect(page.getByLabel("生命阶段", { exact: true })).toHaveValue(
    "unknown",
  );
  await expect(page.getByLabel("食物名称")).toHaveCount(0);
  await expect(page.locator(".care-saved")).toHaveCount(0);
});

test("医院无密钥、定位拒绝、无结果与手动重试", async ({ page }, info) => {
  await setup(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "geolocation", {
      value: {
        getCurrentPosition: (_success: unknown, fail: () => void) => fail(),
      },
      configurable: true,
    });
  });
  await page.goto("/hospitals");
  await page.getByRole("button", { name: "使用我的位置" }).click();
  await expect(page.getByRole("alert")).toContainText("未取得定位");
  await page.getByLabel("城市", { exact: true }).fill("杭州");
  await page.getByLabel("区县（可选）").fill("西湖区");
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText(
    "未取得医院列表",
  );
  await expect(
    page.getByRole("link", { name: "打开高德搜索" }),
  ).toHaveAttribute("href", /uri.amap.com\/search/);
  await expect(page.locator(".hospital-row")).toHaveCount(0);
  await noOverflow(page);
  await settleCapture(page);
  await page.screenshot({
    path: `../.impeccable/review/hospitals-${info.project.name}.png`,
    fullPage: true,
  });
  await page.route("**/api/v1/hospitals/search", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "external",
        status: "empty",
        items: [],
        message: "当前范围没有返回医院",
        queried_at: new Date().toISOString(),
        search_url: "https://uri.amap.com/search?keyword=test",
      }),
    }),
  );
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText(
    "当前范围没有返回医院",
  );
});

test("真实就医摘要编辑、导出及宠物隔离", async ({ page }, info) => {
  const { pets, headers } = await setup(page);
  await page.request.post(`/api/v1/pets/${pets[0].id}/logs`, {
    headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
    data: {
      kind: "observation",
      note: "今天饮水减少（测试记录）",
      occurred_at: new Date(Date.now() - 60000).toISOString(),
    },
  });
  await page.goto("/hospitals#visit-summary");
  await page.getByLabel("本次观察", { exact: true }).fill("呼吸困难");
  await page.getByRole("button", { name: "生成就医摘要", exact: true }).click();
  await expect(page.getByLabel("就医摘要（可编辑）")).toHaveValue(/栗子/);
  await expect(page.getByLabel("就医摘要（可编辑）")).toHaveValue(
    /今天饮水减少/,
  );
  await expect(page.locator(".visit-panel .alert")).toContainText(
    "立即联系兽医",
  );
  await page
    .getByLabel("就医摘要（可编辑）")
    .fill("用户编辑的就医资料\n栗子：记录准确。");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 TXT", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("宠伴-就医摘要.txt");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString("utf8")).toContain(
    "用户编辑的就医资料",
  );
  await noOverflow(page);
  await settleCapture(page);
  await page.screenshot({
    path: `../.impeccable/review/visit-${info.project.name}.png`,
    fullPage: true,
  });
  await page.getByLabel("当前宠物").selectOption({ label: "团团 · 狗" });
  await expect(page.getByLabel("就医摘要（可编辑）")).toHaveCount(0);
  await expect(page.getByLabel("本次观察", { exact: true })).toHaveValue("");
});

test("对话营养行动和紧急就医入口", async ({ page }) => {
  await setup(page);
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("帮我调整喂食和营养");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "不能可靠",
  );
  await expect(
    page
      .locator(".message.assistant")
      .last()
      .getByRole("link", { name: "预览营养方案" }),
  ).toBeVisible();
  await page.getByLabel("提问内容").fill("呼吸困难，附近医院在哪里");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const last = page.locator(".message.assistant").last();
  await expect(last).toContainText("请立即联系兽医");
  await expect(
    last.getByRole("link", { name: "找附近宠物医院" }),
  ).toBeVisible();
  await last.getByRole("link", { name: "整理就医资料" }).click();
  await expect(page).toHaveURL(/\/hospitals#visit-summary$/);
  await expect(page.getByLabel("本次观察", { exact: true })).toBeVisible();
});

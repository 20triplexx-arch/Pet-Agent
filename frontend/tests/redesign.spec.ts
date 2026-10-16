import { test, expect, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";

async function setup(page: Page) {
  const email = `design-${crypto.randomUUID()}@example.com`;
  const password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", {
    data: { email, password, full_name: "照护体验" },
  });
  const login = await page.request.post("/api/v1/login/access-token", {
    form: { username: email, password },
  });
  const headers = {
    Authorization: `Bearer ${(await login.json()).access_token}`,
    "Idempotency-Key": crypto.randomUUID(),
  };
  let catId = "";
  for (const data of [
    {
      name: "奶糖",
      species: "cat",
      estimated_age_months: 8,
      diet: "完整均衡幼猫粮",
      environment: "室内生活，有安静的休息区",
    },
    {
      name: "豆包",
      species: "dog",
      estimated_age_months: 36,
      diet: "完整均衡成年犬粮",
      environment: "公寓，与家人生活",
    },
  ]) {
    const r = await page.request.post("/api/v1/pets", {
      data,
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
    });
    const pet = await r.json();
    await page.request.post(`/api/v1/pets/${pet.id}/logs`, {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data: {
        kind: "weight",
        value: pet.species === "cat" ? 3.4 : 12.8,
        occurred_at: new Date().toISOString(),
      },
    });
    if (pet.species === "cat") {
      catId = pet.id;
      for (const title of ["检查饮水与食盆", "晚间互动", "记录今天的食欲"]) {
        await page.request.post(`/api/v1/pets/${pet.id}/reminders`, {
          headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
          data: {
            title,
            due_local: "2026-01-01T08:00",
            timezone: "Asia/Shanghai",
            recurrence: "once",
          },
        });
      }
    }
  }
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("当前宠物")).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "奶糖 · 猫" });
  return { headers, catId };
}

async function settled(page: Page) {
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.locator("main .state")).toHaveCount(0);
  await page.evaluate(async () => {
    await document.fonts.ready;
    window.scrollTo(0, 0);
  });
}

test("五项手机导航、更多焦点与关闭、路由选中", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 664 });
  const nav = page.getByRole("navigation", { name: "手机主要导航" });
  await expect(nav.getByRole("link")).toHaveCount(4);
  const more = nav.getByRole("button", { name: "更多", exact: true });
  const dialog = page.getByRole("dialog", { name: "更多", exact: true });
  await more.click();
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("button", { name: "关闭更多" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("link", { name: "宠物档案" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(more).toBeFocused();
  await more.click();
  await page.mouse.click(12, 120);
  await expect(dialog).not.toBeVisible();
  await expect(more).toBeFocused();
  await more.click();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.screenshot({
    path: `../.impeccable/review/redesign/more-${info.project.name}.png`,
  });
  await dialog.getByRole("link", { name: "宠物档案" }).click();
  await expect(page).toHaveURL(/\/pets$/);
  await expect(dialog).not.toBeVisible();
  await expect(more).toHaveClass(/active/);
  await expect(page.getByLabel("当前宠物")).toBeVisible();
  await more.click();
  await page.setViewportSize({ width: 1280, height: 720 });
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "主要导航" }).getByRole("link"),
  ).toHaveCount(8);
});

test("全站六种宽度与双倍缩放等效视口，完整宠物插画", async ({ page }, info) => {
  test.setTimeout(120000);
  await setup(page);
  const widths = [320, 390, 430, 850, 1280, 1440];
  const routes = [
    "/",
    "/pets",
    "/chat",
    "/knowledge",
    "/plans",
    "/logs",
    "/settings",
    "/nutrition",
    "/hospitals",
    "/products",
  ];
  for (const width of widths) {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
    for (const path of routes) {
      await page.goto(path);
      await settled(page);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${width}px ${path}`,
      ).toBeTruthy();
      if (path === "/pets") {
        for (const img of await page.locator(".pet-card-head img").all()) {
          expect(
            await img.evaluate((el) => getComputedStyle(el).objectFit),
          ).toBe("contain");
          expect(
            await img.evaluate((el) => (el as HTMLImageElement).naturalWidth),
          ).toBeGreaterThan(0);
        }
      }
      const captureWidth = info.project.name === "desktop" ? 1280 : 390;
      if (width === captureWidth) {
        await page.screenshot({
          path: `../.impeccable/review/redesign/${path === "/" ? "home" : path.slice(1)}-${info.project.name}.png`,
          fullPage: false,
        });
        if (
          ["/nutrition", "/hospitals", "/settings", "/logs", "/pets"].includes(
            path,
          )
        ) {
          await page.screenshot({
            path: `../.impeccable/review/redesign/${path.slice(1)}-${info.project.name}-full.png`,
            fullPage: true,
          });
        }
      }
      if (path === "/" && info.project.name === "desktop") {
        await page.screenshot({
          path: `../.impeccable/review/redesign/home-width-${width}.png`,
        });
      }
    }
  }
  // Browser zoom reduces the CSS viewport. 1280px at 200% has 640 CSS pixels.
  await page.setViewportSize({ width: 640, height: 450 });
  for (const path of routes) {
    await page.goto(path);
    await settled(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      `200% equivalent ${path}`,
    ).toBeTruthy();
    await expect(page.getByLabel("当前宠物")).toBeVisible();
  }
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  await page.goto("/knowledge");
  await settled(page);
  await page.locator(".knowledge-row-content a").first().click();
  await settled(page);
  await page.screenshot({
    path: `../.impeccable/review/redesign/article-${info.project.name}.png`,
    fullPage: true,
  });
});

test("字号、对比度、本地字体和知识请求失败重试", async ({ page, baseURL }) => {
  const external: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== new URL(baseURL!).origin)
      external.push(request.url());
  });
  await setup(page);
  await settled(page);
  const styles = await page.evaluate(() => {
    const primary = getComputedStyle(
      document.querySelector(".home-today .check-button")!,
    );
    const meta = getComputedStyle(
      document.querySelector(".home-welcome-meta")!,
    );
    const root = getComputedStyle(document.documentElement);
    return {
      family: root.fontFamily,
      body: parseFloat(root.fontSize),
      meta: parseFloat(meta.fontSize),
      touch: primary.minHeight,
      colors: [
        root.getPropertyValue("--color-primary").trim(),
        root.getPropertyValue("--color-muted").trim(),
        root.getPropertyValue("--color-ground").trim(),
        root.getPropertyValue("--color-control-line").trim(),
      ],
    };
  });
  expect(styles.family).toContain("Noto Sans SC");
  expect(styles.body).toBeGreaterThanOrEqual(16);
  expect(styles.meta).toBeGreaterThanOrEqual(13);
  expect(parseFloat(styles.touch)).toBeGreaterThanOrEqual(44);
  const luminance = (hex: string) =>
    hex
      .match(/[\da-f]{2}/gi)!
      .map((v) => parseInt(v, 16) / 255)
      .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
      .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
  const contrast = (a: string, b: string) =>
    (Math.max(luminance(a), luminance(b)) + 0.05) /
    (Math.min(luminance(a), luminance(b)) + 0.05);
  expect(contrast(styles.colors[0], "#ffffff")).toBeGreaterThanOrEqual(4.5);
  expect(contrast(styles.colors[1], styles.colors[2])).toBeGreaterThanOrEqual(
    4.5,
  );
  expect(contrast(styles.colors[3], "#ffffff")).toBeGreaterThanOrEqual(3);
  expect(external).toEqual([]);
  let failures = 0;
  await page.route("**/api/v1/knowledge?*", async (route) => {
    if (!failures++)
      await route.fulfill({
        status: 503,
        json: { detail: "知识服务暂时不可用，请重试" },
      });
    else await route.continue();
  });
  await page.goto("/knowledge");
  await expect(page.getByRole("alert")).toContainText("知识服务暂时不可用");
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".knowledge-row").first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("体重图实际标签与记录、知识摘要的正文可读", async ({ page }, info) => {
  const { headers, catId } = await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  for (const data of [
    { kind: "weight", value: 3.2, occurred_at: "2026-09-20T08:00:00Z" },
    {
      kind: "activity",
      note: "晚间玩逗猫棒后主动休息，食欲与饮水和平时相近。",
      occurred_at: new Date().toISOString(),
    },
  ])
    await page.request.post(`/api/v1/pets/${catId}/logs`, {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data,
    });
  await page.goto("/logs");
  await settled(page);
  await expect(page.locator(".weight-chart text")).toHaveCount(5);
  const pixels = await page
    .locator(".weight-chart text")
    .evaluateAll((labels) =>
      labels.map((label) => {
        const matrix = (label as SVGGraphicsElement).getScreenCTM()!;
        return (
          parseFloat(getComputedStyle(label).fontSize) *
          Math.hypot(matrix.c, matrix.d)
        );
      }),
    );
  for (const size of pixels) expect(size).toBeGreaterThanOrEqual(12.99);
  expect(
    await page
      .locator(".journal-row p")
      .first()
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBe(16);
  await page.screenshot({
    path: `../.impeccable/review/redesign/logs-${info.project.name}-full.png`,
    fullPage: true,
  });
  await page.locator(".weight-chart").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `../.impeccable/review/redesign/weight-readable-${info.project.name}.png`,
  });
  writeFileSync(
    `../.impeccable/review/redesign/weight-font-${info.project.name}.json`,
    JSON.stringify(
      { viewport: page.viewportSize(), displayedLabelPixels: pixels },
      null,
      2,
    ),
  );
  await page.goto("/knowledge");
  await settled(page);
  expect(
    await page
      .locator(".article-excerpt")
      .first()
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBe(16);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("档案与计划编辑立即定位、首字段焦点与取消返回", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  await page.goto("/pets");
  await settled(page);
  const petEdit = page
    .locator(".pet-cards .panel")
    .first()
    .getByRole("button", { name: "编辑", exact: true });
  await petEdit.click();
  const name = page.getByLabel("名称", { exact: true });
  await expect(name).toBeFocused();
  const formTop = (await page.locator(".form-panel h2").boundingBox())!.y;
  expect(formTop).toBeGreaterThanOrEqual(64);
  expect(formTop).toBeLessThan(page.viewportSize()!.height - 72);
  await page.screenshot({
    path: `../.impeccable/review/redesign/edit-pet-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(petEdit).toBeFocused();
  const addPet = page.getByRole("button", { name: "新增宠物", exact: true });
  await addPet.click();
  await expect(name).toBeFocused();
  await expect(name).toHaveValue("");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(addPet).toBeFocused();
  await page.goto("/plans");
  await settled(page);
  await page.getByRole("button", { name: "生成 / 重新调整草稿" }).click();
  await expect(page.getByLabel("计划名称", { exact: true })).toBeFocused();
  await page.getByRole("button", { name: "保存计划", exact: true }).click();
  await expect(page.locator(".saved-plan")).toHaveCount(1);
  expect(
    await page
      .locator(".saved-plan p")
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBe(16);
  const planEdit = page
    .locator(".saved-plan")
    .getByRole("button", { name: "编辑", exact: true });
  await planEdit.scrollIntoViewIfNeeded();
  await planEdit.click();
  await expect(page.getByLabel("计划名称", { exact: true })).toBeFocused();
  expect(
    (await page.locator(".form-panel h2").boundingBox())!.y,
  ).toBeGreaterThanOrEqual(64);
  await page.screenshot({
    path: `../.impeccable/review/redesign/edit-plan-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(planEdit).toBeFocused();
  await page.screenshot({
    path: `../.impeccable/review/redesign/plan-readable-${info.project.name}.png`,
  });
});

test("长对话最近消息定位与向上阅读时的新回复入口", async ({ page }, info) => {
  test.setTimeout(60000);
  const { headers, catId } = await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  let conversationId = null;
  for (const text of [
    "猫的新宠到家怎样准备？",
    "它的年龄适合怎样的照护？",
    "猫饮食有什么常见误区？",
    "日常健康观察要记录什么？",
  ]) {
    const r = await page.request.post("/api/v1/chat", {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data: {
        pet_id: catId,
        conversation_id: conversationId,
        text,
        available_minutes: 30,
      },
    });
    expect(r.ok()).toBeTruthy();
    conversationId = (await r.json()).conversation_id;
  }
  await page.goto("/chat");
  await settled(page);
  const list = page.locator(".messages");
  const latest = page.locator(".message.assistant").last();
  const latestInView = async () => {
    const outer = (await list.boundingBox())!;
    const answer = (await latest.boundingBox())!;
    expect(answer.y).toBeGreaterThanOrEqual(outer.y - 1);
    expect(answer.y).toBeLessThan(outer.y + outer.height);
  };
  await expect(page.locator(".message")).toHaveCount(8);
  expect(await list.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await latestInView();
  expect(
    await latest
      .locator(".message-text")
      .evaluate((el) => parseFloat(getComputedStyle(el).fontSize)),
  ).toBe(16);
  await page.getByLabel("提问内容").fill("日常喂食要注意什么？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  // Optimistic streaming adds two message nodes before the reply is committed.
  await expect(page.locator(".message.assistant:not(.generating)")).toHaveCount(5);
  await expect(page.locator(".message")).toHaveCount(10);
  await latestInView();
  let release!: () => void;
  let requested!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  const requestArrived = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route("**/api/v1/chat{,/stream}", async (route) => {
    requested();
    await blocked;
    await route.continue();
  });
  await page.getByLabel("提问内容").fill("猫的日常清洁怎样安排？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await requestArrived;
  await list.hover();
  await page.mouse.wheel(0, -100000);
  await expect.poll(() => list.evaluate(el => el.scrollTop)).toBeLessThan(1);
  release();
  await expect(
    page.getByRole("button", { name: "查看最新回复", exact: true }),
  ).toBeVisible();
  expect(await list.evaluate((el) => el.scrollTop)).toBeLessThan(1);
  await page.screenshot({
    path: `../.impeccable/review/redesign/chat-unread-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "查看最新回复", exact: true }).click();
  await latestInView();
  await expect(
    page.getByRole("button", { name: "查看最新回复", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: `../.impeccable/review/redesign/chat-latest-${info.project.name}.png`,
  });
});

test("档案服务端字段错误关联、定位与原请求重试", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  await page.goto("/pets");
  await settled(page);
  await page.getByRole("button", { name: "新增宠物", exact: true }).click();
  const name = page.getByLabel("名称", { exact: true });
  const age = page.getByLabel("估计年龄（月，生日未知时）");
  await name.fill("字段重试宠物");
  await age.fill("12");
  let count = 0;
  const keys: string[] = [];
  await page.route("**/api/v1/pets", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    keys.push(route.request().headers()["idempotency-key"]);
    if (!count++)
      await route.fulfill({
        status: 422,
        json: {
          detail: [
            {
              loc: ["body", "name"],
              msg: "请检查名称格式",
              type: "value_error",
            },
            {
              loc: ["body", "estimated_age_months"],
              msg: "请核对估计年龄",
              type: "value_error",
            },
          ],
        },
      });
    else await route.continue();
  });
  await page.getByRole("button", { name: "保存档案", exact: true }).click();
  await expect(name).toHaveAttribute("aria-invalid", "true");
  await expect(age).toHaveAttribute("aria-invalid", "true");
  await expect(name).toBeFocused();
  await expect(name).toHaveAccessibleName("名称");
  await expect(name).toHaveAccessibleDescription("请检查名称格式");
  await expect(age).toHaveAccessibleDescription("请核对估计年龄");
  await expect(page.locator(".field-error")).toHaveCount(2);
  await expect(page.getByText("宠物档案已保存", { exact: true })).toHaveCount(
    0,
  );
  await page.screenshot({
    path: `../.impeccable/review/redesign/field-errors-pet-${info.project.name}.png`,
  });
  await page.getByRole("button", { name: "重试本次请求", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "字段重试宠物", exact: true }),
  ).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await expect(page.locator(".field-error")).toHaveCount(0);
  await expect(page.locator("[aria-invalid=true]")).toHaveCount(0);
  await expect(page.locator(".pet-cards .panel")).toHaveCount(3);
});

test("营养嵌套字段错误能关联非表单资料与手动恢复", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  await page.goto("/nutrition");
  await settled(page);
  await page.getByRole("button", { name: "添加食物", exact: true }).click();
  await page.getByLabel("食物名称", { exact: true }).fill("当前完整主粮");
  const energy = page.getByLabel("包装热量", { exact: true });
  await energy.fill("400");
  let failed = false;
  await page.route("**/api/v1/pets/*/nutrition/profile", async (route) => {
    if (route.request().method() !== "PUT" || failed) return route.continue();
    failed = true;
    await route.fulfill({
      status: 422,
      json: {
        detail: [
          {
            loc: ["body", "profile", "foods", 0, "energy"],
            msg: "请核对包装热量",
            type: "value_error",
          },
        ],
      },
    });
  });
  await page.getByRole("button", { name: "只保存资料", exact: true }).click();
  await expect(energy).toHaveAttribute("aria-invalid", "true");
  await expect(energy).toBeFocused();
  await expect(energy).toHaveAccessibleDescription("请核对包装热量");
  await expect(page.locator(".field-error")).toHaveCount(1);
  await page.screenshot({
    path: `../.impeccable/review/redesign/field-errors-nutrition-${info.project.name}.png`,
  });
  await energy.fill("390");
  await page.getByRole("button", { name: "只保存资料", exact: true }).click();
  await expect(page.locator(".field-error")).toHaveCount(0);
  await expect(energy).not.toHaveAttribute("aria-invalid", "true");
});

test("对话侧栏的服务端字段错误跨工作区关联与恢复", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize({
    width: info.project.name === "desktop" ? 1280 : 390,
    height: info.project.name === "desktop" ? 900 : 844,
  });
  await page.goto("/chat");
  await settled(page);
  const minutes = page.locator('.chat-context input[name="available_minutes"]');
  await minutes.fill("1");
  await page.getByLabel("提问内容").fill("日常喂食要注意什么？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(minutes).toHaveAttribute("aria-invalid", "true");
  await expect(minutes).toBeFocused();
  await expect(minutes).toHaveAccessibleDescription(
    /greater than or equal to 5/,
  );
  await expect(page.locator(".message.assistant")).toHaveCount(0);
  await page.screenshot({
    path: `../.impeccable/review/redesign/field-errors-chat-${info.project.name}.png`,
  });
  await minutes.fill("30");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await expect(minutes).not.toHaveAttribute("aria-invalid", "true");
  await expect(page.locator(".field-error")).toHaveCount(0);
});

import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page) {
  const email = `products-${Date.now()}-${Math.random()}@example.com`,
    password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", {
    data: { email, password, full_name: "选购测试" },
  });
  const login = await page.request.post("/api/v1/login/access-token", {
    form: { username: email, password },
  });
  const authorization = "Bearer " + (await login.json()).access_token;
  for (const p of [
    {
      name: "小英",
      species: "cat",
      estimated_age_months: 24,
      breed: "英短",
      breed_id: "cat-british-shorthair",
    },
    {
      name: "豆包",
      species: "dog",
      estimated_age_months: 36,
      breed_id: "dog-golden",
    },
  ]) {
    const r = await page.request.post("/api/v1/pets", {
      headers: {
        Authorization: authorization,
        "Idempotency-Key": crypto.randomUUID(),
      },
      data: p,
    });
    expect(r.ok()).toBeTruthy();
  }
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".home-welcome")).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "小英 · 猫" });
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
}

test("知识的物种、品种、分类、来源与收藏", async ({ page }, info) => {
  await setup(page);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: "品种", exact: true }).click();
  await page.getByLabel("品种筛选").selectOption("cat-british-shorthair");
  await expect(page.locator(".knowledge-grid > .knowledge-row")).toHaveCount(1);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `../.impeccable/review/knowledge-products-${info.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: /英国短毛猫：生活/ }).click();
  await expect(page.getByRole("heading", { name: "名称与特征" })).toBeVisible();
  await expect(
    page.getByText("支持内容：", { exact: false }).first(),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /CFA/ })).toHaveAttribute(
    "href",
    /cfa.org/,
  );
  await page.getByRole("button", { name: "收藏", exact: true }).click();
  await expect(page.getByRole("button", { name: "已收藏" })).toBeVisible();
  await page.getByRole("link", { name: "返回知识库", exact: true }).click();
  await page.getByRole("button", { name: "食物", exact: true }).click();
  await page.getByLabel("搜索知识").fill("保证分析");
  await expect(
    page.locator(".knowledge-grid > .knowledge-row").first(),
  ).toContainText("包装");
  await noOverflow(page);
  await page.getByLabel("当前宠物").selectOption({ label: "豆包 · 狗" });
  await expect(page.getByLabel("知识物种")).toHaveValue("dog");
  await page.getByRole("button", { name: "品种", exact: true }).click();
  await page.getByLabel("品种筛选").selectOption("dog-golden");
  await expect(page.locator(".knowledge-grid > .knowledge-row")).toHaveCount(1);
  await expect(page.locator(".knowledge-grid > .knowledge-row")).toContainText(
    "金毛寻回犬",
  );
});

test("对话的品种与产品行动可进入对应页面", async ({ page }) => {
  await setup(page);
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("英短有哪些品种特点？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const guide = page.getByRole("link", { name: "查看完整品种指南" });
  await expect(guide).toBeVisible();
  await guide.click();
  await expect(page).toHaveURL(/\/knowledge\//);
  await expect(page.getByRole("heading", { name: "名称与特征" })).toBeVisible();
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("帮我比较猫粮");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const compare = page.getByRole("link", { name: "比较具体食品与用品" });
  await expect(compare).toBeVisible();
  await compare.click();
  await expect(page).toHaveURL(/\/products$/);
  await expect(page.locator(".product-editor")).toHaveCount(1);
});

test("手动比较、编辑、保存、回看与宠物切换", async ({ page }, info) => {
  await setup(page);
  await page.goto("/products");
  const product = page.locator(".product-editor").first();
  await product.getByLabel("名称", { exact: true }).fill("测试配方A");
  await product
    .getByLabel("包装文字")
    .fill(
      "SAMPLE LABEL\nEnergy 1673.6 kJ/100g\nNet weight 1000 g\n粗蛋白 ≥ 32.5%\n水分 ≤ 10%",
    );
  await product.getByRole("button", { name: "从文字提取候选数值" }).click();
  await expect(product.getByLabel("包装热量", { exact: true })).toHaveValue(
    "1673.6",
  );
  await expect(product.getByLabel("热量单位")).toHaveValue("kj_100g");
  await product.getByLabel("包装适用物种").selectOption("cat");
  await product.getByLabel("食品适用阶段").selectOption("adult");
  await product.getByLabel("完整 / 补充性食品").selectOption("complete");
  await product.getByLabel("加工方式").selectOption("cooked");
  await product
    .getByLabel("营养适用声明原文")
    .fill("测试标签：完整食品，成年猫维持；非实际商品");
  await product.getByLabel("已确认实际每日摄入").fill("50");
  await product
    .locator("summary")
    .filter({ hasText: "配料、保证分析与专业限制" })
    .click();
  await product.getByLabel("配料原文").fill("测试标签鸡肉等");
  await expect(product.getByLabel("性质").first()).toHaveValue("min");
  await product
    .locator("summary")
    .filter({ hasText: "价格、持续成本与资料来源" })
    .click();
  await product.getByLabel("实际价格", { exact: true }).fill("100");
  await product.getByLabel("价格日期").fill("2026-10-01");
  await product.getByLabel("厂家配方").fill("用户提供的测试资料，未经厂家核实");
  await expect(page.getByRole("button", { name: "核对并比较" })).toBeDisabled();
  await product.getByRole("checkbox", { name: /我已核对/ }).check();
  await page.getByRole("button", { name: "核对并比较" }).click();
  await expect(
    page.getByRole("heading", { name: "比较结果", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".assessment-status")).toHaveText("条件下可考虑");
  await expect(page.locator(".product-costs")).toContainText("2.50");
  await noOverflow(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `../.impeccable/review/product-${info.project.name}.png`,
    animations: "disabled",
  });
  await page.locator(".assessment-result").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `../.impeccable/review/product-result-${info.project.name}.png`,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "明确保存这次比较" }).click();
  await expect(page.getByRole("button", { name: "已保存比较" })).toBeDisabled();
  await expect(page.locator(".comparison-history")).toHaveCount(1);
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "添加到营养资料" }).click();
  await expect(page).toHaveURL(/\/nutrition$/);
  await expect(page.locator('input[value="测试配方A"]')).toHaveCount(1);
  await page.goto("/products");
  await page.getByRole("button", { name: "查看", exact: true }).click();
  await expect(page.getByRole("heading", { name: "历史比较" })).toBeVisible();
  await page.getByRole("button", { name: "用这些资料重新比较" }).click();
  await product.getByLabel("包装热量", { exact: true }).fill("1600");
  await expect(
    product.getByRole("checkbox", { name: /我已核对/ }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("heading", { name: "比较结果", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("当前宠物").selectOption({ label: "豆包 · 狗" });
  await expect(page.getByLabel("名称", { exact: true })).toHaveValue("");
  await expect(page.locator(".comparison-history")).toHaveCount(0);
});

test("真实本地标签识别与关键字段确认", async ({ page }, info) => {
  test.setTimeout(60000);
  await setup(page);
  await page.goto("/products");
  await page.getByLabel("名称", { exact: true }).fill("本地识别测试");
  const upload = page.getByRole("button", { name: "选择包装图片" });
  await expect(upload).toBeVisible();
  await upload.focus();
  await expect(upload).toBeFocused();
  await page
    .getByLabel("上传包装图片")
    .setInputFiles("tests/fixtures/label-zh-en.png");
  await expect(page.getByText("正在本地识别，请稍候…")).toBeVisible();
  await expect(page.getByLabel("比较类别")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "添加同类产品" }),
  ).toBeDisabled();
  await expect(page.getByLabel("包装文字")).toHaveValue(/SAMPLE LABEL/, {
    timeout: 35000,
  });
  await expect(page.getByLabel("包装热量", { exact: true })).toHaveValue(
    "418.4",
  );
  await expect(page.getByLabel("净含量（g）", { exact: true })).toHaveValue(
    "1500",
  );
  await expect(
    page.getByRole("checkbox", { name: /我已核对/ }),
  ).not.toBeChecked();
  await expect(page.getByRole("button", { name: "核对并比较" })).toBeDisabled();
  await noOverflow(page);
  await page
    .locator(".packaging-input")
    .screenshot({
      path: `../.impeccable/review/product-ocr-${info.project.name}.png`,
      animations: "disabled",
    });
});

test("未安装识别时可手动录入，失败可重试", async ({ page }) => {
  await setup(page);
  await page.route("**/api/v1/products/ocr/status", (route) =>
    route.fulfill({
      json: {
        available: false,
        message: "未安装本地识别，手动输入可用",
        engine: "RapidOCR",
        timeout_seconds: 30,
      },
    }),
  );
  await page.goto("/products");
  await expect(page.getByText(/未安装本地识别，手动输入可用/)).toBeVisible();
  await page.getByLabel("名称", { exact: true }).fill("测试玩具");
  await page.getByLabel("比较类别").selectOption("toys");
  await page.getByLabel("包装适用物种").selectOption("cat");
  await page.getByRole("checkbox", { name: /我已核对/ }).check();
  await page.route(
    "**/api/v1/products/assessments/preview",
    (route) =>
      route.fulfill({ status: 503, json: { detail: "测试失败，请重试" } }),
    { times: 1 },
  );
  await page.getByRole("button", { name: "核对并比较" }).click();
  await expect(page.getByText("测试失败，请重试")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "比较结果", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "重试本次请求", exact: true }).click();
  await expect(page.locator(".assessment-status")).toHaveText("资料不足");
});

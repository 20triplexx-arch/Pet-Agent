import { test, expect, type Page } from "@playwright/test";

async function prepare(page: Page) {
  const email = `deep-${Date.now()}-${Math.random()}@example.com`, password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", { data: { email, password, full_name: "深度照护测试" } });
  const login = await page.request.post("/api/v1/login/access-token", { form: { username: email, password } });
  const headers = { Authorization: "Bearer " + (await login.json()).access_token };
  const pets = [];
  for (const item of [{ name: "小团", species: "cat", neutered: true }, { name: "阿福", species: "dog", neutered: true }]) {
    const response = await page.request.post("/api/v1/pets", { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { ...item, estimated_age_months: 36 } });
    pets.push(await response.json());
  }
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".home-welcome")).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "小团 · 猫" });
  await page.goto("/chat");
  return { headers, pets };
}

test("long input, supplement persistence, source sections and deeper followup", async ({ page, context }, info) => {
  await prepare(page);
  await page.getByRole("button", { name: "补充资料", exact: true }).click();
  await page.getByLabel("照护目标", { exact: true }).fill("减少抓沙发，同时改善多猫相处");
  await page.getByLabel("时间线", { exact: true }).fill("上周新猫到家，原住猫最近开始回避");
  await page.getByRole("button", { name: "回到提问" }).click();
  const text = "猫抓沙发怎么办？另外多猫如何相处？" + "补充家庭环境记录。".repeat(460);
  await page.getByLabel("提问内容").fill(text);
  await expect(page.locator("#chat-input-count")).toContainText(`${text.length} / 12000`);
  await page.getByLabel("回答深度", { exact: true }).selectOption("detailed");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("上周新猫到家");
  await expect(page.locator(".answer-content h3").first()).toBeVisible();
  await expect(page.locator(".answer-content").last()).toContainText("抓");
  await expect(page.locator(".answer-content").last()).toContainText("相处");
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "复制回答" }).last().click();
  await expect(page.getByRole("button", { name: "已复制" }).last()).toBeVisible();
  await page.getByRole("button", { name: "继续深入" }).last().click();
  await expect(page.getByLabel("提问内容")).toHaveValue(/进一步说明/);
  await expect(page.getByLabel("回答深度", { exact: true })).toHaveValue("detailed");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(2);
  await expect(page.locator(".message.assistant").last()).toContainText("上周新猫到家");
  await page.getByLabel("当前宠物").selectOption({ label: "阿福 · 狗" });
  await expect(page.locator(".message.assistant")).toHaveCount(0);
  await page.getByRole("button", { name: "补充资料", exact: true }).click();
  await expect(page.getByLabel("照护目标", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "回到提问" }).click();
  await expect(page.getByLabel("提问内容")).toHaveValue("");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("nutrition table and sources come from local assessment without new plan", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: info.project.name === "desktop" ? 900 : 844 });
  const { headers, pets } = await prepare(page), pet = pets[0];
  await page.request.post(`/api/v1/pets/${pet.id}/logs`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { kind: "weight", value: 4, occurred_at: new Date().toISOString() } });
  const profile = { life_stage: "adult", health_status: "healthy", bcs: 5, muscle: "normal", assessed_on: new Date().toISOString().slice(0, 10), assessor: "owner", activity_level: "normal", pregnancy_lactation: "no", weight_confirmed: true, treats_confirmed: true, food_shares_confirmed: true, foods: [{ name: "已核对主粮", complete_adult_food: true, energy: 400, energy_unit: "kcal_100g", daily_grams: 60 }] };
  await page.request.put(`/api/v1/pets/${pet.id}/nutrition/profile`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { profile, revision: 0 } });
  await page.getByLabel("提问内容").fill("请深入分析目前营养摄入、热量依据，以及后续该观察什么");
  await page.getByLabel("回答深度", { exact: true }).selectOption("detailed");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".answer-table table")).toBeVisible();
  await expect(page.locator(".answer-table")).toContainText("240");
  await expect(page.locator(".answer-content")).toContainText("保存目标后才改变任务");
  const plans = await page.request.get(`/api/v1/pets/${pet.id}/plans`, { headers });
  expect(await plans.json()).toHaveLength(0);
  await page.locator(".sources summary").last().click();
  await expect(page.locator(".source-section").first()).toBeVisible();
  const firstSection = page.locator(".source-section").first();
  await firstSection.click();
  await expect(page.locator(".article-body h2").first()).toBeVisible();
  await page.goto("/chat");
  await expect(page.locator(".answer-table")).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
    const list = document.querySelector<HTMLElement>(".messages")!, message = document.querySelector<HTMLElement>(".message.assistant")!;
    list.scrollTop += message.getBoundingClientRect().top - list.getBoundingClientRect().top - 12;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.scrollTo({ top: 0, behavior: "instant" });
  });
  await page.screenshot({ path: `../.impeccable/review/deep-chat-answer-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  await page.locator(".answer-table").scrollIntoViewIfNeeded();
  await page.locator(".answer-table").screenshot({ path: `../.impeccable/review/deep-chat-table-${info.project.name}.png`, animations: "disabled" });
});

test("oversized text, context validation, copy recovery and no raw HTML", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("提问内容").fill("文".repeat(12001));
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("请分次发送");
  await page.getByLabel("提问内容").fill("普通提问");
  await page.route("**/api/v1/chat", route => route.fulfill({ json: { conversation_id: "mock", answer: "## 对照说明\n\n| 条件 | 做法 |\n| --- | --- |\n| 已知 | **核对** |\n\n<script>window.injected=true</script> [not-a-source]", mode: "demo", sources: [], draft: null, message: { id: "safe-render", role: "assistant", content: "## 对照说明\n\n| 条件 | 做法 |\n| --- | --- |\n| 已知 | **核对** |\n\n<script>window.injected=true</script> [not-a-source]", metadata_json: { mode: "demo", sources: [] } } } }));
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".answer-content h3")).toHaveText("对照说明");
  await expect(page.locator(".answer-content strong")).toHaveText("核对");
  expect(await page.evaluate(() => (window as unknown as { injected?: boolean }).injected)).toBeUndefined();
  await expect(page.locator(".answer-content script")).toHaveCount(0);
  await expect(page.locator(".inline-source")).toHaveCount(0);
});

test("supplement inputs are usable and request errors preserve data", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: info.project.name === "desktop" ? 900 : 844 });
  await prepare(page);
  await page.getByRole("button", { name: "补充资料", exact: true }).click();
  await page.getByLabel("本次观察", { exact: true }).fill("昨天一次呕吐，精神和食欲正常");
  await page.getByLabel("时间线", { exact: true }).fill("昨天开始，今天暂未再出现");
  await page.evaluate(async () => { await document.fonts.ready; if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.waitForTimeout(200);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: `../.impeccable/review/deep-chat-supplement-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "回到提问" }).click();
  await page.getByLabel("提问内容").fill("需要记录什么，哪些变化会改变就医优先级");
  let calls = 0;
  await page.route("**/api/v1/chat", async route => { if (++calls === 1) await route.fulfill({ status: 503, json: { detail: "本次回答未完成，可手动重试" } }); else await route.continue(); });
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("未完成");
  await expect(page.getByLabel("提问内容")).toHaveValue(/需要记录什么/);
  await page.getByRole("button", { name: "重试本次请求", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await expect(page.locator(".message.assistant")).toContainText("昨天开始");
  expect(calls).toBe(2);
});

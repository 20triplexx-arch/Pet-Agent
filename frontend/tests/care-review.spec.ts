import { test, expect, type Page } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

async function setup(page: Page) {
  const email = `review-${Date.now()}-${Math.random()}@example.com`, password = "BrowserTesting2026!";
  await page.request.post("/api/v1/users/signup", { data: { email, password, full_name: "复盘测试" } });
  const auth = await page.request.post("/api/v1/login/access-token", { form: { username: email, password } });
  const headers = { Authorization: "Bearer " + (await auth.json()).access_token }, pets = [];
  for (const p of [{ name: "小年", species: "cat" }, { name: "阿米", species: "dog" }]) {
    const response = await page.request.post("/api/v1/pets", { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { ...p, estimated_age_months: 36 } });
    pets.push(await response.json());
  }
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByLabel("当前宠物").selectOption({ label: "小年 · 猫" });
  return { headers, pets };
}

test("batch records, dated review, download and pet switching", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: 900 });
  const { headers, pets } = await setup(page), pet = pets[0];
  for (const [days, value] of [[3, 4], [1, 4.1]]) {
    await page.request.post(`/api/v1/pets/${pet.id}/logs`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { kind: "weight", value, occurred_at: new Date(Date.now() - days * 86400000).toISOString() } });
  }
  await page.goto("/logs");
  await expect(page.locator(".care-review")).toContainText("实测差 +0.1 kg");
  await page.locator(".quick-care > summary").click();
  const form = page.getByRole("form", { name: "多项照护记录" });
  await form.getByLabel("饮食情况（可留空）").fill("提供完整成年主粮60克，剩余未称");
  await form.getByLabel("活动情况（可留空）").fill("互动10分钟，主动参与");
  await form.getByLabel("观察情况（可留空）").fill("今天观察食欲未变化；排泄数量未测");
  await form.getByLabel("我已核对填写内容与所选宠物、发生时间一致").check();
  await mkdir("../.impeccable/review", { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `../.impeccable/review/care-batch-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  await form.getByRole("button", { name: "保存填写的记录" }).click();
  await expect(page.locator(".quick-care")).toContainText("多项记录已全部保存");
  await expect(page.locator(".care-review .review-facts")).toContainText("共 5 条");
  const records = await page.request.get(`/api/v1/pets/${pet.id}/logs`, { headers });
  expect(await records.json()).toHaveLength(5);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载复盘 TXT" }).click();
  const download = await downloadPromise;
  expect(await readFile((await download.path())!, "utf8")).toContain("未记录不等于未照护");
  await page.locator(".quick-care > summary").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `../.impeccable/review/care-review-${info.project.name}.png`, fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "30天", exact: true }).click();
  await expect(page.locator(".care-review .review-facts")).toContainText("/ 30 天");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByLabel("当前宠物").selectOption({ label: "阿米 · 狗" });
  await expect(page.locator(".care-review")).toContainText("这段时间还没有记录");
  await page.locator(".quick-care > summary").click();
  await expect(form.getByLabel("饮食情况（可留空）")).toHaveValue("");
  await page.locator(".quick-care > summary").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `../.impeccable/review/care-review-empty-${info.project.name}.png`, fullPage: true, animations: "disabled" });
});

test("review and batch failure can retry without duplicate records", async ({ page }) => {
  const { headers, pets } = await setup(page), pet = pets[0];
  let reviewFail = true, batchFail = true;
  const keys: string[] = [];
  await page.route("**/care-review?*", route => {
    if (reviewFail) { reviewFail = false; return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "复盘暂时无法读取" }) }); }
    return route.continue();
  });
  await page.goto("/logs");
  await expect(page.locator(".care-review")).toContainText("复盘暂时无法读取");
  await page.locator(".care-review").getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.locator(".care-review")).toContainText("这段时间还没有记录");
  await page.route("**/logs/batch", route => {
    keys.push(route.request().headers()["idempotency-key"]);
    if (batchFail) { batchFail = false; return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "本次没有保存" }) }); }
    return route.continue();
  });
  await page.locator(".quick-care > summary").click();
  const form = page.getByRole("form", { name: "多项照护记录" });
  await form.getByLabel("护理情况（可留空）").fill("梳毛，接受短暂接触");
  await form.getByLabel("我已核对填写内容与所选宠物、发生时间一致").check();
  await form.getByRole("button", { name: "保存填写的记录" }).click();
  await expect(page.locator(".quick-care")).toContainText("本次没有保存");
  await expect(form.getByLabel("护理情况（可留空）")).toHaveValue("梳毛，接受短暂接触");
  await page.locator(".quick-care").getByRole("button", { name: "重试本次请求" }).click();
  await expect(page.locator(".quick-care")).toContainText("多项记录已全部保存");
  expect(keys).toHaveLength(2); expect(keys[0]).toBe(keys[1]);
  expect(await (await page.request.get(`/api/v1/pets/${pet.id}/logs`, { headers })).json()).toHaveLength(1);
});

test("review chat is local and actual source excerpts remain inspectable", async ({ page }, info) => {
  await page.setViewportSize({ width: info.project.name === "desktop" ? 1280 : 390, height: 900 });
  await setup(page);
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("请做照护复盘");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".answer-content")).toContainText("没有记录");
  await page.getByRole("link", { name: "查看照护复盘与记录" }).click();
  await expect(page.locator(".care-review")).toBeVisible();
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("猫的日常照护记录怎么写，怎样区分实际观察与估计？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(2);
  const message = page.locator(".message.assistant").last();
  await message.locator(".sources > summary").click();
  await message.locator(".source-evidence > summary").first().click();
  await expect(message.locator(".source-evidence").first()).toContainText("片段来自本次实际检索");
  await message.locator(".source-entry > a").first().evaluate(el => {
    const pane = el.closest(".messages") as HTMLElement;
    pane.scrollTo({ top: pane.scrollTop + el.getBoundingClientRect().top - pane.getBoundingClientRect().top - 12, behavior: "instant" });
    const panel = pane.closest("section")!;
    window.scrollTo({ top: window.scrollY + panel.getBoundingClientRect().top - 96, behavior: "instant" });
  });
  await page.screenshot({ path: `../.impeccable/review/care-evidence-${info.project.name}.png`, animations: "disabled" });
  await message.locator(".source-evidence small").first().evaluate(el => {
    const pane = el.closest(".messages") as HTMLElement;
    pane.scrollTo({ top: pane.scrollTop + el.getBoundingClientRect().bottom - pane.getBoundingClientRect().bottom + 12, behavior: "instant" });
  });
  await page.screenshot({ path: `../.impeccable/review/care-evidence-end-${info.project.name}.png`, animations: "disabled" });
});

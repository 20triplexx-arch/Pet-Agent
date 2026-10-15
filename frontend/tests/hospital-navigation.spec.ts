import { test, expect, type Page } from "@playwright/test";

async function prepare(page: Page) {
  const response = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await response.json()).access_token);
  await page.goto("/");
  await expect(page.getByLabel("当前宠物")).toBeVisible();
  await page.getByLabel("当前宠物").selectOption({ label: "奶糖 · 猫" });
}

async function screenshot(page: Page, name: string, fullPage = true) {
  await page.evaluate(async () => { await document.fonts.ready; if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/hospital-nav-${name}.png`, fullPage, animations: "disabled" });
}

test("独立医院导航：桌面、紧凑侧栏和手机更多直接进入及选中", async ({ page }, info) => {
  let searches = 0;
  page.on("request", request => { if (request.url().endsWith("/api/v1/hospitals/search")) searches++; });
  await prepare(page);
  if (info.project.name === "desktop") {
    await page.setViewportSize({ width: 1280, height: 900 });
    const nav = page.getByRole("navigation", { name: "主要导航", exact: true });
    const hospital = nav.getByRole("link", { name: "医院查询", exact: true });
    await hospital.click();
    await expect(page).toHaveURL(/\/hospitals$/);
    await expect(page.getByRole("heading", { name: "医院查询", exact: true })).toBeVisible();
    await expect(hospital).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "账户与设置", exact: true })).not.toHaveClass(/active/);
    await expect(page.getByLabel("当前宠物")).toHaveValue(/.+/);
    await screenshot(page, "desktop");
    await page.reload();
    await expect(hospital).toHaveAttribute("aria-current", "page");
    await page.setViewportSize({ width: 850, height: 900 });
    await expect(hospital.locator(".nav-short")).toHaveText("医院");
    await expect(nav.getByRole("link", { name: "账户与设置", exact: true }).locator(".nav-short")).toHaveText("设置");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await screenshot(page, "compact");
  } else {
    await page.setViewportSize({ width: 390, height: 900 });
    const nav = page.getByRole("navigation", { name: "手机主要导航", exact: true });
    const more = nav.getByRole("button", { name: "更多", exact: true });
    const dialog = page.getByRole("dialog", { name: "更多", exact: true });
    await more.click();
    await expect(dialog.getByRole("link", { name: "医院查询", exact: true })).toBeVisible();
    await dialog.getByRole("link", { name: "医院查询", exact: true }).click();
    await expect(page).toHaveURL(/\/hospitals$/);
    await expect(dialog).not.toBeVisible();
    await expect(more).toHaveClass(/active/);
    await expect(page.getByRole("heading", { name: "医院查询", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await screenshot(page, "mobile");
    await more.click();
    await expect(dialog.getByRole("link", { name: "医院查询", exact: true })).toHaveAttribute("aria-current", "page");
    await page.mouse.move(0, 0);
    await screenshot(page, "more-mobile", false);
    await page.keyboard.press("Escape");
    await expect(more).toBeFocused();
    await expect(nav.getByRole("link")).toHaveCount(4);
  }
  expect(searches).toBe(0);
});

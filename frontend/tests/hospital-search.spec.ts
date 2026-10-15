import { test, expect, type Page } from "@playwright/test";

const region = (name: string, adcode: string, level: string, children: unknown[] = []) => ({ name, adcode, level, children });
const cities = [region("成都市", "510100", "city"), region("绵阳市", "510700", "city"), region("南充市", "511300", "city")];
const districts = [region("武侯区", "510107", "district"), region("锦江区", "510104", "district")];

async function prepare(page: Page) {
  const response = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await response.json()).access_token);
  await page.route("**/api/v1/hospitals/usage", route => route.fulfill({ json: { enabled: true, day_requests: 0, month_requests: 0, day_limit: 50, month_limit: 500, note: "测试响应" } }));
  await page.route("**/api/v1/hospitals/regions?**", route => {
    const keyword = new URL(route.request().url()).searchParams.get("keywords");
    const regions = keyword === "四川省" ? [region("四川省", "510000", "province", cities)] : keyword === "510100" || keyword === "成都市" ? [region("成都市", "510100", "city", districts)] : [];
    return route.fulfill({ json: { status: regions.length ? "ok" : "empty", regions, message: "测试响应", queried_at: "2026-10-14T06:00:00Z", cached: false } });
  });
  await page.goto("/hospitals");
  await expect(page.getByLabel("城市", { exact: true })).toBeVisible();
}

async function choose(page: Page) {
  await page.getByLabel("城市", { exact: true }).fill("四川省");
  await expect(page.getByRole("option", { name: /成都市/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /绵阳市/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /南充市/ })).toBeVisible();
  await page.getByLabel("城市", { exact: true }).press("ArrowDown");
  await page.getByLabel("城市", { exact: true }).press("Enter");
  await expect(page.getByLabel("城市", { exact: true })).toHaveValue("成都市");
  await page.getByLabel("区县（可选）", { exact: true }).focus();
  await expect(page.getByRole("option", { name: /武侯区/ })).toBeVisible();
  await page.getByLabel("区县（可选）", { exact: true }).fill("武侯");
  await expect(page.locator(".region-dropdown").getByRole("option")).toHaveCount(1);
  await page.getByRole("option", { name: /武侯区/ }).click();
}

async function image(page: Page) {
  return page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 600; canvas.height = 320;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#e8f1eb"; ctx.fillRect(0, 0, 600, 320);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 20;
    for (let x = 70; x < 600; x += 100) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 320); ctx.stroke(); }
    for (let y = 80; y < 320; y += 100) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(600, y); ctx.stroke(); }
    ctx.fillStyle = "#995268"; ctx.beginPath(); ctx.arc(300, 155, 18, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#ffffff"; ctx.font = "18px sans-serif"; ctx.fillText("A", 294, 162);
    ctx.fillStyle = "#332f39"; ctx.font = "20px sans-serif"; ctx.fillText("测试地图响应 / TEST FIXTURE", 110, 285);
    return canvas.toDataURL("image/png").split(",")[1];
  });
}

async function capture(page: Page, name: string, keepFocus = false) {
  await page.evaluate(async (keepFocus) => { await document.fonts.ready; if (!keepFocus && document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); }, keepFocus);
  await page.screenshot({ path: `../.impeccable/review/hospital-search-${name}.png`, fullPage: true, animations: "disabled" });
}

test("省市区联动、键盘选取、区域编码、独立地图与真实信息边界", async ({ page }, info) => {
  await prepare(page);
  if (info.project.name === "desktop") await page.setViewportSize({ width: 1440, height: 1000 });
  else await page.setViewportSize({ width: 390, height: 900 });
  await page.getByLabel("城市", { exact: true }).fill("四川省");
  await expect(page.getByRole("option", { name: /南充市/ })).toBeVisible();
  await capture(page, `candidates-${info.project.name}`, true);
  await choose(page);
  const png = await image(page);
  let mapCalls = 0;
  await page.route("**/api/v1/hospitals/map", route => { mapCalls++; return route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from(png, "base64") }); });
  await page.route("**/api/v1/hospitals/search", route => {
    expect(route.request().postDataJSON()).toMatchObject({ city: "成都市", district: "武侯区", region_adcode: "510107" });
    return route.fulfill({ json: { status: "ok", mode: "external", message: "测试响应 · 接诊能力未核实", queried_at: "2026-10-14T06:00:00Z", search_url: "https://uri.amap.com/search?keyword=test",
      map_preview_token: "test-token-012345678901234567890123456789", items: [{ id: "test-only", name: "测试响应医院 A", map_number: "A", address: "测试地址 · 武侯区", distance_m: null,
        phone: "028-12345678", opening_hours: "09:00–21:00", opening_status: "地图登记信息，出发前请电话核实", emergency: "待核实", species_capability: "待核实", qualification: "待核实",
        source: "高德地点搜索", source_url: "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch", registered_region: "四川省 · 成都市 · 武侯区",
        map_url: "https://uri.amap.com/search?keyword=test", navigation_url: "https://uri.amap.com/search?keyword=test", match_reason: "测试响应，用于界面验证" }] } });
  });
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.getByAltText("高德地图：编号对应下方医院候选")).toBeVisible();
  expect(await page.getByAltText("高德地图：编号对应下方医院候选").evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(600);
  await expect(page.locator(".hospital-row")).toContainText("暂无可靠评分");
  await page.getByText("资料来源与匹配依据").click();
  await expect(page.locator(".hospital-row details")).toContainText("电话核实");
  await page.getByText("资料来源与匹配依据").click();
  expect(mapCalls).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await capture(page, info.project.name);
  if (info.project.name === "desktop") { await page.setViewportSize({ width: 1031, height: 1244 }); await capture(page, "user-1031"); }
  await page.getByLabel("城市", { exact: true }).fill("绵阳");
  await expect(page.getByLabel("区县（可选）", { exact: true })).toHaveValue("");
  await expect(page.locator(".hospital-row")).toHaveCount(0);
  await expect(page.getByAltText("高德地图：编号对应下方医院候选")).toHaveCount(0);
});

test("区域候选失败可重试或手输，省份不直接查询医院", async ({ page }) => {
  await prepare(page);
  let searches = 0;
  page.on("request", request => { if (request.url().endsWith("/hospitals/search")) searches++; });
  await page.getByLabel("城市", { exact: true }).fill("四川省");
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("具体城市");
  expect(searches).toBe(0);
  let fail = true;
  await page.route("**/api/v1/hospitals/regions?**", route => route.fulfill({ json: { status: fail ? "unavailable" : "ok", regions: fail ? [] : [region("成都市", "510100", "city")], message: "区域额度不足，可手动输入" } }));
  await page.getByLabel("城市", { exact: true }).fill("成都市");
  await expect(page.getByRole("button", { name: "重试区域候选" })).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "重试区域候选" }).click();
  await expect(page.getByRole("option", { name: /成都市/ })).toBeVisible();
  await page.getByLabel("城市", { exact: true }).press("Escape");
  await expect(page.getByRole("listbox")).not.toBeVisible();
  await expect(page.getByLabel("城市", { exact: true })).toHaveValue("成都市");
});

test("地图失败不隐藏医院，手动重试后正确显示", async ({ page }, info) => {
  await prepare(page); await choose(page);
  const png = await image(page);
  let fail = true;
  await page.route("**/api/v1/hospitals/search", route => route.fulfill({ json: { status: "ok", mode: "external", items: [{ id: "test-only", name: "测试响应医院 A", map_number: "A", address: "测试地址", distance_m: null, phone: "028-12345678", opening_hours: "09:00–21:00", opening_status: "地图登记，未电话核实", emergency: "待核实", species_capability: "待核实", qualification: "待核实", source: "高德地点搜索", source_url: "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch", map_url: "https://uri.amap.com/search?keyword=test", navigation_url: "https://uri.amap.com/search?keyword=test", match_reason: "测试响应，用于验证地图失败时医院列表仍可用" }], message: "测试医院列表独立保留", queried_at: "2026-10-14T06:00:00Z", search_url: "https://uri.amap.com/search?keyword=test", map_preview_token: "test-token-012345678901234567890123456789" } }));
  await page.route("**/api/v1/hospitals/map", route => fail ? route.fulfill({ status: 503, json: { detail: "地图额度不足，医院列表仍可查看" } }) : route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from(png, "base64") }));
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.getByRole("button", { name: "重试地图" })).toBeVisible();
  await expect(page.locator(".hospital-results")).toContainText("测试医院列表独立保留");
  await expect(page.getByRole("heading", { name: /测试响应医院 A/ })).toBeVisible();
  await capture(page, `failure-${info.project.name}`);
  fail = false; await page.getByRole("button", { name: "重试地图" }).click();
  await expect(page.getByAltText("高德地图：编号对应下方医院候选")).toBeVisible();
});

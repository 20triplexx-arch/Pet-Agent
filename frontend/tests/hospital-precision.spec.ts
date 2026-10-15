import { test, expect, type Page } from "@playwright/test";

const region = (name: string, adcode: string, level: string, children: unknown[] = []) => ({ name, adcode, level, children });
const streets = [region("天彭街道", "510182", "street"), region("致和街道", "510182", "street"), region("九尺镇", "510182", "street")];
async function setup(page: Page) {
  const r = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await r.json()).access_token);
  await page.route("**/api/v1/hospitals/usage", route => route.fulfill({ json: { enabled: true, day_requests: 0, month_requests: 0, day_limit: 50, month_limit: 500 } }));
  await page.route("**/api/v1/hospitals/regions?**", route => {
    const q = new URL(route.request().url()).searchParams.get("keywords");
    const rows = q === "四川省" ? [region("四川省", "510000", "province", [region("成都市", "510100", "city")])] : q === "510100" ? [region("成都市", "510100", "city", [region("彭州市", "510182", "district"), region("武侯区", "510107", "district")])] : q === "510182" ? [region("彭州市", "510182", "district", streets)] : [];
    return route.fulfill({ json: { status: "ok", regions: rows, message: "测试响应" } });
  });
  await page.goto("/hospitals");
  await page.getByLabel("城市", { exact: true }).fill("四川省");
  await page.getByRole("option", { name: /成都市/ }).click();
  await page.getByLabel("区县（可选）", { exact: true }).click();
  await page.getByRole("option", { name: /彭州市/ }).click();
}

async function capture(page: Page, name: string, focus = false) {
  await page.evaluate(async (focus) => { await document.fonts.ready; if (!focus && document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); }, focus);
  await page.screenshot({ path: `../.impeccable/review/hospital-precision-${name}.png`, fullPage: true, animations: "disabled" });
}

test("区县后选择真实街道同码不合并，具体地点1公里与查询范围", async ({ page }, info) => {
  await setup(page);
  await page.setViewportSize(info.project.name === "desktop" ? { width: 1440, height: 1100 } : { width: 390, height: 900 });
  await page.getByLabel("街道 / 乡镇（可选）", { exact: true }).click();
  const options = page.getByRole("listbox", { name: "街道 / 乡镇（可选）候选", exact: true });
  await expect(options.getByRole("option")).toHaveCount(3);
  await capture(page, `street-${info.project.name}`, true);
  await page.getByRole("option", { name: /天彭街道/ }).click();
  await page.getByLabel("具体地点（可选）", { exact: true }).fill("测试路8号");
  await expect(page.getByLabel("附近查询范围", { exact: true })).toHaveValue("1");
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 600; canvas.height = 320;
    const c = canvas.getContext("2d")!; c.fillStyle = "#e8f1eb"; c.fillRect(0, 0, 600, 320);
    c.strokeStyle = "#ffffff"; c.lineWidth = 18;
    for (let x = 70; x < 600; x += 120) { c.beginPath(); c.moveTo(x,0); c.lineTo(x,320); c.stroke(); }
    for (let y = 100; y < 320; y += 100) { c.beginPath(); c.moveTo(0,y); c.lineTo(600,y); c.stroke(); }
    c.fillStyle = "#995268"; c.beginPath(); c.arc(300,150,18,0,Math.PI*2); c.fill();
    c.fillStyle = "#ffffff"; c.font = "18px sans-serif"; c.fillText("A",294,157);
    c.fillStyle = "#332f39"; c.font = "18px sans-serif"; c.fillText("测试地图 / TEST FIXTURE",140,285);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.route("**/api/v1/hospitals/map", route => route.fulfill({ contentType: "image/png", body: Buffer.from(png, "base64") }));
  await page.route("**/api/v1/hospitals/search", route => {
    expect(route.request().postDataJSON()).toMatchObject({ city: "成都市", district: "彭州市", street: "天彭街道", address_detail: "测试路8号", region_adcode: "510182", radius_km: 1 });
    return route.fulfill({ json: { status: "ok", mode: "external", message: "测试响应 · 接诊能力未核实", queried_at: "2026-10-14T07:00:00Z", search_url: "https://uri.amap.com/search?keyword=test", map_preview_token: "test-only-012345678901234567890123456789",
      scope_label: "四川省成都市彭州市天彭街道测试路8号附近 1 公里", scope_note: "以地图匹配点为中心，不是实时定位", items: [{ id: "test", map_number: "A", name: "测试响应附近医院", address: "四川省成都市彭州市测试路10号", phone: "028-12345678", distance_m: 200, opening_hours: "09:00–21:00", opening_status: "地图登记信息，出发前请电话核实", emergency: "待核实", species_capability: "待核实", qualification: "待核实", source: "高德地点搜索", source_url: "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch", map_url: "https://uri.amap.com/search?keyword=test", navigation_url: "https://uri.amap.com/search?keyword=test", match_reason: "测试响应" }] } });
  });
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.getByAltText("高德地图：编号对应下方医院候选")).toBeVisible();
  await expect(page.locator(".hospital-search-scope")).toContainText("测试路8号附近 1 公里");
  await expect(page.locator(".hospital-row")).toContainText("四川省成都市彭州市测试路10号");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await capture(page, info.project.name);
  if (info.project.name === "desktop") { await page.setViewportSize({ width: 1031, height: 1244 }); await capture(page, "user-1031"); }
  await page.getByLabel("区县（可选）", { exact: true }).fill("武侯区");
  await expect(page.getByLabel("街道 / 乡镇（可选）", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("具体地点（可选）", { exact: true })).toHaveValue("");
  await expect(page.locator(".hospital-row")).toHaveCount(0);
  await expect(page.getByText("查询状态已返回，请查看结果", { exact: true })).toHaveCount(0);
});

test("仅匹配到区县时停止附近查询，明确缺口并可缩小半径", async ({ page }, info) => {
  await setup(page);
  await page.getByLabel("具体地点（可选）", { exact: true }).fill("不完整地点");
  await page.getByLabel("附近查询范围", { exact: true }).selectOption("3");
  let requests = 0;
  await page.route("**/api/v1/hospitals/search", route => { requests++; return route.fulfill({ json: { status: "unavailable", mode: "map_link", items: [], message: "地图只匹配到较大的行政区，未按附近范围查询。请补充街道、小区或门牌。", queried_at: "2026-10-14T07:00:00Z", search_url: "https://uri.amap.com/search?keyword=test" } }); });
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText("未按附近范围查询");
  await expect(page.locator(".hospital-row")).toHaveCount(0);
  expect(requests).toBe(1);
  await capture(page, `blocked-${info.project.name}`);
});

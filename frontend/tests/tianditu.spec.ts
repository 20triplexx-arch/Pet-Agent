import { test, expect, type Page } from "@playwright/test";

const providers = [
  { provider: "amap", provider_name: "高德", enabled: true, day_requests: 2, month_requests: 4, day_limit: 50, month_limit: 500 },
  { provider: "tianditu", provider_name: "天地图", enabled: true, day_requests: 1, month_requests: 1, day_limit: 50, month_limit: 500 },
];
async function prepare(page: Page, enabled = true) {
  const response = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await response.json()).access_token);
  await page.route("**/api/v1/hospitals/usage", route => route.fulfill({ json: {
    provider: "auto", provider_name: "地图综合查询", enabled, region_enabled: false, day_requests: 3, month_requests: 5, day_limit: 100, month_limit: 1000,
    note: "测试响应：合计应用计数，不是供应商余额", providers: providers.map(p => ({ ...p, enabled })),
  } }));
  await page.goto("/hospitals");
  await expect(page.getByLabel("城市", { exact: true })).toBeVisible();
  await expect(page.getByLabel("医院查询来源", { exact: true })).toHaveCount(0);
}

function result(state: "combined" | "partial" | "unavailable" = "combined") {
  const both = state === "combined";
  const source = (provider: string, phone: string) => ({ provider, provider_name: provider === "amap" ? "高德" : "天地图", queried_at: "2026-10-14T07:00:00Z",
    name: "综合测试医院 / TEST FIXTURE", address: "四川省成都市彭州市测试路8号", phone, opening_hours: provider === "amap" ? "09:00-18:00" : "",
    source: "测试地图登记", source_url: provider === "amap" ? "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch" : "https://lbs.tianditu.gov.cn/server/search2.html" });
  const item = {
    id: "fixture-only", name: "综合测试医院 / TEST FIXTURE", address: "四川省成都市彭州市测试路8号", phone: "028-12345678", distance_m: 300,
    opening_hours: both ? "09:00-18:00" : "", opening_status: "测试响应：地图登记，出发前请电话核实", emergency: "待核实", species_capability: "待核实", qualification: "待核实",
    source: "测试地图登记", source_url: "https://lbs.tianditu.gov.cn/server/search2.html", rating_note: "测试响应：暂无可靠评分，不推测星级。",
    navigation_label: both ? "导航" : "按名称导航", navigation_url: "https://uri.amap.com/search?keyword=fixture", map_url: "https://uri.amap.com/search?keyword=fixture",
    match_reason: "测试响应：核对完整名称、地区及门牌；此条目仅用于浏览器测试。", map_number: both ? "A" : undefined,
    sources: both ? [source("amap", "028-12345678"), source("tianditu", "028-87654321")] : [source("tianditu", "028-12345678")],
    conflicts: both ? ["电话登记不一致，请分别核实来源记录"] : [],
  };
  return { provider: "auto", provider_name: "地图资料综合", mode: state === "unavailable" ? "map_link" : "external", status: state === "unavailable" ? "unavailable" : "ok",
    queried_at: "2026-10-14T07:00:00Z", message: state === "combined" ? "测试响应：已综合高德、天地图的资料。" : state === "partial" ? "测试响应：高德超时，保留天地图资料；部分来源未完成查询。" : "测试响应：未配置地图接口，未取得医院列表。",
    search_url: "https://uri.amap.com/search?keyword=fixture", map_preview_token: both ? "fixture-token" : null,
    map_note: both ? "测试响应：地图仅标注取得高德坐标的候选，其他候选可按名称查看地图。" : "测试响应：暂无可展示的高德位置资料，可按名称核对医院地图。",
    scope_label: state === "unavailable" ? undefined : "测试路8号附近 1 公里", scope_note: "测试响应：按匹配点范围，距离不是质量或行车距离。",
    agent_summary: { mode: "local_rules", merged_duplicates: both ? 1 : 0, unique_candidates: state === "unavailable" ? 0 : 1, basis: "测试响应：自动结合可用地图来源，核对重复资料，未做医疗质量排名。" },
    provider_results: providers.map(p => ({ provider: p.provider, provider_name: p.provider_name, status: state === "unavailable" ? "skipped" : both || p.provider === "tianditu" ? "ok" : "unavailable",
      item_count: state === "unavailable" ? 0 : both || p.provider === "tianditu" ? 1 : 0, queried_at: "2026-10-14T07:00:00Z",
      message: state === "unavailable" ? "未配置密钥，未调用" : both || p.provider === "tianditu" ? "测试响应：已取得候选" : "测试响应：查询超时，可手动重试" })),
    items: state === "unavailable" ? [] : [item] };
}

async function capture(page: Page, name: string) {
  await page.evaluate(async () => { await document.fonts.ready; if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: `../.impeccable/review/hospital-combined-${name}.png`, fullPage: true, animations: "disabled" });
}

async function mapFixture(page: Page) {
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas"); canvas.width = 600; canvas.height = 320;
    const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#e8f1eb"; ctx.fillRect(0, 0, 600, 320);
    ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 16;
    for (let x = 60; x < 600; x += 120) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 320); ctx.stroke(); }
    ctx.fillStyle = "#995268"; ctx.beginPath(); ctx.arc(300, 160, 18, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#ffffff"; ctx.font = "16px sans-serif"; ctx.fillText("A", 294, 166);
    ctx.fillStyle = "#436652"; ctx.font = "14px sans-serif"; ctx.fillText("TEST FIXTURE · not a real map", 15, 300);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.route("**/api/v1/hospitals/map", route => route.fulfill({ contentType: "image/png", body: Buffer.from(png, "base64") }));
}

test("一键综合：没有来源选择，来源差异可核对，地图仅标注高德，换宠物清空", async ({ page }, info) => {
  await prepare(page);
  await page.setViewportSize(info.project.name === "desktop" ? { width: 1440, height: 1100 } : { width: 390, height: 900 });
  await capture(page, `before-query-${info.project.name}`);
  await mapFixture(page);
  let calls = 0;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/hospitals/search", async route => {
    expect(route.request().postDataJSON().provider).toBeUndefined(); calls++;
    await gate; await route.fulfill({ json: result() });
  });
  await page.getByLabel("城市", { exact: true }).fill("成都市彭州市");
  await page.getByLabel("具体地点（可选）", { exact: true }).fill("测试路8号");
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.getByRole("button", { name: "查询医院", exact: true })).toBeDisabled();
  await capture(page, `loading-${info.project.name}`); release();
  await expect(page.locator(".hospital-row")).toContainText("资料来自高德、天地图");
  await expect(page.getByAltText("高德地图：编号对应下方医院候选")).toBeVisible();
  await expect(page.locator(".hospital-row")).toContainText("登记信息存在差异");
  expect(calls).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await capture(page, info.project.name);
  if (info.project.name === "desktop") { await page.setViewportSize({ width: 1031, height: 1244 }); await capture(page, "user-1031"); }
  await page.getByText("综合依据与查询状态", { exact: true }).click();
  await expect(page.locator(".hospital-results details").first()).toContainText("确认合并 1 条");
  await page.getByText("资料来源与匹配依据", { exact: true }).click();
  await expect(page.locator(".hospital-row details")).toContainText("028-87654321");
  await capture(page, `conflict-${info.project.name}`);
  await page.getByLabel("当前宠物").selectOption({ label: "豆包 · 狗" });
  await expect(page.locator(".hospital-row")).toHaveCount(0);
});

test("单家失败保留另一来源，只在用户重试时再次查询", async ({ page }, info) => {
  await prepare(page); let calls = 0;
  await page.route("**/api/v1/hospitals/search", route => { calls++; return route.fulfill({ json: result("partial") }); });
  await page.route("**/api/v1/hospitals/map", () => { throw new Error("No AMap positions, no static map request"); });
  await page.getByLabel("城市", { exact: true }).fill("成都市彭州市");
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText("部分来源未完成查询");
  await expect(page.locator(".hospital-row")).toContainText("资料来自天地图");
  await expect(page.locator(".hospital-map-frame")).toHaveCount(0);
  expect(calls).toBe(1);
  await page.getByText("综合依据与查询状态", { exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText("查询超时");
  await capture(page, `partial-${info.project.name}`);
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-row")).toBeVisible(); expect(calls).toBe(2);
  await page.getByLabel("城市", { exact: true }).fill("绵阳市");
  await expect(page.locator(".hospital-row")).toHaveCount(0);
});

test("没有密钥时不伪造医院或评分，保留手动地图入口", async ({ page }, info) => {
  await prepare(page, false);
  await page.route("**/api/v1/hospitals/search", route => route.fulfill({ json: result("unavailable") }));
  await expect(page.locator(".hospital-map-frame")).toHaveCount(0);
  await page.getByLabel("城市", { exact: true }).fill("成都市彭州市");
  await page.getByRole("button", { name: "查询医院", exact: true }).click();
  await expect(page.locator(".hospital-results")).toContainText("未取得医院列表");
  await expect(page.locator(".hospital-row")).toHaveCount(0);
  await expect(page.locator(".hospital-results").getByRole("link", { name: "打开高德搜索", exact: true })).toBeVisible();
  await page.getByText("综合依据与查询状态", { exact: true }).click();
  await capture(page, `no-key-${info.project.name}`);
});

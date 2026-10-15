import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  const login = await page.request.post("/api/v1/login/access-token", { form: { username: "demo@example.com", password: "Chongban2026!" } });
  await page.addInitScript(token => sessionStorage.setItem("chongban_token", token), (await login.json()).access_token);
});

test("checked paragraph appears before final, stops, and retracts on final failure", async ({ page }, info) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    let attempt = 0;
    window.fetch = async (input, init) => {
      if (String(input) !== "/api/v1/chat/stream") return original(input, init);
      const count = ++attempt;
      const encoder = new TextEncoder();
      let active = true;
      const sources = [{ id: "cat-scratching", title: "猫的抓挠行为", url: "https://icatcare.org/advice/", organization: "iCatCare", sections: ["替代方案"], evidence: [{ heading: "替代方案", text: "提供稳定的替代抓挠位置。" }] }];
      const body = new ReadableStream({
        start(controller) {
          const emit = (name: string, value: unknown) => { if (active) controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(value)}\n\n`)); };
          emit("accepted", { request_id: "browser-fixture" });
          setTimeout(() => emit("section", { index: 0, text: "先提供稳定的替代抓挠位置。", sources, question_ids: [1], model_used: "qwen3.7-flash-2026-07-15" }), 100);
          setTimeout(() => {
            if (!active) return;
            if (count === 1) emit("error", { detail: "后续段落检查未通过，回答未保存。", retract: true });
            else emit("final", { conversation_id: "stream-browser", answer: "先提供稳定的替代抓挠位置，再按反应调整。", mode: "live", sources, draft: null, message: { id: "stream-final", role: "assistant", content: "先提供稳定的替代抓挠位置，再按反应调整。", metadata_json: { mode: "live", model_used: "qwen3.7-flash-2026-07-15", sources } } });
            controller.close();
          }, 1600);
          init?.signal?.addEventListener("abort", () => { active = false; controller.error(new DOMException("Aborted", "AbortError")); });
        },
        cancel() { active = false; },
      });
      return new Response(body, { headers: { "content-type": "text/event-stream" } });
    };
  });
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("猫抓沙发怎么办？");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.user").last()).toContainText("猫抓沙发怎么办？");
  await expect(page.locator(".generating")).toContainText("先提供稳定的替代抓挠位置");
  await expect(page.getByRole("button", { name: "停止生成", exact: true })).toBeVisible();
  await page.screenshot({ path: `../.impeccable/review/chat-stream-${info.project.name}.png`, fullPage: false, animations: "disabled" });
  await expect(page.getByText("后续段落检查未通过，回答未保存。", { exact: true })).toBeVisible();
  await expect(page.locator(".generating")).toHaveCount(0);
  await expect(page.getByLabel("提问内容")).toHaveValue("猫抓沙发怎么办？");
  await page.getByRole("button", { name: "重试本次请求", exact: true }).click();
  await expect(page.locator(".generating")).toContainText("替代抓挠位置");
  await page.getByRole("button", { name: "停止生成", exact: true }).click();
  await expect(page.getByText("已停止生成，未完成的回答未保存。", { exact: true })).toBeVisible();
  await expect(page.locator(".generating")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("interrupted stream recovers committed result without another generation", async ({ page }) => {
  let calls = 0;
  const result = { conversation_id: "recovered", answer: "已核验的完整回答。", mode: "live", sources: [], draft: null,
    message: { id: "recovered-answer", role: "assistant", content: "已核验的完整回答。", metadata_json: { mode: "live", sources: [], model_used: "qwen3.8-flash" } } };
  await page.route("**/api/v1/chat/stream", route => { calls++; return route.fulfill({ contentType: "text/event-stream", body: 'event: accepted\ndata: {}\n\n' }); });
  await page.route("**/api/v1/chat/status", route => route.fulfill({ json: { state: "complete", response: result } }));
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("猫日常护理");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("已核验的完整回答");
  expect(calls).toBe(1);
  await expect(page.locator(".generating")).toHaveCount(0);
});

test("Chinese and emoji survive byte-split SSE with CRLF framing", async ({ page }) => {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      if (String(input) !== "/api/v1/chat/stream") return original(input, init);
      const answer = "中文🐾段落已完整核对。";
      const result = { conversation_id: "utf8-fixture", answer, sources: [], mode: "live", draft: null,
        message: { id: "utf8-final", role: "assistant", content: answer, metadata_json: { mode: "live", sources: [], model_used: "qwen3.8-flash" } } };
      const frames = [["accepted", {}], ["section", { index: 0, text: answer, sources: [], question_ids: [1] }], ["final", result]];
      const bytes = new TextEncoder().encode(frames.map(([event, data]) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`).join(""));
      return new Response(new ReadableStream({ start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      } }), { headers: { "content-type": "text/event-stream" } });
    };
  });
  await page.goto("/chat");
  await page.getByLabel("提问内容").fill("中文拆包验证");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.locator(".message.assistant").last()).toContainText("中文🐾段落已完整核对。");
  await expect(page.locator(".generating")).toHaveCount(0);
  expect(await page.locator(".message.assistant").last().textContent()).not.toContain("�");
});

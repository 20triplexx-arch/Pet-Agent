export type User = {
  id: string;
  email: string;
  full_name: string;
  timezone: string;
};
export type FieldIssue = { path: string; message: string };
export class ApiError extends Error {
  constructor(
    message: string,
    public fields: FieldIssue[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export type Pet = {
  id: string;
  name: string;
  species: string;
  capabilities?: Record<string, boolean>;
  breed: string | null;
  breed_id: string | null;
  breed_name: string | null;
  birthday: string | null;
  estimated_age_months: number | null;
  age_months: number | null;
  sex: string | null;
  neutered: boolean | null;
  weight: number | null;
  weight_date: string | null;
  diet: string | null;
  activity: string | null;
  environment: string | null;
  allergies: string | null;
  medical_history: string | null;
  vet_advice: string | null;
};
export type Task = {
  title: string;
  instructions: string;
  basis: string;
  recurrence: "daily" | "weekly";
  local_time: string;
  weekday: number;
};
export type Draft = { title: string; basis: string; tasks: Task[] };
export type Plan = Draft & {
  id: string;
  pet_id: string;
  status: string;
  revision: number;
  provenance?: {
    kind: string;
    amounts?: { name: string; daily_grams: number; per_meal_grams: number }[];
  } | null;
};
export type Reminder = {
  id: string;
  pet_id: string;
  task_id: string | null;
  title: string;
  recurrence: string;
  timezone: string;
  due_at: string;
  local_due: string;
  paused: boolean;
  completed: boolean;
  due: boolean;
};
export type Log = {
  id: string;
  kind: string;
  value: number | null;
  note: string;
  occurred_at: string;
};
export type Source = {
  id: string;
  title: string;
  url: string;
  organization: string;
  sections?: string[];
  evidence?: { heading: string; text: string }[];
};
export type Reply = {
  answer: string;
  mode: string;
  urgent: boolean;
  sources: Source[];
  draft: Draft | null;
  conversation_id: string;
  cards?: import("./care-api").ActionCard[];
  answer_depth?: string;
  questions?: string[];
  context_conflicts?: string[];
  context_budget_notes?: string[];
  model_selection?: ChatModel;
  model_used?: string | null;
};

export type ChatModel = { id: string; name: string; label: string; provider: string | null; available: boolean; mode: string; availability_reason?: string };
export type ChatModels = { default_id: string; options: ChatModel[] };
export type ChatSection = { index: number; text: string; sources: Source[]; question_ids: number[]; model_used?: string };
export type ChatReply = Reply & { message: Message };
export type ChatStatus = { state: "not_found" | "pending" | "unknown" | "failed" | "canceled" | "complete"; response?: ChatReply };

export async function streamChat(body: unknown, key: string, onSection: (section: ChatSection) => void, signal: AbortSignal): Promise<ChatReply> {
  const headers: Record<string, string> = { "Content-Type": "application/json", "Idempotency-Key": key };
  if (token()) headers.Authorization = "Bearer " + token();
  let serverError = false;
  try {
    const response = await fetch("/api/v1/chat/stream", { method: "POST", headers, body: JSON.stringify(body), signal });
    if (response.status === 401 && token()) {
      sessionStorage.removeItem("chongban_token");
      window.dispatchEvent(new Event("auth-expired"));
    }
    if (!response.ok) {
      serverError = true;
      const data = await response.json().catch(() => ({}));
      const fields: FieldIssue[] = response.status === 422 && Array.isArray(data.detail)
        ? data.detail.map((d: {loc?: (string | number)[]; msg?: string}) => ({path: (d.loc || []).filter(p => p !== "body").join("."), message: d.msg || "资料无效"})) : [];
      throw new ApiError(typeof data.detail === "string" ? data.detail : fields.map(f => f.message).join("；") || "回答未完成，请手动重试。", fields);
    }
    // A complete JSON response remains valid for older compatible servers.
    if (response.headers.get("content-type")?.includes("application/json")) return await response.json();
    if (!response.body) throw new Error("回答连接没有返回内容。");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let final: ChatReply | undefined;
    let expected = 0;
    const consume = (frame: string) => {
      let name = "";
      const data: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length) return;
      const value = JSON.parse(data.join("\n"));
      if (name === "section") {
        if (!Number.isInteger(value.index) || value.index !== expected || typeof value.text !== "string" || !Array.isArray(value.sources)) throw new Error("回答段落顺序无效。");
        expected++;
        onSection(value);
      } else if (name === "final") {
        if (!value.message || typeof value.answer !== "string") throw new Error("完整回答格式无效。");
        final = value;
      } else if (name === "error") {
        serverError = true;
        throw new ApiError(typeof value.detail === "string" ? value.detail : "回答检查未通过，请手动重试。");
      }
    };
    try {
      while (!final) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        if (buffer.length > 250000) throw new Error("回答传输超出范围。");
        let separator: RegExpExecArray | null;
        while ((separator = /\r?\n\r?\n/.exec(buffer))) {
          consume(buffer.slice(0, separator.index));
          buffer = buffer.slice(separator.index + separator[0].length);
          if (final) break;
        }
        if (done) break;
      }
      if (!final) throw new Error("回答连接中断。");
      return final;
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  } catch (error) {
    if ((error as Error).name === "AbortError" || serverError) throw error;
    // A connection loss never starts another generation. Recover an already committed reply.
    const status = await api<ChatStatus>("/chat/status", "GET", undefined, key).catch(() => null);
    if (status?.state === "complete" && status.response) return status.response;
    throw new Error(status?.state === "pending" || status?.state === "unknown"
      ? "连接已中断，请稍后点重试核对本次状态；不会重复生成。"
      : "回答未完成，请手动重试；本次输入已保留。");
  }
}

export type ModelQuota = {
  limits_enabled?: boolean;
  daily_limit: number | null;
  attempted_turns: number;
  failed_turns: number;
  remaining_turns: number | null;
  request_limit?: number | null;
  tool_calls_limit?: number | null;
  timezone: string;
  note: string;
};
export type Message = {
  id: string;
  role: string;
  content: string;
  metadata_json: Reply;
  created_at: string;
};
export type Article = {
  id: string;
  title: string;
  body: string;
  species: string[];
  life_stages: string[];
  topic: string;
  source_organization: string;
  source_url: string;
  source_version: string;
  published_at: string | null;
  ingested_at: string;
  updated_at: string;
  review_status: string;
  bookmarked: boolean;
  content_kind: "care" | "breed" | "food" | "supplies";
  breed_ids: string[];
  references: { organization: string; url: string; supports: string; version: string; checked_at: string }[];
};
export function token() {
  return sessionStorage.getItem("chongban_token");
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
  signal?: AbortSignal,
  format: "json" | "blob" = "json",
): Promise<T> {
  const headers: Record<string, string> = {};
  if (token()) headers.Authorization = "Bearer " + token();
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  let res: Response;
  try {
    res = await fetch("/api/v1" + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error("连接失败，请检查后端是否启动。重试会保留本次请求标识。");
  }
  if (res.status === 401 && token()) {
    sessionStorage.removeItem("chongban_token");
    window.dispatchEvent(new Event("auth-expired"));
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const fields: FieldIssue[] =
      res.status === 422 && Array.isArray(data.detail)
        ? data.detail
            .filter(
              (d: { loc?: unknown; msg?: unknown }) =>
                Array.isArray(d.loc) && typeof d.msg === "string",
            )
            .map((d: { loc: (string | number)[]; msg: string }) => ({
              path: d.loc
                .filter((part, index) => !(index === 0 && part === "body"))
                .join("."),
              message: d.msg.replace(/^Value error, /, ""),
            }))
        : [];
    throw new ApiError(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("；")
          : "请求失败，请重试",
      fields,
    );
  }
  return (format === "blob" ? await res.blob() : await res.json()) as T;
}
export async function login(email: string, password: string) {
  const res = await fetch("/api/v1/login/access-token", {
    method: "POST",
    body: new URLSearchParams({ username: email, password }),
  });
  if (!res.ok) throw new Error("邮箱或密码不正确，或服务未启动");
  const data = await res.json();
  sessionStorage.setItem("chongban_token", data.access_token);
}
export function petLabel(p: Pet) {
  return p.species === "cat" ? "猫" : p.species === "dog" ? "狗" : p.species;
}
export function dateText(value: string, tz: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: tz,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
export function localNow(tz: string) {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
  return parts.replace(" ", "T");
}

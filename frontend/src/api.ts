export type User = {
  id: string;
  email: string;
  full_name: string;
  timezone: string;
};
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
};
export type Reply = {
  answer: string;
  mode: string;
  urgent: boolean;
  sources: Source[];
  draft: Draft | null;
  conversation_id: string;
  cards?: import("./care-api").ActionCard[];
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
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("；")
          : "请求失败，请重试",
    );
  }
  return res.json();
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

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import {
  ArrowUpRight,
  ArrowLeft,
  Plus,
  Sparkles,
  Check,
  Clock,
  Heart,
  House,
  Utensils,
  Sprout,
  LogOut,
  BookOpen,
  Trash2,
  Pencil,
  Send,
  Bookmark,
  ShieldCheck,
  CalendarDays,
  Scale,
  Activity,
  ChevronRight,
} from "./icons";
import { Button } from "./components/ui/button";
import { useApp } from "./App";
import {
  api,
  dateText,
  localNow,
  petLabel,
  type Pet,
  type Reminder,
  type Plan,
  type Draft,
  type Log,
  type Reply,
  type Message,
  type Article,
  type Source,
} from "./api";
import { useAction, useEditorFocus, useRemote } from "./hooks";
import { AnswerContent } from "./answer-content";
import { ChatSupplement, type Supplement } from "./chat-supplement";
import type { ModelQuota } from "./api";
import type { MapUsage } from "./care-api";
import type { BreedList } from "./product-api";
import {
  Panel,
  State,
  Feedback,
  Empty,
  Sources,
  PageTitle,
  PetArtwork,
  PetPortrait,
  ArticleContent,
} from "./components";
const topics = [
  "养宠前准备",
  "新宠到家",
  "饮食与体重",
  "居住与清洁",
  "互动与训练",
  "生命阶段",
  "误区与危险",
  "健康与就医",
];
function NeedPet() {
  return (
    <Empty>
      先在右上角选择一只宠物，或<Link to="/pets">建立宠物档案</Link>
      。普通知识可以直接在 AI 对话中提问。
    </Empty>
  );
}
function ReminderList({
  items,
  reload,
  compact = false,
}: {
  items: Reminder[];
  reload: () => void;
  compact?: boolean;
}) {
  const { user } = useApp(),
    action = useAction();
  return (
    <>
      <Feedback action={action} />
      {!items.length ? (
        <Empty>还没有待办。生成照护计划，或创建你的第一条提醒。</Empty>
      ) : (
        <div className="task-list">
          {items.map((r) => (
            <div className="todo" key={r.id}>
              <Button
                className={"check-button " + (r.paused ? "done" : "")}
                aria-label={"完成 " + r.title}
                disabled={!r.due || action.busy}
                onClick={() =>
                  action.run(async (key) => {
                    await api(
                      "/reminders/" + r.id + "/complete",
                      "POST",
                      { occurrence_at: r.due_at },
                      key,
                    );
                    reload();
                  }, "本周期已打卡")
                }
              >
                <Check size={17} />
              </Button>
              <div className="todo-content">
                <strong>{r.title}</strong>
                <small>
                  {dateText(r.due_at, user.timezone)} ·{" "}
                  {r.recurrence === "once"
                    ? "一次性"
                    : r.recurrence === "daily"
                      ? "每日"
                      : "每周"}{" "}
                  {compact ? "" : " · " + r.timezone}
                </small>
              </div>
              <span className={"badge " + (r.due ? "orange" : "quiet")}>
                {r.completed
                  ? "已完成"
                  : r.paused
                    ? "已暂停"
                    : r.due
                      ? "已到期"
                      : "待到期"}
              </span>
              {!compact && !r.task_id && !r.completed && (
                <Button
                  className="text-button"
                  disabled={action.busy}
                  onClick={() =>
                    action.run(
                      async () => {
                        await api("/reminders/" + r.id + "/pause", "PATCH");
                        reload();
                      },
                      r.paused ? "已恢复" : "已暂停",
                    )
                  }
                >
                  {r.paused ? "恢复" : "暂停"}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
export function Home() {
  const { pet, user } = useApp(),
    navigate = useNavigate();
  const reminders = useRemote<Reminder[]>(
    pet ? "/reminders?pet_id=" + pet.id : null,
  );
  const today = new Intl.DateTimeFormat("zh-CN", {
    timeZone: user.timezone,
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());
  const due = (reminders.data || []).filter((r) => r.due);
  const petSummary = pet
    ? [
        pet.name,
        petLabel(pet),
        pet.age_months !== null ? pet.age_months + " 个月" : null,
        pet.weight !== null ? pet.weight + " kg" : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : "选择一只宠物，开始今天的照护。";
  return (
    <div className="home-page">
      <header className="home-welcome">
        <div className="home-welcome-copy">
          <h1>今天，好好陪伴</h1>
          <p className="home-pet-summary">{petSummary}</p>
          <div className="home-welcome-meta">
            <time>{today}</time>
            <Link to="/pets">
              {pet ? "管理档案" : "查看 / 建立档案"}
              <ChevronRight size={15} />
            </Link>
          </div>
        </div>
        {pet ? (
          <PetPortrait species={pet.species} />
        ) : (
          <PetArtwork className="home-companions" />
        )}
      </header>

      <div className="home-care-layout">
        <Panel className="home-today">
          <div className="section-heading">
            <h2>今日照护</h2>
            <Link to="/plans">
              全部待办{pet && due.length ? "（" + due.length + "）" : ""}
              <ArrowUpRight size={15} />
            </Link>
          </div>
          {!pet ? (
            <div className="home-empty">
              <CalendarDays size={28} aria-hidden="true" />
              <p>选好宠物，就能看到它的待办。</p>
              <Button className="primary" onClick={() => navigate("/pets")}>
                查看宠物档案
              </Button>
            </div>
          ) : (
            <>
              <State {...reminders} retry={reminders.reload} />
              {reminders.data &&
                (due.length ? (
                  <ReminderList
                    items={due.slice(0, 3)}
                    reload={reminders.reload}
                    compact
                  />
                ) : (
                  <div className="home-empty">
                    <Check size={28} aria-hidden="true" />
                    <p>暂时没有到期待办。</p>
                    <Button
                      className="primary"
                      onClick={() => navigate("/plans")}
                    >
                      安排照护计划
                    </Button>
                  </div>
                ))}
            </>
          )}
          <details className="home-reminder-note">
            <summary>提醒说明 · {user.timezone}</summary>
            <p>
              仅在页面打开或刷新时显示站内提醒，关闭应用后不会推送。待办按账户时区显示。
            </p>
          </details>
        </Panel>

        <section className="home-ask" aria-labelledby="home-ask-title">
          <h2 id="home-ask-title">想问什么？</h2>
          <div className="home-questions">
            {[
              ["怎么吃更合适？", "它每天应该怎么吃？"],
              ["照护计划怎么安排？", "帮我生成一份照护计划"],
              ["新宠到家要准备什么？", "新宠到家需要准备什么？"],
            ].map(([label, question]) => (
              <button
                key={question}
                onClick={() =>
                  navigate("/chat?q=" + encodeURIComponent(question))
                }
              >
                <span>{label}</span>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
          <Link className="home-chat-link" to="/chat">
            自由提问
            <ChevronRight size={15} />
          </Link>
        </section>
      </div>

      <section
        className="home-knowledge"
        aria-labelledby="home-knowledge-title"
      >
        <div className="section-heading">
          <h2 id="home-knowledge-title">照护知识</h2>
          <Link to="/knowledge">
            浏览全部
            <ArrowUpRight size={15} />
          </Link>
        </div>
        <div className="home-topics">
          {topics.slice(0, 4).map((topic, i) => {
            const Icon = [Heart, House, Utensils, Sprout][i];
            return (
              <Link
                to={"/knowledge?topic=" + encodeURIComponent(topic)}
                key={topic}
              >
                <Icon size={20} aria-hidden="true" />
                <span>{topic}</span>
              </Link>
            );
          })}
        </div>
      </section>
      <div className="home-health-note">
        <ShieldCheck size={18} aria-hidden="true" />
        <p>呼吸困难、排不出尿时，请及时联系兽医。</p>
        <Link to={"/knowledge?topic=" + encodeURIComponent("健康与就医")}>
          了解更多
        </Link>
      </div>
    </div>
  );
}
const blankPet = {
  name: "",
  species: "cat",
  breed: "",
  breed_id: "",
  birthday: "",
  estimated_age_months: "",
  sex: "unknown",
  neutered: "",
  diet: "",
  activity: "",
  environment: "",
  allergies: "",
  medical_history: "",
  vet_advice: "",
};
export function Pets() {
  const { pets, pet, refresh } = useApp(),
    action = useAction(),
    [editing, setEditing] = useState<Pet | null>(null),
    [show, setShow] = useState(false),
    [form, setForm] = useState<Record<string, string>>({ ...blankPet }),
    [other, setOther] = useState("");
  const breeds = useRemote<BreedList>(
    "/breeds?species=" + encodeURIComponent(form.species),
  );
  const breedCandidates = useRemote<BreedList>(
    form.breed
      ? "/breeds?species=" +
          encodeURIComponent(form.species) +
          "&q=" +
          encodeURIComponent(form.breed)
      : null,
  );
  const editor = useEditorFocus(show);
  const edit = (p: Pet | null, trigger: HTMLElement) => {
    editor.beginEditing(trigger);
    setEditing(p);
    setShow(true);
    setForm(
      p
        ? Object.fromEntries(
            Object.keys(blankPet).map((k) => [
              k,
              p[k as keyof Pet] === null ? "" : String(p[k as keyof Pet] ?? ""),
            ]),
          )
        : { ...blankPet },
    );
    setOther(
      p &&
        !["cat", "dog", "rabbit", "hamster", "guinea_pig"].includes(p.species)
        ? p.species
        : "",
    );
  };
  const update = (k: string, v: string) =>
    setForm((f) => ({
      ...f,
      [k]: v,
      ...(k === "species" || k === "breed" ? { breed_id: "" } : {}),
    }));
  return (
    <>
      <PageTitle
        title="每一只，都值得被了解"
        desc="未知信息可以留空。体重在照护记录中按日期保存。"
      >
        <Button
          className="primary"
          onClick={(e) => edit(null, e.currentTarget)}
        >
          <Plus size={17} />
          新增宠物
        </Button>
      </PageTitle>
      <Feedback action={action} />
      {!pets.length && !show ? (
        <Empty>还没有宠物档案，点击“新增宠物”开始。</Empty>
      ) : (
        <div className="pet-cards">
          {pets.map((p) => (
            <Panel
              key={p.id}
              className={pet?.id === p.id ? "selected-pet" : ""}
            >
              <div className="pet-card-head">
                <PetPortrait species={p.species} />
                <div className="pet-identity">
                  <h2>{p.name}</h2>
                  <p>
                    {p.breed_name || p.breed || "品种未知"} ·{" "}
                    {p.age_months === null
                      ? "年龄未知"
                      : p.age_months + " 个月"}{" "}
                    · {p.weight ? p.weight + " kg" : "体重待记录"}
                  </p>
                  <span
                    className={
                      "badge " + (pet?.id === p.id ? "green" : "quiet")
                    }
                  >
                    {petLabel(p)}
                    {pet?.id === p.id ? " · 当前宠物" : ""}
                  </span>
                </div>
              </div>
              {!p.capabilities?.knowledge && (
                <div className="note">
                  暂支持档案记录，该物种的个性化建议尚未上线。
                </div>
              )}
              <div className="pet-detail">
                <small>饮食</small>
                <span>{p.diet || "待补充"}</span>
                <small>生活环境</small>
                <span>{p.environment || "待补充"}</span>
              </div>
              <div className="button-row">
                {p.id === pet?.id && (
                  <Link className="care-link" to="/nutrition">
                    营养资料与方案 <ArrowUpRight size={14} />
                  </Link>
                )}
                <Link
                  className="care-link"
                  to={
                    "/knowledge?species=" +
                    p.species +
                    "&content_kind=breed" +
                    (p.breed_id ? "&breed_id=" + p.breed_id : "")
                  }
                >
                  品种知识 <ArrowUpRight size={14} />
                </Link>
                <Button onClick={(e) => edit(p, e.currentTarget)}>
                  <Pencil size={15} />
                  编辑
                </Button>
                <Button
                  className="danger-text"
                  disabled={action.busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        "删除 " +
                          p.name +
                          " 的档案及关联会话、计划、提醒与记录？",
                      )
                    )
                      action.run(async () => {
                        await api("/pets/" + p.id, "DELETE");
                        refresh();
                      }, "档案已删除");
                  }}
                >
                  <Trash2 size={15} />
                  删除
                </Button>
              </div>
            </Panel>
          ))}
        </div>
      )}
      {show && (
        <Panel className="form-panel">
          <div className="section-heading">
            <h2>{editing ? "编辑 " + editing.name : "建立新宠物档案"}</h2>
            <Button
              onClick={() => {
                setShow(false);
                editor.returnFocus();
              }}
            >
              取消
            </Button>
          </div>
          <form
            ref={editor.formRef}
            onSubmit={(e) => {
              e.preventDefault();
              const payload: Record<string, unknown> = {};
              for (const [k, v] of Object.entries(form)) payload[k] = v || null;
              payload.name = form.name;
              payload.species =
                form.species === "other" ? other.trim() : form.species;
              payload.estimated_age_months =
                form.estimated_age_months === ""
                  ? null
                  : Number(form.estimated_age_months);
              payload.neutered =
                form.neutered === "" ? null : form.neutered === "true";
              action.run(async (key) => {
                await api(
                  editing ? "/pets/" + editing.id : "/pets",
                  editing ? "PUT" : "POST",
                  payload,
                  key,
                );
                refresh();
                setShow(false);
              }, "宠物档案已保存");
            }}
          >
            <fieldset className="profile-group">
              <legend>基础信息</legend>
              <div className="form-grid">
                <label>
                  名称
                  <input
                    name="name"
                    required
                    maxLength={60}
                    value={form.name}
                    onChange={(e) => update("name", e.target.value)}
                  />
                </label>
                <label>
                  物种
                  <select
                    name="species"
                    value={
                      [
                        "cat",
                        "dog",
                        "rabbit",
                        "hamster",
                        "guinea_pig",
                      ].includes(form.species)
                        ? form.species
                        : "other"
                    }
                    onChange={(e) => update("species", e.target.value)}
                  >
                    <option value="cat">猫 · 已支持</option>
                    <option value="dog">狗 · 已支持</option>
                    <option value="rabbit">兔子 · 仅档案</option>
                    <option value="hamster">仓鼠 · 仅档案</option>
                    <option value="guinea_pig">豚鼠 · 仅档案</option>
                    <option value="other">其他具体物种 · 仅档案</option>
                  </select>
                </label>
                {!["cat", "dog", "rabbit", "hamster", "guinea_pig"].includes(
                  form.species,
                ) && (
                  <label>
                    具体物种 / 学名
                    <input
                      name="species"
                      required
                      value={other}
                      onChange={(e) => {
                        setOther(e.target.value);
                        update("species", "other");
                      }}
                      placeholder="如：虎皮鹦鹉 / Melopsittacus undulatus"
                    />
                  </label>
                )}
                <label>
                  品种
                  <input
                    name="breed"
                    value={form.breed}
                    onChange={(e) => update("breed", e.target.value)}
                  />
                </label>
                {["cat", "dog"].includes(form.species) && (
                  <label>
                    规范品种（确认后关联）
                    <select
                      name="breed_id"
                      value={form.breed_id}
                      onChange={(e) => update("breed_id", e.target.value)}
                    >
                      <option value="">未知 / 暂不关联</option>
                      {(breeds.data?.items || []).map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                    <small>
                      {breedCandidates.data?.note ||
                        "保留原始品种文字。家猫、田园犬和混种也有照护入口。"}
                    </small>
                    <State {...breeds} retry={breeds.reload} />
                  </label>
                )}
                <label>
                  生日
                  <input
                    name="birthday"
                    type="date"
                    value={form.birthday}
                    onChange={(e) => update("birthday", e.target.value)}
                  />
                </label>
                <label>
                  估计年龄（月，生日未知时）
                  <input
                    name="estimated_age_months"
                    type="number"
                    min="0"
                    max="600"
                    value={form.estimated_age_months}
                    onChange={(e) =>
                      update("estimated_age_months", e.target.value)
                    }
                  />
                </label>
                <label>
                  性别
                  <select
                    name="sex"
                    value={form.sex || "unknown"}
                    onChange={(e) => update("sex", e.target.value)}
                  >
                    <option value="unknown">未知</option>
                    <option value="male">雄性</option>
                    <option value="female">雌性</option>
                  </select>
                </label>
                <label>
                  绝育情况
                  <select
                    name="neutered"
                    value={form.neutered}
                    onChange={(e) => update("neutered", e.target.value)}
                  >
                    <option value="">未知</option>
                    <option value="true">已绝育</option>
                    <option value="false">未绝育</option>
                  </select>
                </label>
              </div>
            </fieldset>
            {[
              {
                title: "生活习惯",
                fields: [
                  ["diet", "当前饮食"],
                  ["activity", "活动情况"],
                  ["environment", "生活环境"],
                ],
              },
              {
                title: "健康资料",
                fields: [
                  ["allergies", "用户填写的过敏史"],
                  ["medical_history", "既往病史"],
                  ["vet_advice", "兽医建议（请保留原意）"],
                ],
              },
            ].map((group) => (
              <fieldset className="profile-group" key={group.title}>
                <legend>{group.title}</legend>
                <div className="form-grid">
                  {group.fields.map(([k, t]) => (
                    <label key={k}>
                      {t}
                      <textarea
                        name={k}
                        value={form[k]}
                        onChange={(e) => update(k, e.target.value)}
                        maxLength={2000}
                      />
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}
            <Button className="primary" disabled={action.busy} type="submit">
              保存档案
            </Button>
          </form>
        </Panel>
      )}
    </>
  );
}
function DraftEditor({
  draft,
  setDraft,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
}) {
  const change = (i: number, k: string, v: string | number) =>
    setDraft({
      ...draft,
      tasks: draft.tasks.map((t, n) => (n === i ? { ...t, [k]: v } : t)),
    });
  return (
    <>
      <label>
        计划名称
        <input
          name="title"
          aria-label="计划名称"
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          required
        />
      </label>
      <label>
        整体依据与适用条件
        <textarea
          name="basis"
          value={draft.basis}
          onChange={(e) => setDraft({ ...draft, basis: e.target.value })}
          required
        />
      </label>
      <div className="draft-tasks">
        {draft.tasks.map((t, i) => (
          <div className="draft-task" key={i}>
            <div className="form-grid">
              <label>
                任务名称
                <input
                  name={`tasks.${i}.title`}
                  aria-label={"任务名称 " + (i + 1)}
                  value={t.title}
                  onChange={(e) => change(i, "title", e.target.value)}
                  required
                />
              </label>
              <label>
                当地时间
                <input
                  name={`tasks.${i}.local_time`}
                  type="time"
                  value={t.local_time}
                  onChange={(e) => change(i, "local_time", e.target.value)}
                  required
                />
              </label>
              <label>
                重复
                <select
                  name={`tasks.${i}.recurrence`}
                  value={t.recurrence}
                  onChange={(e) => change(i, "recurrence", e.target.value)}
                >
                  <option value="daily">每日</option>
                  <option value="weekly">每周</option>
                </select>
              </label>
              {t.recurrence === "weekly" && (
                <label>
                  星期
                  <select
                    name={`tasks.${i}.weekday`}
                    value={t.weekday}
                    onChange={(e) =>
                      change(i, "weekday", Number(e.target.value))
                    }
                  >
                    {["一", "二", "三", "四", "五", "六", "日"].map((d, n) => (
                      <option key={n} value={n}>
                        星期{d}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            <label>
              操作说明
              <textarea
                name={`tasks.${i}.instructions`}
                value={t.instructions}
                onChange={(e) => change(i, "instructions", e.target.value)}
                required
              />
            </label>
            <label>
              依据与适用条件
              <textarea
                name={`tasks.${i}.basis`}
                value={t.basis}
                onChange={(e) => change(i, "basis", e.target.value)}
                required
              />
            </label>
            <Button
              className="danger-text"
              type="button"
              disabled={draft.tasks.length === 1}
              onClick={() =>
                setDraft({
                  ...draft,
                  tasks: draft.tasks.filter((_, n) => n !== i),
                })
              }
            >
              <Trash2 size={14} />
              移除此项
            </Button>
          </div>
        ))}
      </div>
      <Button
        type="button"
        onClick={() =>
          setDraft({
            ...draft,
            tasks: [
              ...draft.tasks,
              {
                title: "",
                instructions: "",
                basis: "由用户指定，请填入适用依据",
                recurrence: "daily",
                local_time: "09:00",
                weekday: 0,
              },
            ],
          })
        }
      >
        <Plus size={16} />
        添加任务
      </Button>
    </>
  );
}
export function Plans() {
  const navigate = useNavigate();
  const { pet, user } = useApp(),
    location = useLocation(),
    action = useAction();
  const plans = useRemote<Plan[]>(pet ? "/pets/" + pet.id + "/plans" : null),
    reminders = useRemote<Reminder[]>(
      pet ? "/reminders?pet_id=" + pet.id : null,
    );
  const [minutes, setMinutes] = useState(30),
    [draft, setDraft] = useState<Draft | null>(
      location.state?.petId === pet?.id ? location.state.draft : null,
    ),
    [sources, setSources] = useState<Source[]>([]),
    [editPlan, setEditPlan] = useState<Plan | null>(null);
  const [title, setTitle] = useState(""),
    [due, setDue] = useState(localNow(user.timezone)),
    [recurrence, setRecurrence] = useState("once");
  const editor = useEditorFocus(!!draft);
  const reload = () => {
    plans.reload();
    reminders.reload();
  };
  return (
    <>
      <PageTitle
        title="让照护，成为轻松的日常"
        desc={"预览后编辑保存 · 当地时间 " + user.timezone}
      />
      <Feedback action={action} />
      {!pet ? (
        <NeedPet />
      ) : (
        <>
          <Panel>
            <div className="section-heading">
              <h2>
                <Sparkles size={20} />为 {pet.name} 生成计划
              </h2>
              <span className="badge quiet">先预览，再保存</span>
            </div>
            <div className="inline-form">
              <label>
                每天可用于互动与整理的时间
                <input
                  name="available_minutes"
                  type="number"
                  min="5"
                  max="240"
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                />
              </label>
              <span>分钟</span>
              <Button
                className="primary"
                disabled={action.busy}
                onClick={(e) => {
                  editor.beginEditing(e.currentTarget);
                  action.run(async () => {
                    const r = await api<{ draft: Draft; sources: Source[] }>(
                      "/pets/" + pet.id + "/plans/preview",
                      "POST",
                      { available_minutes: minutes },
                    );
                    setDraft(r.draft);
                    setSources(r.sources);
                    setEditPlan(null);
                  }, "草稿已生成，请检查后保存");
                }}
              >
                <Sparkles size={17} />
                生成 / 重新调整草稿
              </Button>
            </div>
            <p className="muted small">
              使用最新档案。分钟数是用户时间分配，不代表宠物全天照护需求或运动处方。
            </p>
          </Panel>
          {draft && (
            <Panel className="form-panel">
              <h2>{editPlan ? "确认调整计划" : "照护计划草稿"}</h2>
              <div className="note">
                尚未保存。核对兽医建议与每项适用条件后再确认。
              </div>
              <form
                ref={editor.formRef}
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = editPlan
                    ? { ...draft, revision: editPlan.revision }
                    : draft;
                  action.run(async (key) => {
                    await api(
                      editPlan
                        ? "/plans/" + editPlan.id
                        : "/pets/" + pet.id + "/plans",
                      editPlan ? "PUT" : "POST",
                      data,
                      key,
                    );
                    setDraft(null);
                    setEditPlan(null);
                    reload();
                  }, "计划已保存，提醒已创建");
                }}
              >
                <DraftEditor draft={draft} setDraft={setDraft} />
                <Sources items={sources} />
                <div className="button-row">
                  <Button
                    className="primary"
                    disabled={action.busy}
                    type="submit"
                  >
                    {editPlan ? "确认更新计划" : "保存计划"}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => {
                      setDraft(null);
                      setEditPlan(null);
                      editor.returnFocus();
                    }}
                  >
                    取消
                  </Button>
                </div>
              </form>
            </Panel>
          )}
          <div className="two-col">
            <Panel>
              <div className="section-heading">
                <h2>
                  <CalendarDays size={20} />
                  已保存的计划
                </h2>
              </div>
              <State {...plans} retry={plans.reload} />
              {plans.data && !plans.data.length && (
                <Empty>计划草稿保存后会显示在这里。</Empty>
              )}
              {plans.data?.map((p) => (
                <div className="saved-plan" key={p.id}>
                  <div className="section-heading">
                    <h3>{p.title}</h3>
                    <span
                      className={
                        "badge " + (p.status === "active" ? "green" : "quiet")
                      }
                    >
                      {p.status === "active"
                        ? "执行中"
                        : p.status === "paused"
                          ? "已暂停"
                          : "已完成"}
                    </span>
                  </div>
                  <p>{p.basis}</p>
                  <ul>
                    {p.tasks.map((t, i) => (
                      <li key={i}>
                        <strong>{t.title}</strong>
                        <small>
                          {t.local_time} ·{" "}
                          {t.recurrence === "daily" ? "每日" : "每周"}
                        </small>
                        {p.provenance?.kind === "nutrition" && (
                          <span className="care-task-detail">
                            {t.instructions}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                  <div className="button-row">
                    <Button
                      onClick={(e) => {
                        if (p.provenance?.kind === "nutrition") {
                          navigate("/nutrition");
                          return;
                        }
                        editor.beginEditing(e.currentTarget);
                        setEditPlan(p);
                        setDraft({
                          title: p.title,
                          basis: p.basis,
                          tasks: p.tasks.map((t) => ({
                            title: t.title,
                            instructions: t.instructions,
                            basis: t.basis,
                            recurrence: t.recurrence,
                            local_time: t.local_time,
                            weekday: t.weekday,
                          })),
                        });
                        setSources([]);
                      }}
                    >
                      <Pencil size={14} />
                      编辑
                    </Button>
                    <Button
                      disabled={action.busy}
                      onClick={() =>
                        action.run(async () => {
                          await api("/plans/" + p.id + "/status", "PATCH", {
                            status: p.status === "active" ? "paused" : "active",
                          });
                          reload();
                        }, "计划状态已更新")
                      }
                    >
                      {p.status === "active" ? "暂停" : "恢复"}
                    </Button>
                    {p.status !== "completed" && (
                      <Button
                        disabled={action.busy}
                        onClick={() =>
                          action.run(async () => {
                            await api("/plans/" + p.id + "/status", "PATCH", {
                              status: "completed",
                            });
                            reload();
                          }, "计划已完成")
                        }
                      >
                        结束计划
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </Panel>
            <Panel>
              <h2>
                <Clock size={20} />
                自定义提醒
              </h2>
              <p className="muted small">
                站内提醒仅在打开或刷新页面时显示，关闭应用后不会推送。
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action.run(async (key) => {
                    await api(
                      "/pets/" + pet.id + "/reminders",
                      "POST",
                      {
                        title,
                        due_local: due,
                        recurrence,
                        timezone: user.timezone,
                      },
                      key,
                    );
                    setTitle("");
                    reminders.reload();
                  }, "提醒已创建");
                }}
              >
                <label>
                  待办事项
                  <input
                    name="title"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    maxLength={100}
                  />
                </label>
                <label>
                  到期当地时间
                  <input
                    name="due_local"
                    required
                    type="datetime-local"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                  />
                </label>
                <label>
                  重复方式
                  <select
                    name="recurrence"
                    value={recurrence}
                    onChange={(e) => setRecurrence(e.target.value)}
                  >
                    <option value="once">一次性</option>
                    <option value="daily">每日（当地日历）</option>
                    <option value="weekly">每周（同星期）</option>
                  </select>
                </label>
                <p className="small muted">
                  时区：{user.timezone} · 每周按所选日期的星期重复
                </p>
                <Button
                  className="primary"
                  disabled={action.busy}
                  type="submit"
                >
                  <Plus size={16} />
                  创建提醒
                </Button>
              </form>
            </Panel>
          </div>
          <Panel>
            <div className="section-heading">
              <h2>
                <Check size={20} />
                照护待办与打卡
              </h2>
              <Button onClick={reminders.reload}>刷新到期待办</Button>
            </div>
            <State {...reminders} retry={reminders.reload} />
            {reminders.data && (
              <ReminderList items={reminders.data} reload={reminders.reload} />
            )}
          </Panel>
        </>
      )}
    </>
  );
}
export function Chat() {
  const { pet } = useApp(),
    navigate = useNavigate(),
    [query] = useSearchParams(),
    action = useAction();
  const conversations = useRemote<{ id: string }[]>(
    "/conversations" + (pet ? "?pet_id=" + pet.id : ""),
  );
  const [cid, setCid] = useState<string | null>(null),
    [newChat, setNewChat] = useState(false),
    [text, setText] = useState(query.get("q") || ""),
    [minutes, setMinutes] = useState(30),
    [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [context, setContext] = useState<Supplement>({});
  const [depth, setDepth] = useState("auto");
  const [contextOpen, setContextOpen] = useState(false);
  const [copied, setCopied] = useState("");
  const [copyError, setCopyError] = useState("");
  const supplementRef = useRef<HTMLDetailsElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const quota = useRemote<ModelQuota>("/usage/quota");
  useEffect(() => { if (contextOpen) supplementRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [contextOpen]);
  const messageListRef = useRef<HTMLDivElement>(null);
  const chatRootRef = useRef<HTMLDivElement>(null);
  const followLatestRef = useRef(true);
  const positionHistoryRef = useRef(true);
  const lastMessageRef = useRef<string | null>(null);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const showLatest = () => {
    const list = messageListRef.current;
    const latest = list?.querySelector<HTMLElement>(".message:last-child");
    if (list && latest) {
      list.scrollTo({
        top:
          latest.getBoundingClientRect().top -
          list.getBoundingClientRect().top +
          list.scrollTop -
          24,
        behavior: "instant",
      });
    }
    setHasNewMessages(false);
  };
  useLayoutEffect(() => {
    if (!localMessages.length) return;
    const latestId = localMessages.at(-1)!.id;
    if (positionHistoryRef.current || followLatestRef.current) showLatest();
    else if (latestId !== lastMessageRef.current) setHasNewMessages(true);
    positionHistoryRef.current = false;
    lastMessageRef.current = latestId;
  }, [localMessages]);
  const messages = useRemote<Message[]>(
    cid ? "/conversations/" + cid + "/messages" : null,
  );
  useEffect(() => {
    if (!cid && !newChat && conversations.data?.length)
      setCid(conversations.data[0].id);
  }, [conversations.data, cid, newChat]);
  useEffect(() => {
    if (messages.data) setLocalMessages(messages.data);
  }, [messages.data]);
  const send = (value: string) => {
    if (value.length > 12000 || action.busy) return;
    followLatestRef.current = true;
    setHasNewMessages(false);
    action.run(
      async (key) => {
        const r = await api<Reply & { message: Message }>(
          "/chat",
          "POST",
          {
            pet_id: pet?.id || null,
            conversation_id: cid,
            text: value,
            available_minutes: minutes,
            context,
            answer_depth: depth,
          },
          key,
        );
        setCid(r.conversation_id);
        setNewChat(false);
        setText("");
        setLocalMessages((current) => [
          ...current,
          {
            id: key,
            role: "user",
            content: value,
            metadata_json: r,
            created_at: new Date().toISOString(),
          },
          r.message,
        ]);
        conversations.reload();
        messages.reload();
        quota.reload();
      },
      "",
      chatRootRef.current,
    );
  };
  return (
    <>
      <PageTitle
        title="有问题，和宠伴聊聊"
        desc={
          pet
            ? "当前对话仅使用 " + pet.name + " 的档案与适用知识"
            : "无需建档，也可以提问猫狗普通知识。"
        }
      />
      <div className="chat-layout deep-chat-layout" ref={chatRootRef}>
        <Panel className="chat-panel">
          <div className="chat-toolbar">
            <span className="badge green">{pet ? pet.name : "普通知识"}</span>
            <select
              aria-label="历史会话"
              value={cid || ""}
              onChange={(e) => {
                positionHistoryRef.current = true;
                followLatestRef.current = true;
                setHasNewMessages(false);
                setCid(e.target.value || null);
                setLocalMessages([]);
                setContext({});
                setContextOpen(false);
                setNewChat(!e.target.value);
              }}
            >
              <option value="">新会话</option>
              {conversations.data?.map((c, i) => (
                <option key={c.id} value={c.id}>
                  会话 {conversations.data!.length - i}
                </option>
              ))}
            </select>
            <Button
              onClick={() => {
                positionHistoryRef.current = true;
                followLatestRef.current = true;
                setHasNewMessages(false);
                setCid(null);
                setNewChat(true);
                setLocalMessages([]);
                setContext({});
                setContextOpen(false);
              }}
            >
              <Plus size={15} />
              新对话
            </Button>
          </div>
          <State
            loading={conversations.loading || messages.loading}
            error={conversations.error || messages.error}
            retry={() => {
              conversations.reload();
              messages.reload();
            }}
          />
          <div
            className="messages"
            ref={messageListRef}
            aria-live="polite"
            onScroll={(e) => {
              const list = e.currentTarget;
              followLatestRef.current =
                list.scrollHeight - list.scrollTop - list.clientHeight < 80;
              if (followLatestRef.current) setHasNewMessages(false);
            }}
          >
            {!localMessages.length && (
              <div className="chat-welcome">
                <h2>你好，我是宠伴。</h2>
                <p>可以问饮食、日常照护，或一起安排计划。</p>
                {[
                  "日常喂食要注意什么？",
                  "它的年龄适合怎样的照护？",
                  "帮我生成照护计划",
                ].map((q) => (
                  <Button key={q} onClick={() => setText(q)}>
                    {q}
                    <ArrowUpRight size={14} />
                  </Button>
                ))}
              </div>
            )}
            {localMessages.map((m) => (
              <div
                className={
                  "message " +
                  m.role +
                  (m.metadata_json.urgent ? " urgent" : "")
                }
                key={m.id}
              >
                <div className="message-label">
                  {m.role === "user" ? "你" : "宠伴"}
                  {m.role === "assistant" && (
                    <span className="badge quiet">
                      {m.metadata_json.mode === "demo"
                        ? "演示模式"
                        : m.metadata_json.mode === "live"
                          ? "模型回答"
                          : m.metadata_json.mode === "tools"
                            ? "工具执行结果"
                            : "规则 / 计划引擎"}
                    </span>
                  )}
                </div>
                {m.metadata_json.urgent && m.role === "assistant" && (
                  <strong className="urgent-title">紧急就医提示</strong>
                )}
                <div className="message-text">{m.role === "assistant" ? <AnswerContent text={m.content} sources={m.metadata_json.sources || []} /> : m.content}</div>
                {m.role === "assistant" && (
                  <>
                    <div className="answer-actions">
                      <Button type="button" className="text-button" onClick={async () => { try { await navigator.clipboard.writeText(m.content); setCopied(m.id); setCopyError(""); } catch { setCopyError("复制失败，可以选中回答文字手动复制。"); } }}>{copied === m.id ? "已复制" : "复制回答"}</Button>
                      <Button type="button" className="text-button" disabled={action.busy} onClick={() => { setText("请结合上面的资料，进一步说明适用条件、选择依据和具体执行步骤。"); setDepth("detailed"); inputRef.current?.focus(); }}>继续深入</Button>
                    </div>
                    {m.metadata_json.context_budget_notes?.length ? <p className="muted small">{m.metadata_json.context_budget_notes.join("；")}</p> : null}
                    <Sources items={m.metadata_json.sources || []} />
                    {m.metadata_json.cards?.map((card) =>
                      [
                        "/nutrition",
                        "/hospitals",
                        "/hospitals#visit-summary",
                        "/products",
                      ].includes(card.href) ||
                      /^\/knowledge(?:\/[^/?#]+)?(?:\?[^#]*)?$/.test(
                        card.href,
                      ) ? (
                        <div className="agent-action" key={card.type}>
                          <Link
                            to={card.href}
                            state={{ urgent: m.metadata_json.urgent }}
                          >
                            {card.title} <ArrowUpRight size={16} />
                          </Link>
                          {card.text && (
                            <details>
                              <summary>查看已整理摘要</summary>
                              <pre>{card.text}</pre>
                            </details>
                          )}
                        </div>
                      ) : null,
                    )}
                    {m.metadata_json.draft && (
                      <div className="draft-preview">
                        <strong>{m.metadata_json.draft.title}</strong>
                        <p>
                          {m.metadata_json.draft.tasks.length} 项任务 · 尚未保存
                        </p>
                        <Button
                          onClick={() =>
                            navigate("/plans", {
                              state: {
                                draft: m.metadata_json.draft,
                                petId: pet?.id,
                              },
                            })
                          }
                        >
                          预览 / 编辑后保存 <ArrowUpRight size={15} />
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
          {hasNewMessages && (
            <Button
              className="latest-message"
              onClick={() => {
                followLatestRef.current = true;
                showLatest();
              }}
            >
              查看最新回复
            </Button>
          )}
          <div className="care-link-row chat-care-links">
            <Link to="/nutrition">营养方案</Link>
            <Link to="/hospitals">医院与就医资料</Link>
          </div>
          <Feedback action={action} />
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) send(text.trim());
            }}
          >
            <textarea
              ref={inputRef}
              name="text"
              aria-label="提问内容"
              placeholder={
                pet
                  ? "问问关于 " + pet.name + " 的照护…"
                  : "例如：养猫前需要准备什么？"
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              required
              aria-describedby="chat-input-count"
              aria-invalid={text.length > 12000}
              disabled={action.busy}
            />
            <div className="chat-compose-controls">
              <label>深度<select aria-label="回答深度" value={depth} disabled={action.busy} onChange={e => setDepth(e.target.value)}><option value="auto">自动</option><option value="brief">简短</option><option value="detailed">深入</option></select></label>
              <Button type="button" disabled={action.busy} aria-expanded={contextOpen} aria-controls="chat-supplement" onClick={() => setContextOpen(!contextOpen)}>补充资料</Button>
              <span id="chat-input-count" role={text.length > 12000 ? "alert" : undefined} className={text.length > 12000 ? "input-over-limit" : ""}>{text.length} / 12000 字{text.length > 12000 ? "，请分次发送" : ""}</span>
            </div>
            <div>
              <span>健康问题提供观察与就医准备建议</span>
              <Button className="primary" disabled={action.busy || text.length > 12000} type="submit">
                <Send size={16} />
                发送
              </Button>
            </div>
            {copyError && <p role="status">{copyError}</p>}
          </form>
        </Panel>
        <div>
            <details ref={supplementRef} className="chat-supplement" id="chat-supplement" open={contextOpen} onToggle={e => setContextOpen(e.currentTarget.open)}>
              <summary>补充本次照护资料</summary>
              <ChatSupplement value={context} change={setContext} busy={action.busy} />
              <Button type="button" onClick={() => { setContextOpen(false); inputRef.current?.focus(); }}>回到提问</Button>
            </details>
          <Panel className="chat-context">
            <details className="context-details" open>
              <summary>当前照护背景</summary>
              {pet ? (
                <>
                  <strong>
                    {pet.name} · {petLabel(pet)}
                  </strong>
                  <dl>
                    <dt>年龄</dt>
                    <dd>
                      {pet.age_months === null
                        ? "未知"
                        : pet.age_months + " 个月"}
                    </dd>
                    <dt>最新体重</dt>
                    <dd>{pet.weight ? pet.weight + " kg" : "未记录"}</dd>
                    <dt>饮食</dt>
                    <dd>{pet.diet || "待补充"}</dd>
                    <dt>兽医建议</dt>
                    <dd>{pet.vet_advice || "未填写"}</dd>
                  </dl>
                  <Link to="/pets">
                    完善档案 <ArrowUpRight size={14} />
                  </Link>
                </>
              ) : (
                <p>未选择宠物。回答不会使用其他宠物档案。</p>
              )}
              <label>
                计划可用时间（分钟）
                <input
                  name="available_minutes"
                  type="number"
                  min="5"
                  max="240"
                  value={minutes}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                />
              </label>
              <div className="note">
                演示模式采用真实检索和受控模板。真实模型需在服务端配置，不会自动产生费用。
              </div>
            </details>
          </Panel>
        </div>
      </div>
    </>
  );
}
export function Knowledge() {
  const { pet } = useApp(),
    location = useLocation(),
    params = useParams(),
    [query] = useSearchParams(),
    action = useAction();
  const [q, setQ] = useState(""),
    [species, setSpecies] = useState(
      query.get("species") || pet?.species || "",
    ),
    [topic, setTopic] = useState(query.get("topic") || ""),
    [favorites, setFavorites] = useState(false),
    [contentKind, setContentKind] = useState(query.get("content_kind") || ""),
    [breedId, setBreedId] = useState(
      query.get("breed_id") ||
        (query.get("species") && query.get("species") !== pet?.species
          ? ""
          : pet?.breed_id || ""),
    ),
    [lifeStage, setLifeStage] = useState(""),
    [visible, setVisible] = useState(24);
  const breeds = useRemote<BreedList>(
    "/breeds?" + new URLSearchParams({ species }).toString(),
  );
  useEffect(() => {
    setVisible(24);
  }, [species, q, topic, favorites, contentKind, breedId, lifeStage]);
  const path =
    "/knowledge?" +
    new URLSearchParams({
      q,
      species,
      topic,
      favorites: String(favorites),
      content_kind: contentKind,
      breed_id: breedId,
      life_stage: lifeStage,
    }).toString();
  const items = useRemote<Article[]>(!params.id ? path : null),
    detail = useRemote<Article>(params.id ? "/knowledge/" + params.id : null);
  useEffect(() => {
    if (!detail.data || !location.hash) return;
    try { document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({ block: "start" }); } catch { /* Invalid hash leaves the article readable. */ }
  }, [detail.data, location.hash]);
  const mark = (a: Article) =>
    action.run(
      async () => {
        await api(
          "/knowledge/" + a.id + "/bookmark",
          a.bookmarked ? "DELETE" : "PUT",
        );
        items.reload();
        detail.reload();
      },
      a.bookmarked ? "已取消收藏" : "已收藏",
    );
  if (params.id)
    return (
      <>
        <Link className="back-link" to="/knowledge">
          <ArrowLeft size={17} /> 返回知识库
        </Link>
        <State {...detail} retry={detail.reload} />
        <Feedback action={action} />
        {detail.data && (
          <Panel className="article-detail">
            <span className="article-topic">{detail.data.topic}</span>
            <h1>{detail.data.title}</h1>
            <div className="button-row">
              <span className="badge green">
                {detail.data.species
                  .map((s) => (s === "cat" ? "猫" : s === "dog" ? "狗" : s))
                  .join(" / ")}
              </span>
              <span className="badge quiet">
                适用阶段：
                {detail.data.life_stages
                  .map(
                    (s) =>
                      (
                        ({
                          all: "全部（请结合正文条件）",
                          kitten: "幼猫",
                          young_adult: "年轻成年",
                          mature_adult: "成熟成年",
                          senior: "老年",
                        }) as Record<string, string>
                      )[s] || s,
                  )
                  .join(" / ")}
              </span>
              <Button onClick={() => mark(detail.data!)}>
                <Bookmark
                  size={16}
                  weight={detail.data.bookmarked ? "fill" : "regular"}
                />
                {detail.data.bookmarked ? "已收藏" : "收藏"}
              </Button>
            </div>
            <ArticleContent body={detail.data.body} />
            <div className="source-card">
              <h3>资料来源与审核信息</h3>
              <p>来源机构：{detail.data.source_organization}</p>
              <p>
                版本：{detail.data.source_version} · 发布日期：
                {detail.data.published_at || "原页未标明"}
              </p>
              <p>
                收录：{detail.data.ingested_at} · 摘要更新：
                {detail.data.updated_at}
              </p>
              <p>审核状态：编辑摘要，未经兽医审核</p>
              <a href={detail.data.source_url} target="_blank" rel="noreferrer">
                查看专业来源原文 ↗
              </a>
              {detail.data.references?.map((r, i) => (
                <div className="article-reference" key={r.url + i}>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.organization} ↗
                  </a>
                  <p>支持内容：{r.supports}</p>
                  <small>
                    {r.version} · 核对 {r.checked_at}
                  </small>
                </div>
              ))}
              <small>
                中文内容为公开资料的原创摘要与应用操作清单，具体建议需结合宠物个体和兽医意见。
              </small>
            </div>
          </Panel>
        )}
      </>
    );
  return (
    <>
      <PageTitle
        title="了解多一点，照护安心一点"
        desc="先选猫或狗，再了解品种、食物与日常用品。"
      >
        <Link className="care-link" to="/products">
          比较具体食品与用品 <ArrowUpRight size={15} />
        </Link>
      </PageTitle>
      <Feedback action={action} />
      <div className="knowledge-domains" aria-label="知识分类">
        {[
          ["", "全部"],
          ["care", "通用照护"],
          ["breed", "品种"],
          ["food", "食物"],
          ["supplies", "用品"],
        ].map(([value, label]) => (
          <Button
            key={value}
            aria-pressed={contentKind === value}
            className={contentKind === value ? "primary" : ""}
            onClick={() => {
              setContentKind(value);
              setTopic("");
            }}
          >
            {label}
          </Button>
        ))}
      </div>
      <Panel className="filters">
        <label className="search-label">
          搜索知识
          <input
            aria-label="搜索知识"
            placeholder="搜索饮食、互动、猫砂…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label>
          适用物种
          <select
            aria-label="知识物种"
            value={species}
            onChange={(e) => {
              setSpecies(e.target.value);
              setBreedId("");
              setLifeStage("");
            }}
          >
            <option value="">猫与狗</option>
            <option value="cat">猫</option>
            <option value="dog">狗</option>
            {pet && !pet.capabilities?.knowledge && (
              <option value={pet.species}>{pet.species} · 暂未支持</option>
            )}
          </select>
        </label>
        <label>
          照护主题
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">全部主题</option>
            {[...topics, "品种照护", "食物选购", "用品选购"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          品种筛选
          <select value={breedId} onChange={(e) => setBreedId(e.target.value)}>
            <option value="">全部品种 / 通用知识</option>
            {breeds.data?.items.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          生命阶段
          <select
            value={lifeStage}
            onChange={(e) => setLifeStage(e.target.value)}
          >
            <option value="">全部阶段</option>
            <option value={species === "dog" ? "puppy" : "kitten"}>幼龄</option>
            <option value="young_adult">年轻成年</option>
            <option value="mature_adult">成熟成年</option>
            <option value="senior">老年</option>
          </select>
        </label>
        <Button
          className={favorites ? "primary" : ""}
          onClick={() => setFavorites(!favorites)}
        >
          <Bookmark size={16} />
          {favorites ? "我的收藏" : "查看收藏"}
        </Button>
      </Panel>
      <State {...breeds} retry={breeds.reload} />
      <State {...items} retry={items.reload} />
      {items.data && !items.data.length && (
        <Empty>
          暂无匹配资料，请尝试其他关键词。未支持物种不能套用猫狗建议。
        </Empty>
      )}
      <div className="knowledge-grid">
        {items.data?.slice(0, visible).map((a) => (
          <article key={a.id} className="knowledge-row">
            <div className="knowledge-row-content">
              <Link to={"/knowledge/" + a.id}>
                <h3>{a.title}</h3>
              </Link>
              <p className="article-excerpt">
                {a.body.replace(/^## .*\n/gm, "").split(/\n\s*\n/)[0]}
              </p>
              <div className="article-meta">
                <span>
                  {a.topic} ·{" "}
                  {a.species
                    .map((s) => (s === "cat" ? "猫" : "狗"))
                    .join(" / ")}
                </span>
                <span>{a.source_organization}</span>
                <small>更新 {a.updated_at} · 编辑摘要，未兽医审核</small>
              </div>
            </div>
            <div className="knowledge-row-actions">
              <button
                className="bookmark-button"
                aria-label={"收藏 " + a.title}
                aria-pressed={a.bookmarked}
                disabled={action.busy}
                onClick={() => mark(a)}
              >
                <Bookmark
                  size={21}
                  weight={a.bookmarked ? "fill" : "regular"}
                />
              </button>
              <Link to={"/knowledge/" + a.id} className="read-link">
                阅读详情 <ArrowUpRight size={16} />
              </Link>
            </div>
          </article>
        ))}
      </div>
      {items.data && visible < items.data.length && (
        <Button onClick={() => setVisible((v) => v + 24)}>
          继续阅读（还有 {items.data.length - visible} 篇）
        </Button>
      )}
    </>
  );
}
const kindNames: Record<string, string> = {
  weight: "体重",
  diet: "饮食",
  activity: "活动",
  grooming: "护理",
  observation: "异常观察",
};
export function Logs() {
  const { pet, user, refresh } = useApp(),
    action = useAction(),
    logs = useRemote<Log[]>(pet ? "/pets/" + pet.id + "/logs" : null),
    completions = useRemote<
      {
        id: string;
        title: string;
        completed_at: string;
        occurrence_at: string;
      }[]
    >(pet ? "/pets/" + pet.id + "/completions" : null);
  const [kind, setKind] = useState("weight"),
    [value, setValue] = useState(""),
    [note, setNote] = useState(""),
    [when, setWhen] = useState(localNow(user.timezone));
  const weights = (logs.data || [])
    .filter((l) => l.kind === "weight")
    .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
  return (
    <>
      <PageTitle
        title="记录日常，看见它的变化"
        desc={
          pet
            ? pet.name + " 的独立照护历史 · " + user.timezone
            : "体重趋势、照护记录与打卡历史"
        }
      />
      <Feedback action={action} />
      {!pet ? (
        <NeedPet />
      ) : (
        <>
          <div className="two-col logs-grid">
            <Panel>
              <h2>
                <Scale size={20} />
                体重趋势
              </h2>
              <State {...logs} retry={logs.reload} />
              {weights.length ? (
                <WeightChart weights={weights} tz={user.timezone} />
              ) : (
                !logs.loading && <Empty>记录第一笔体重，开始关注变化。</Empty>
              )}
            </Panel>
            <Panel>
              <h2>
                <Plus size={20} />
                添加照护记录
              </h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  action.run(async (key) => {
                    await api(
                      "/pets/" + pet.id + "/logs",
                      "POST",
                      {
                        kind,
                        value: kind === "weight" ? Number(value) : null,
                        note,
                        occurred_at: await localToUTC(when, user.timezone),
                      },
                      key,
                    );
                    setNote("");
                    setValue("");
                    logs.reload();
                    refresh();
                  }, "照护记录已保存");
                }}
              >
                <div className="form-grid">
                  <label>
                    记录类型
                    <select
                      name="kind"
                      value={kind}
                      onChange={(e) => setKind(e.target.value)}
                    >
                      {Object.entries(kindNames).map(([k, t]) => (
                        <option key={k} value={k}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </label>
                  {kind === "weight" && (
                    <label>
                      体重（kg）
                      <input
                        name="value"
                        aria-label="体重公斤"
                        type="number"
                        step="0.01"
                        min="0.01"
                        max="200"
                        required
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                      />
                    </label>
                  )}
                </div>
                <label>
                  发生时间（{user.timezone}）
                  <input
                    name="occurred_at"
                    type="datetime-local"
                    required
                    value={when}
                    onChange={(e) => setWhen(e.target.value)}
                  />
                </label>
                <label>
                  记录内容
                  <textarea
                    name="note"
                    value={note}
                    required={kind !== "weight"}
                    maxLength={3000}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="记录食欲、活动或观察到的变化…"
                  />
                </label>
                <Button
                  className="primary"
                  disabled={action.busy}
                  type="submit"
                >
                  保存记录
                </Button>
              </form>
              <p className="muted small">
                异常观察不会自动作出诊断。有紧急症状时优先联系兽医。
              </p>
            </Panel>
          </div>
          <Panel>
            <h2>
              <Activity size={20} />
              照护历史
            </h2>
            <State {...logs} retry={logs.reload} />
            {logs.data && !logs.data.length && (
              <Empty>还没有记录，今天从一件小事开始。</Empty>
            )}
            <div className="journal-list">
              {logs.data?.map((l) => (
                <div key={l.id} className="journal-row">
                  <span className="journal-kind" aria-hidden="true">
                    {(() => {
                      const Icon =
                        (
                          {
                            weight: Scale,
                            diet: Utensils,
                            activity: Activity,
                            grooming: Heart,
                            observation: ShieldCheck,
                          } as Record<string, typeof Scale>
                        )[l.kind] || Heart;
                      return <Icon size={20} />;
                    })()}
                  </span>
                  <div>
                    <strong>
                      {kindNames[l.kind]}
                      {l.value ? " · " + l.value + " kg" : ""}
                    </strong>
                    <p>{l.note || "未填写备注"}</p>
                    <small>{dateText(l.occurred_at, user.timezone)}</small>
                  </div>
                  <Button
                    className="danger-text"
                    aria-label={"删除记录 " + l.id}
                    onClick={() => {
                      if (window.confirm("删除这条记录？"))
                        action.run(async () => {
                          await api("/logs/" + l.id, "DELETE");
                          logs.reload();
                          refresh();
                        }, "记录已删除");
                    }}
                  >
                    <Trash2 size={15} />
                  </Button>
                </div>
              ))}
            </div>
          </Panel>
          <Panel>
            <h2>
              <Check size={20} />
              任务完成历史
            </h2>
            <State {...completions} retry={completions.reload} />
            {completions.data && !completions.data.length && (
              <Empty>完成一项到期待办后，打卡会显示在这里。</Empty>
            )}
            {completions.data?.map((c) => (
              <div className="journal-row" key={c.id}>
                <Check size={18} />
                <div>
                  <strong>{c.title}</strong>
                  <small>
                    周期 {dateText(c.occurrence_at, user.timezone)} · 完成{" "}
                    {dateText(c.completed_at, user.timezone)}
                  </small>
                </div>
              </div>
            ))}
          </Panel>
        </>
      )}
    </>
  );
}
async function localToUTC(local: string, timezone: string): Promise<string> {
  const r = await api<{ utc: string }>("/time/convert", "POST", {
    local,
    timezone,
  });
  return r.utc;
}
function WeightChart({ weights, tz }: { weights: Log[]; tz: string }) {
  const chartRef = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(560);
  useLayoutEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const measure = () => setWidth(chart.getBoundingClientRect().width);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(chart);
    return () => observer.disconnect();
  }, []);
  const values = weights.map((w) => w.value!),
    min = Math.min(...values) - 0.2,
    max = Math.max(...values) + 0.2;
  const dates = weights.map((w) => new Date(w.occurred_at).getTime()),
    start = dates[0],
    span = dates.at(-1)! - start;
  const points = weights.map((w, i) => [
    44 + (span === 0 ? 0 : ((dates[i] - start) / span) * (width - 60)),
    160 - ((w.value! - min) / (max - min)) * 115,
  ]);
  return (
    <>
      <div className="weight-current">
        <strong>
          {values.at(-1)}
          <small>kg</small>
        </strong>
        <span>最近一次记录</span>
      </div>
      <svg
        className="weight-chart"
        ref={chartRef}
        viewBox={`0 0 ${width} 215`}
        role="img"
        aria-label="体重趋势，按实际记录日期显示"
      >
        {[0, 1, 2].map((n) => (
          <g key={n}>
            <line
              x1="44"
              x2={width - 16}
              y1={45 + n * 57.5}
              y2={45 + n * 57.5}
            />
            <text x="3" y={49 + n * 57.5}>
              {(max - (n * (max - min)) / 2).toFixed(1)}
            </text>
          </g>
        ))}
        <polyline
          points={points.map((p) => p.join(",")).join(" ")}
          fill="none"
        />
        {points.map(([x, y], i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="4" />
            <title>
              {dateText(weights[i].occurred_at, tz)} · {weights[i].value}kg
            </title>
            {(i === 0 || i === points.length - 1) && (
              <text x={x} y="195" textAnchor={i === 0 ? "start" : "end"}>
                {dateText(weights[i].occurred_at, tz).slice(0, 5)}
              </text>
            )}
          </g>
        ))}
      </svg>
      <p className="muted small">
        体重变化需结合体况和健康状态评估。此趋势不自动判断正常或异常。
      </p>
    </>
  );
}
export function SettingsPage() {
  const { user, refreshUser, logout } = useApp(),
    [name, setName] = useState(user.full_name),
    [timezone, setTimezone] = useState(user.timezone),
    action = useAction();
  const status = useRemote<{ mode: string; model: string | null }>("/status"),
    mapUsage = useRemote<MapUsage>("/hospitals/usage"),
    quota = useRemote<ModelQuota>("/usage/quota"),
    usage = useRemote<{
      requests: number;
      input_tokens: number;
      output_tokens: number;
    }>("/usage");
  return (
    <>
      <PageTitle
        title="你的宠伴，按你的习惯"
        desc="账户信息、时区与模型运行状态。"
      />
      <Feedback action={action} />
      <div className="two-col">
        <Panel>
          <h2>账户与时间设置</h2>
          <p className="muted account-email">{user.email}</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action.run(async () => {
                await api("/users/me", "PATCH", { full_name: name, timezone });
                refreshUser();
              }, "设置已保存");
            }}
          >
            <label>
              昵称
              <input
                name="full_name"
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              IANA 时区
              <input
                name="timezone"
                list="timezones"
                value={timezone}
                required
                onChange={(e) => setTimezone(e.target.value)}
              />
              <datalist id="timezones">
                {[
                  "Asia/Shanghai",
                  "Asia/Tokyo",
                  "America/New_York",
                  "Europe/London",
                  "Australia/Sydney",
                  "UTC",
                ].map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </datalist>
            </label>
            <p className="muted small">
              显示按账户时区转换。已有重复提醒继续使用创建时的时区，编辑计划可用新时区重新安排。
            </p>
            <Button className="primary" disabled={action.busy} type="submit">
              保存设置
            </Button>
          </form>
          <div className="account-actions">
            <Button onClick={logout} disabled={action.busy}>
              <LogOut size={16} />
              退出登录
            </Button>
          </div>
        </Panel>
        <Panel>
          <h2>
            <Sparkles size={20} />
            模型与费用
          </h2>
          <State {...status} retry={status.reload} />
          {status.data && (
            <>
              <span className="badge">
                {status.data.mode === "demo" ? "演示模式" : "真实模型已启用"}
              </span>
              <p>
                {status.data.mode === "demo"
                  ? "无模型调用费用。使用真实知识检索与受控模板生成内容。"
                  : "当前模型：" +
                    status.data.model +
                    "。费用由配置的模型服务商按用量计算。"}
              </p>
              <div className="note">
                API 密钥仅在服务端环境变量中配置。启用真实模型需修改 .env
                并重启后端。
              </div>
            </>
          )}
          <State {...usage} retry={usage.reload} />
          <State {...quota} retry={quota.reload} />
          {quota.data && <p className="model-quota">今日真实问答 {quota.data.attempted_turns} / {quota.data.daily_limit} 次，剩余 {quota.data.remaining_turns} 次；失败 {quota.data.failed_turns} 次。按上海时区计算，应用统计不是供应商账单。</p>}
          {usage.data && (
            <dl>
              <dt>已记录模型请求</dt>
              <dd>{usage.data.requests}</dd>
              <dt>输入 / 输出 token</dt>
              <dd>
                {usage.data.input_tokens} / {usage.data.output_tokens}
              </dd>
            </dl>
          )}
          <details className="care-details map-usage-details">
            <summary>地图查询与请求用量</summary>
            <State {...mapUsage} retry={mapUsage.reload} />
            {mapUsage.data && (
              <>
                <p>
                  {mapUsage.data.enabled ? "地图接口已配置" : "地图接口未启用"}
                  ；本地营养计算和摘要不需要外部密钥。
                </p>
                <dl>
                  <dt>今日应用请求</dt>
                  <dd>
                    {mapUsage.data.day_requests} / {mapUsage.data.day_limit}
                  </dd>
                  <dt>本月应用请求</dt>
                  <dd>
                    {mapUsage.data.month_requests} / {mapUsage.data.month_limit}
                  </dd>
                </dl>
                <p className="small muted">
                  按上海时区计数，含坐标转换和失败请求；不是供应商余额。免费资格由账号确认后手动启用。
                </p>
              </>
            )}
          </details>
        </Panel>
      </div>
      <Panel>
        <h2>能力与提醒范围</h2>
        <p>
          首版完整支持猫、狗。兔子、仓鼠、豚鼠及其他具体物种可保存档案和人工记录，但个性化照护建议尚未上线。鸟类、龟类、观赏鱼必须具体到物种。
        </p>
        <p>
          站内到期提醒仅在页面打开或刷新时显示，关闭应用后不会收到系统推送。
        </p>
        <p>
          健康回答提供观察与就医准备建议，不作确定性诊断，不开药或给药物剂量。知识摘要未经兽医审核。
        </p>
      </Panel>
    </>
  );
}

import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import {
  ArrowUpRight,
  Plus,
  Sparkles,
  Check,
  Clock,
  Heart,
  Sun,
  House,
  Utensils,
  Sprout,
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
} from "lucide-react";
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
import { useAction, useRemote } from "./hooks";
import {
  Panel,
  State,
  Feedback,
  Empty,
  Sources,
  PageTitle,
  PetArtwork,
  PetPortrait,
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
}: {
  items: Reminder[];
  reload: () => void;
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
                  · {r.timezone}
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
              {!r.task_id && !r.completed && (
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
  return (
    <>
      <PageTitle
        eyebrow={today}
        title="陪伴，是每天的小小用心"
        desc="把照护安排妥当，把更多时间留给彼此。"
      >
        <Button onClick={() => navigate("/pets")}>
          <Plus size={17} />
          管理宠物
        </Button>
      </PageTitle>
      <p className="today-line">
        <Sun size={16} aria-hidden="true" />
        {today}
        <span> · 把小小的照护，放进今天。</span>
      </p>
      <div className="home-grid">
        <section className="hero">
          <div>
            <h2>{pet ? pet.name + "，今天也要好好的" : "你好，新朋友。"}</h2>
            <p>
              {pet
                ? petLabel(pet) +
                  " · " +
                  (pet.age_months !== null
                    ? pet.age_months + " 个月"
                    : "年龄待补充") +
                  " · " +
                  (pet.weight ? pet.weight + " kg" : "体重待记录")
                : "建立一份档案，让建议更适合你的宠物。"}
            </p>
            <Button
              className="primary"
              onClick={() => navigate(pet ? "/plans" : "/pets")}
            >
              {pet ? "为它安排照护计划" : "建立宠物档案"}
              <ArrowUpRight size={17} />
            </Button>
            <small>
              {pet
                ? "当前档案中的信息，会用于问答与计划"
                : "首版完整支持猫和狗"}
            </small>
          </div>
          <div className="hero-art">
            <PetArtwork />
            <span className="art-caption">有你，就是好日子</span>
          </div>
        </section>
        <Panel className="care-tip">
          <div className="icon-box green">
            <ShieldCheck />
          </div>
          <h3>
            了解它的日常，
            <br />
            才能看见变化。
          </h3>
          <p>
            记下食欲、活动与排泄的变化。遇到呼吸困难、排不出尿等情况，及时联系兽医。
          </p>
          <Link to="/knowledge">
            了解健康观察
            <ChevronRight size={15} />
          </Link>
        </Panel>
      </div>
      <div className="stats">
        <Panel>
          <div className="icon-box peach">
            <CalendarDays />
          </div>
          <div>
            <strong>
              {due.length}
              <small>项</small>
            </strong>
            <p>当前宠物到期待办</p>
          </div>
        </Panel>
        <Panel>
          <div className="icon-box green">
            <Scale />
          </div>
          <div>
            <strong>
              {pet?.weight ?? "—"}
              <small>kg</small>
            </strong>
            <p>
              {pet?.weight_date
                ? "最近记录 " + dateText(pet.weight_date, user.timezone)
                : "记录体重，关注趋势"}
            </p>
          </div>
        </Panel>
        <Panel>
          <div className="icon-box violet">
            <Sparkles />
          </div>
          <div>
            <strong className="stat-text">有据可依</strong>
            <p>检索真实资料，展示来源</p>
          </div>
        </Panel>
      </div>
      <div className="two-col">
        <Panel>
          <div className="section-heading">
            <h2>
              <CalendarDays size={20} />
              今日照护
            </h2>
            <Link to="/plans">
              全部计划 <ArrowUpRight size={15} />
            </Link>
          </div>
          <p className="muted small">
            仅在页面打开或刷新时显示站内提醒 · {user.timezone}
          </p>
          {!pet ? (
            <NeedPet />
          ) : (
            <>
              <State {...reminders} retry={reminders.reload} />
              {reminders.data && (
                <ReminderList
                  items={due.slice(0, 6)}
                  reload={reminders.reload}
                />
              )}
            </>
          )}
        </Panel>
        <Panel>
          <div className="section-heading">
            <h2>
              <MessageIcon />
              和宠伴聊聊
            </h2>
          </div>
          <p className="muted">一点困惑，随时问问。</p>
          <div className="quick-questions">
            {[
              "它每天应该怎么吃？",
              "帮我生成一份照护计划",
              "新宠到家需要准备什么？",
            ].map((q) => (
              <button
                key={q}
                onClick={() => navigate("/chat?q=" + encodeURIComponent(q))}
              >
                <span>{q}</span>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
          <div className="mini-note">
            <BookOpen size={20} />
            <div>
              知识来自专业公开资料<small>中文摘要标注来源与审核状态</small>
            </div>
          </div>
        </Panel>
      </div>
      <div className="section-heading bottom-heading">
        <h2>照护知识，从这里开始</h2>
        <Link to="/knowledge">
          浏览知识库 <ArrowUpRight size={15} />
        </Link>
      </div>
      <div className="topic-cards">
        {topics.slice(0, 4).map((t, i) => (
          <Link to={"/knowledge?topic=" + encodeURIComponent(t)} key={t}>
            <span className={"topic-symbol tone-" + i}>
              {
                [
                  <Heart key="heart" />,
                  <House key="house" />,
                  <Utensils key="food" />,
                  <Sprout key="home" />,
                ][i]
              }
            </span>
            <h3>{t}</h3>
            <p>
              {
                [
                  "给陪伴做好准备",
                  "一起适应新的生活",
                  "吃得合适，健康成长",
                  "舒服的家，安心的它",
                ][i]
              }
            </p>
            <ArrowUpRight size={18} />
          </Link>
        ))}
      </div>
    </>
  );
}
function MessageIcon() {
  return <Sparkles size={20} />;
}
const blankPet = {
  name: "",
  species: "cat",
  breed: "",
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
  const edit = (p: Pet | null) => {
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
  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <>
      <PageTitle
        eyebrow="PET PROFILES"
        title="每一只，都值得被了解"
        desc="未知信息可以留空。体重在照护记录中按日期保存。"
      >
        <Button className="primary" onClick={() => edit(null)}>
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
                <span
                  className={"badge " + (pet?.id === p.id ? "green" : "quiet")}
                >
                  {petLabel(p)}
                  {pet?.id === p.id ? " · 当前宠物" : ""}
                </span>
              </div>
              <h2>{p.name}</h2>
              <p>
                {p.breed || "品种未知"} ·{" "}
                {p.age_months === null ? "年龄未知" : p.age_months + " 个月"} ·{" "}
                {p.weight ? p.weight + " kg" : "体重待记录"}
              </p>
              {!["cat", "dog"].includes(p.species) && (
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
                <Button onClick={() => edit(p)}>
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
            <Button onClick={() => setShow(false)}>取消</Button>
          </div>
          <form
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
            <div className="form-grid">
              <label>
                名称
                <input
                  required
                  maxLength={60}
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                />
              </label>
              <label>
                物种
                <select
                  value={
                    ["cat", "dog", "rabbit", "hamster", "guinea_pig"].includes(
                      form.species,
                    )
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
                  value={form.breed}
                  onChange={(e) => update("breed", e.target.value)}
                />
              </label>
              <label>
                生日
                <input
                  type="date"
                  value={form.birthday}
                  onChange={(e) => update("birthday", e.target.value)}
                />
              </label>
              <label>
                估计年龄（月，生日未知时）
                <input
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
                  value={form.neutered}
                  onChange={(e) => update("neutered", e.target.value)}
                >
                  <option value="">未知</option>
                  <option value="true">已绝育</option>
                  <option value="false">未绝育</option>
                </select>
              </label>
            </div>
            <div className="form-grid">
              {[
                ["diet", "当前饮食"],
                ["activity", "活动情况"],
                ["environment", "生活环境"],
                ["allergies", "用户填写的过敏史"],
                ["medical_history", "既往病史"],
                ["vet_advice", "兽医建议（请保留原意）"],
              ].map(([k, t]) => (
                <label key={k}>
                  {t}
                  <textarea
                    value={form[k]}
                    onChange={(e) => update(k, e.target.value)}
                    maxLength={2000}
                  />
                </label>
              ))}
            </div>
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
          aria-label="计划名称"
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          required
        />
      </label>
      <label>
        整体依据与适用条件
        <textarea
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
                  aria-label={"任务名称 " + (i + 1)}
                  value={t.title}
                  onChange={(e) => change(i, "title", e.target.value)}
                  required
                />
              </label>
              <label>
                当地时间
                <input
                  type="time"
                  value={t.local_time}
                  onChange={(e) => change(i, "local_time", e.target.value)}
                  required
                />
              </label>
              <label>
                重复
                <select
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
                value={t.instructions}
                onChange={(e) => change(i, "instructions", e.target.value)}
                required
              />
            </label>
            <label>
              依据与适用条件
              <textarea
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
  const reload = () => {
    plans.reload();
    reminders.reload();
  };
  return (
    <>
      <PageTitle
        eyebrow="CARE PLANNER"
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
                onClick={() =>
                  action.run(async () => {
                    const r = await api<{ draft: Draft; sources: Source[] }>(
                      "/pets/" + pet.id + "/plans/preview",
                      "POST",
                      { available_minutes: minutes },
                    );
                    setDraft(r.draft);
                    setSources(r.sources);
                    setEditPlan(null);
                  }, "草稿已生成，请检查后保存")
                }
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
                      </li>
                    ))}
                  </ul>
                  <div className="button-row">
                    <Button
                      onClick={() => {
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
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    maxLength={100}
                  />
                </label>
                <label>
                  到期当地时间
                  <input
                    required
                    type="datetime-local"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                  />
                </label>
                <label>
                  重复方式
                  <select
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
  const send = (value: string) =>
    action.run(async (key) => {
      const r = await api<Reply & { message: Message }>(
        "/chat",
        "POST",
        {
          pet_id: pet?.id || null,
          conversation_id: cid,
          text: value,
          available_minutes: minutes,
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
    }, "回答已返回");
  return (
    <>
      <PageTitle
        eyebrow="PET CARE AGENT"
        title="有问题，和宠伴聊聊"
        desc={
          pet
            ? "当前对话仅使用 " + pet.name + " 的档案与适用知识"
            : "无需建档，也可以提问猫狗普通知识。"
        }
      />
      <div className="chat-layout">
        <Panel className="chat-panel">
          <div className="chat-toolbar">
            <span className="badge green">{pet ? pet.name : "普通知识"}</span>
            <select
              aria-label="历史会话"
              value={cid || ""}
              onChange={(e) => {
                setCid(e.target.value || null);
                setLocalMessages([]);
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
                setCid(null);
                setNewChat(true);
                setLocalMessages([]);
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
          <div className="messages" aria-live="polite">
            {!localMessages.length && (
              <div className="chat-welcome">
                <PetArtwork className="chat-welcome-art" />
                <h2>你好，我是宠伴。</h2>
                <p>
                  一起了解它，一点点安排好照护。
                  <br />
                  可以问饮食、到家准备、日常互动，或生成计划。
                </p>
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
                <div className="message-text">{m.content}</div>
                {m.role === "assistant" && (
                  <>
                    <Sources items={m.metadata_json.sources || []} />
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
          <Feedback action={action} />
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) send(text.trim());
            }}
          >
            <textarea
              aria-label="提问内容"
              placeholder={
                pet
                  ? "问问关于 " + pet.name + " 的照护…"
                  : "例如：养猫前需要准备什么？"
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={4000}
              required
            />
            <div>
              <span>健康问题提供观察与就医准备建议</span>
              <Button className="primary" disabled={action.busy} type="submit">
                <Send size={16} />
                发送
              </Button>
            </div>
          </form>
        </Panel>
        <div>
          <Panel className="chat-context">
            <div className="icon-box green">
              <ShieldCheck />
            </div>
            <h3>当前照护背景</h3>
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
          </Panel>
        </div>
      </div>
    </>
  );
}
export function Knowledge() {
  const { pet } = useApp(),
    params = useParams(),
    [query] = useSearchParams(),
    action = useAction();
  const [q, setQ] = useState(""),
    [species, setSpecies] = useState(pet?.species || ""),
    [topic, setTopic] = useState(query.get("topic") || ""),
    [favorites, setFavorites] = useState(false);
  const path =
    "/knowledge?" +
    new URLSearchParams({
      q,
      species,
      topic,
      favorites: String(favorites),
    }).toString();
  const items = useRemote<Article[]>(!params.id ? path : null),
    detail = useRemote<Article>(params.id ? "/knowledge/" + params.id : null);
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
          ← 返回知识库
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
                  fill={detail.data.bookmarked ? "currentColor" : "none"}
                />
                {detail.data.bookmarked ? "已收藏" : "收藏"}
              </Button>
            </div>
            <div className="article-body">{detail.data.body}</div>
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
              <small>
                中文内容为公开资料的简短摘要，具体建议需结合宠物个体和兽医意见。
              </small>
            </div>
          </Panel>
        )}
      </>
    );
  return (
    <>
      <PageTitle
        eyebrow="KNOWLEDGE LIBRARY"
        title="了解多一点，照护安心一点"
        desc="按物种检索专业公开资料的中文摘要。每一条，都有来源。"
      />
      <Feedback action={action} />
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
            onChange={(e) => setSpecies(e.target.value)}
          >
            <option value="">猫与狗</option>
            <option value="cat">猫</option>
            <option value="dog">狗</option>
            {pet && !["cat", "dog"].includes(pet.species) && (
              <option value={pet.species}>{pet.species} · 暂未支持</option>
            )}
          </select>
        </label>
        <label>
          照护主题
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            <option value="">全部主题</option>
            {topics.map((t) => (
              <option key={t}>{t}</option>
            ))}
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
      <State {...items} retry={items.reload} />
      {items.data && !items.data.length && (
        <Empty>
          暂无匹配资料，请尝试其他关键词。未支持物种不能套用猫狗建议。
        </Empty>
      )}
      <div className="knowledge-grid">
        {items.data?.map((a, i) => (
          <Panel key={a.id}>
            <div className={"article-icon tone-" + (i % 4)}>
              <BookOpen size={22} />
              <span>{a.topic}</span>
            </div>
            <div className="section-heading">
              <span className="badge quiet">
                {a.species.map((s) => (s === "cat" ? "猫" : "狗")).join(" / ")}
              </span>
              <button
                className="bookmark-button"
                aria-label={"收藏 " + a.title}
                onClick={() => mark(a)}
              >
                <Bookmark
                  size={18}
                  fill={a.bookmarked ? "currentColor" : "none"}
                />
              </button>
            </div>
            <Link to={"/knowledge/" + a.id}>
              <h3>{a.title}</h3>
            </Link>
            <p className="article-excerpt">{a.body}</p>
            <div className="article-meta">
              {a.source_organization}
              <small>更新 {a.updated_at} · 编辑摘要，未兽医审核</small>
            </div>
            <Link to={"/knowledge/" + a.id} className="read-link">
              阅读详情 <ArrowUpRight size={15} />
            </Link>
          </Panel>
        ))}
      </div>
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
        eyebrow="CARE JOURNAL"
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
          <div className="two-col">
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
                    type="datetime-local"
                    required
                    value={when}
                    onChange={(e) => setWhen(e.target.value)}
                  />
                </label>
                <label>
                  记录内容
                  <textarea
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
                  <span className="journal-dot" />
                  <div>
                    <strong>
                      {kindNames[l.kind]}
                      {l.value ? " · " + l.value + " kg" : ""}
                    </strong>
                    <p>{l.note || "—"}</p>
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
  const values = weights.map((w) => w.value!),
    min = Math.min(...values) - 0.2,
    max = Math.max(...values) + 0.2;
  const dates = weights.map((w) => new Date(w.occurred_at).getTime()),
    start = dates[0],
    span = dates.at(-1)! - start;
  const points = weights.map((w, i) => [
    45 + (span === 0 ? 0 : ((dates[i] - start) / span) * 460),
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
        viewBox="0 0 560 215"
        role="img"
        aria-label="体重趋势，按实际记录日期显示"
      >
        {[0, 1, 2].map((n) => (
          <g key={n}>
            <line x1="45" x2="515" y1={45 + n * 57.5} y2={45 + n * 57.5} />
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
              <text x={x - 25} y="195">
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
  const { user, refreshUser } = useApp(),
    [name, setName] = useState(user.full_name),
    [timezone, setTimezone] = useState(user.timezone),
    action = useAction();
  const status = useRemote<{ mode: string; model: string | null }>("/status"),
    usage = useRemote<{
      requests: number;
      input_tokens: number;
      output_tokens: number;
    }>("/usage");
  return (
    <>
      <PageTitle
        eyebrow="ACCOUNT & PREFERENCES"
        title="你的宠伴，按你的习惯"
        desc="账户信息、时区与模型运行状态。"
      />
      <Feedback action={action} />
      <div className="two-col">
        <Panel>
          <h2>账户与时间设置</h2>
          <p className="muted">{user.email}</p>
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
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              IANA 时区
              <input
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

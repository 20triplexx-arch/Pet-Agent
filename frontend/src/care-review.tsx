import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "./App";
import { api, dateText, localNow, type Source } from "./api";
import { useAction, useRemote } from "./hooks";
import { Empty, Feedback, Panel, Sources, State } from "./components";
import { Button } from "./components/ui/button";

type Review = {
  pet_id: string; pet_name: string; generated_at: string; text: string;
  period: { days: number; timezone: string; start_date: string; end_date: string };
  summary: { records: number; recorded_days: number; unrecorded_days: number; completed_occurrences: number; current_due: number };
  counts: Record<string, number>;
  weight: { points: { id: string; value: number; occurred_at: string }[]; change_kg: number | null; change_percent: number | null };
  observations: { id: string; note: string; occurred_at: string }[]; observation_total: number;
  alerts: { record_id: string; message: string; occurred_at: string }[];
  suggestions: { title: string; detail: string; href: string }[];
  limitations: string[]; sources: Source[];
};
const names: Record<string, string> = { weight: "体重", diet: "饮食", activity: "活动", grooming: "护理", observation: "观察" };

export function CareReviewPanel({ version }: { version: number }) {
  const { pet } = useApp();
  const [days, setDays] = useState(7);
  const review = useRemote<Review>(pet ? `/pets/${pet.id}/care-review?days=${days}` : null);
  const previous = useRef(version);
  useEffect(() => { if (previous.current !== version) { previous.current = version; review.reload(); } }, [version]);
  const data = review.data;
  return <Panel className="care-review" id="care-review">
    <div className="section-heading review-heading"><h2>照护复盘</h2><div className="button-row" role="group" aria-label="复盘窗口">
      {[7, 30].map(n => <Button key={n} type="button" aria-pressed={days === n} className={days === n ? "primary" : ""} onClick={() => setDays(n)}>{n}天</Button>)}
    </div></div>
    <p className="muted small">从真实记录看变化。未记录不等于未照护，复盘不会自动调整计划或食量。</p>
    <State {...review} retry={review.reload} />
    {data && <>
      {data.alerts.map((alert, i) => <div className="alert" role="alert" key={`${alert.record_id}-${i}`}><div><strong>近期记录中的紧急线索</strong><p>{alert.message}</p><small>观察时间：{dateText(alert.occurred_at, data.period.timezone)}</small><p><Link to="/hospitals">查找医院与准备就医资料</Link></p></div></div>)}
      <p className="review-period">{data.period.start_date} — {data.period.end_date} · {data.period.timezone} · 本地统计</p>
      <dl className="review-facts"><div><dt>记录覆盖</dt><dd>{data.summary.recorded_days} / {data.period.days} 天，共 {data.summary.records} 条</dd></div><div><dt>窗口内打卡</dt><dd>{data.summary.completed_occurrences} 次</dd></div><div><dt>未记录日期</dt><dd>{data.summary.unrecorded_days} 天</dd></div><div><dt>当前到期待办</dt><dd>{data.summary.current_due} 项</dd></div></dl>
      {!data.summary.records && <Empty>这段时间还没有记录。填写真实发生的饮食、活动或观察后，再回来复盘。</Empty>}
      <p className="review-kind-counts">{Object.entries(names).map(([kind, name]) => `${name} ${data.counts[kind] || 0}条`).join(" · ")}</p>
      <h3>体重实测变化</h3>
      {data.weight.change_kg !== null ? <p>{data.weight.points[0].value} → {data.weight.points.at(-1)!.value} kg，实测差 {data.weight.change_kg > 0 ? "+" : ""}{data.weight.change_kg} kg（{data.weight.change_percent}%）。<br /><small className="muted">{dateText(data.weight.points[0].occurred_at, data.period.timezone)} 至 {dateText(data.weight.points.at(-1)!.occurred_at, data.period.timezone)}；仅描述实测数值，不推定病因或目标食量。</small></p> : <p className="muted">窗口内不同时间的有效称重不足两次，暂不计算变化。称重频率以个体情况和专业建议为准。</p>}
      {!!data.suggestions.length && <><h3>建议先核对</h3><ul className="review-suggestions">{data.suggestions.map(item => <li key={item.title}><Link to={item.href}>{item.title}</Link><p>{item.detail}</p></li>)}</ul></>}
      {!!data.observations.length && <details className="review-observations"><summary>查看观察记录 · {data.observation_total} 条{data.observation_total > 20 ? "（显示最新20条）" : ""}</summary>{data.observations.map(o => <div className="review-observation" key={o.id}><small>{dateText(o.occurred_at, data.period.timezone)}</small><p>{o.note}</p></div>)}</details>}
      <Sources items={data.sources} />
      <details className="review-boundaries"><summary>统计口径与边界</summary><ul>{data.limitations.map(t => <li key={t}>{t}</li>)}</ul><p>生成时间：{dateText(data.generated_at, data.period.timezone)}</p></details>
      <div className="button-row"><Button type="button" onClick={() => {
        const blob = new Blob([data.text + "\n\n检索参考\n" + data.sources.map(s => s.title + " " + s.url).join("\n")], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob), link = document.createElement("a");
        link.href = url; link.download = `${data.pet_name}-照护复盘-${data.period.end_date}.txt`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      }}>下载复盘 TXT</Button><Button type="button" onClick={review.reload} disabled={review.loading}>刷新复盘</Button></div>
    </>}
  </Panel>;
}

export function QuickCareLog({ saved }: { saved: () => void }) {
  const { pet, user } = useApp(), action = useAction();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [weight, setWeight] = useState("");
  const [when, setWhen] = useState(localNow(user.timezone));
  const [confirmed, setConfirmed] = useState(false);
  if (!pet) return null;
  return <details className="quick-care"><summary>多项一起记录</summary><p className="muted small">仅填写实际观察到的内容，空白项不会保存。一次记录不会替代任务打卡。</p>
    <Feedback action={action} />
    <form aria-label="多项照护记录" onSubmit={e => {
      e.preventDefault(); action.run(async key => {
        const { utc: occurred_at } = await api<{ utc: string }>("/time/convert", "POST", { local: when, timezone: user.timezone });
        const entries: { kind: string; value: number | null; note: string; occurred_at: string }[] = [];
        if (weight.trim()) entries.push({ kind: "weight", value: Number(weight), note: "", occurred_at });
        for (const kind of ["diet", "activity", "grooming", "observation"]) if (notes[kind]?.trim()) entries.push({ kind, value: null, note: notes[kind].trim(), occurred_at });
        if (!entries.length) throw new Error("至少填写一项真实发生的照护记录。");
        await api(`/pets/${pet.id}/logs/batch`, "POST", { entries, confirm: confirmed }, key);
        setNotes({}); setWeight(""); setConfirmed(false); saved();
      }, "多项记录已全部保存");
    }}>
      <fieldset className="quick-care-fields" disabled={action.busy}>
        <label>多项记录发生时间（{user.timezone}）<input type="datetime-local" required value={when} onChange={e => { setWhen(e.target.value); setConfirmed(false); }} /></label>
        <label>多项记录体重（kg，可留空）<input type="number" min="0.01" max="200" step="0.01" value={weight} onChange={e => { setWeight(e.target.value); setConfirmed(false); }} /></label>
        {Object.entries(names).filter(([kind]) => kind !== "weight").map(([kind, name]) => <label key={kind}>{name}情况（可留空）<textarea rows={2} maxLength={3000} value={notes[kind] || ""} onChange={e => { setNotes({ ...notes, [kind]: e.target.value }); setConfirmed(false); }} placeholder={kind === "diet" ? "具体食物、实际摄入和零食，未知不推测" : "写下实际做法或观察；没有信息请留空"} /></label>)}
        <label className="care-check"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />我已核对填写内容与所选宠物、发生时间一致</label>
        <Button type="submit" className="primary">{action.busy ? "正在保存…" : "保存填写的记录"}</Button>
      </fieldset>
    </form>
  </details>;
}

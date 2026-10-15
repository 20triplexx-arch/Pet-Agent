"""Local, dated care facts. Missing entries never mean care was not performed."""
from collections import Counter
from datetime import datetime, timedelta, time
import math
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlmodel import select
from app.clock import utc_now, iso, parse_utc
from app.models import Pet, CareLog, CarePlan, Reminder, TaskCompletion, PetNutritionProfile, KnowledgeArticle
from app.services import owned
from app.knowledge import search_knowledge

KIND_NAMES = {"weight": "体重", "diet": "饮食", "activity": "活动", "grooming": "护理", "observation": "观察"}
RULE_VERSION = "care-review-2026-10-13.1"


def build_review(session, user, pet_id, days=7, *, current=None):
    if days not in (7, 30):
        raise HTTPException(422, "请选择7天或30天复盘")
    pet = owned(session, Pet, pet_id, user.id)
    current = current or utc_now()
    zone = ZoneInfo(user.timezone)
    end_date = current.astimezone(zone).date()
    start_date = end_date - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, zone)
    records = session.exec(select(CareLog).where(CareLog.user_id == user.id, CareLog.pet_id == pet_id,
        CareLog.occurred_at >= iso(start), CareLog.occurred_at <= iso(current)).order_by(CareLog.occurred_at, CareLog.created_at, CareLog.id)).all()
    counts = Counter(r.kind for r in records)
    dates = Counter(parse_utc(r.occurred_at).astimezone(zone).date().isoformat() for r in records)
    weights = [{"id": r.id, "value": r.value, "occurred_at": r.occurred_at} for r in records
        if r.kind == "weight" and r.value is not None and math.isfinite(r.value) and r.value > 0]
    weight = {"points": weights, "change_kg": None, "change_percent": None}
    if len(weights) > 1 and weights[0]["occurred_at"] != weights[-1]["occurred_at"]:
        delta = weights[-1]["value"] - weights[0]["value"]
        weight.update(change_kg=round(delta, 3), change_percent=round(delta / weights[0]["value"] * 100, 2))
    completions = session.exec(select(TaskCompletion).join(Reminder, Reminder.id == TaskCompletion.reminder_id)
        .where(TaskCompletion.user_id == user.id, Reminder.user_id == user.id, Reminder.pet_id == pet_id,
            TaskCompletion.completed_at >= iso(start), TaskCompletion.completed_at <= iso(current))).all()
    plans = session.exec(select(CarePlan).where(CarePlan.user_id == user.id, CarePlan.pet_id == pet_id)).all()
    reminders = session.exec(select(Reminder).where(Reminder.user_id == user.id, Reminder.pet_id == pet_id,
        Reminder.paused == False, Reminder.due_at <= iso(current))).all()
    overdue = [r for r in reminders if not session.exec(select(TaskCompletion).where(
        TaskCompletion.user_id == user.id, TaskCompletion.reminder_id == r.id, TaskCompletion.occurrence_at == r.due_at)).first()]
    suggestions = []
    if not records:
        suggestions.append({"title": "先补充真实发生的记录", "detail": "窗口内暂无记录，不能判断照护是否执行。可从饮食、活动或观察开始，未知内容留空。", "href": "/logs"})
    elif not counts["diet"]:
        suggestions.append({"title": "补充饮食的实际执行情况", "detail": "记录具体食品、实际摄入、零食与食欲；不要用计划数量代替实际吃下的数量。", "href": "/logs"})
    if overdue:
        suggestions.append({"title": "核对当前到期待办", "detail": f"当前有{len(overdue)}项到期待办尚无该周期打卡。请核对实际执行情况，不补造过去的完成历史。", "href": "/plans"})
    nutrition = session.exec(select(PetNutritionProfile).where(PetNutritionProfile.user_id == user.id,
        PetNutritionProfile.pet_id == pet_id)).first()
    active_nutrition = next((p for p in plans if nutrition and p.id == nutrition.active_plan_id and p.status == "active"), None)
    new_inputs = [r.id for r in records if active_nutrition and r.kind in ("weight", "diet", "observation")
        and parse_utc(r.occurred_at) > parse_utc(active_nutrition.created_at)]
    if new_inputs:
        suggestions.append({"title": "新记录可用于营养复评", "detail": "当前营养方案之后出现新的体重、饮食或观察记录。先核对资料，再到营养页重新预览；本次不会自动更改食量或任务。", "href": "/nutrition", "record_ids": new_inputs})
    observations = [{"id": r.id, "note": r.note, "occurred_at": r.occurred_at} for r in reversed(records) if r.kind == "observation"]
    from app.agent import risks
    alerts = []
    for observation in observations:
        # Only flag fresh observations; a historical note cannot establish current urgency.
        if parse_utc(observation["occurred_at"]) >= current - timedelta(hours=24):
            for rule in risks(observation["note"], pet.species):
                alerts.append({"record_id": observation["id"], "occurred_at": observation["occurred_at"],
                    "rule_id": rule["id"], "article_id": rule["article_id"],
                    "message": "最近24小时的记录包含紧急风险线索；若仍在发生，请立即联系兽医或宠物急诊。历史记录不能确认症状是否已经解决。 " + rule["message"]})
    if observations and not alerts:
        suggestions.append({"title": "核对观察是否仍在发生", "detail": "这些是用户观察，不能据此诊断或判定已经恢复。补充开始时间、频率和变化；必要时整理就医资料。", "href": "/hospitals#visit-summary"})
    articles = search_knowledge(session, pet.species, "照护复盘 记录 饮食实际摄入", limit=3, personal=True)
    for alert in alerts:
        article = session.get(KnowledgeArticle, alert["article_id"])
        if article and article.id not in {a["id"] for a in articles}:
            articles.append(article.model_dump())
    return {"pet_id": pet_id, "pet_name": pet.name, "generated_at": iso(current), "rule_version": RULE_VERSION,
        "period": {"days": days, "timezone": user.timezone, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "summary": {"records": len(records), "recorded_days": len(dates), "unrecorded_days": days - len(dates),
            "completed_occurrences": len(completions), "current_due": len(overdue)},
        "counts": {kind: counts[kind] for kind in KIND_NAMES},
        "daily": [{"date": (start_date + timedelta(days=i)).isoformat(), "records": dates[(start_date + timedelta(days=i)).isoformat()]} for i in range(days)],
        "weight": weight, "observations": observations[:20], "observation_total": len(observations), "alerts": alerts,
        "plans": [{"id": p.id, "title": p.title, "status": p.status, "revision": p.revision} for p in plans],
        "suggestions": suggestions,
        "record_ids": [r.id for r in records], "completion_ids": [c.id for c in completions],
        "sources": [{"id": a["id"], "title": a["title"], "url": a["source_url"], "organization": a["source_organization"]} for a in articles],
        "limitations": ["未记录不等于未照护；本报告不计算历史任务漏做率。", "7/30天是应用统计窗口，不是称重或医疗复查频率。", "体重差仅为两次实测数值之差，不判断脂肪、疾病或目标食量。", "完成数按打卡发生时间统计；暂停和旧计划的完成历史仍保留。"]}


def review_text(review):
    period, summary = review["period"], review["summary"]
    lines = [f"{review['pet_name']}的照护复盘", f"{period['start_date']} 至 {period['end_date']} · {period['timezone']}",
        "生成时间：" + review["generated_at"], "\n最近记录中的紧急线索"] if review["alerts"] else [f"{review['pet_name']}的照护复盘", f"{period['start_date']} 至 {period['end_date']} · {period['timezone']}", "生成时间：" + review["generated_at"]]
    lines += [a["message"] + "（观察时间：" + a["occurred_at"] + "）" for a in review["alerts"]]
    lines += ["\n可核对事实", f"共有{summary['records']}条记录，覆盖{summary['recorded_days']}天；{summary['unrecorded_days']}天没有记录。", f"窗口内打卡{summary['completed_occurrences']}次，当前到期待办{summary['current_due']}项。"]
    if review["weight"]["change_kg"] is not None:
        points = review["weight"]["points"]
        lines.append(f"体重：{points[0]['value']} kg → {points[-1]['value']} kg，实测差{review['weight']['change_kg']:+g} kg（{points[0]['occurred_at']} 至 {points[-1]['occurred_at']}）。")
    else:
        lines.append("窗口内不同时间的有效称重不足两次，无法计算体重变化。")
    lines += ["\n建议先核对"] + [s["title"] + "：" + s["detail"] for s in review["suggestions"]]
    lines += ["\n统计边界"] + review["limitations"]
    return "\n".join(lines)

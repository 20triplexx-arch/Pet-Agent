"""Deterministic, source-bound maintenance assessment; never a treatment prescription."""
from datetime import datetime, timedelta, UTC
import math
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import select
from app.models import Pet, CareLog, CarePlan, Reminder, PetNutritionProfile, now
from app.services import owned, pet_public, fingerprint, add_plan
from app.schemas import PlanDraft, TaskDraft
from app.care_schemas import NutritionInput, NutritionSave
from app.knowledge import search_knowledge
from app.species import supports

RULE_VERSION = "aaha-2021-maintenance-v1"


def get_profile(session, user, pid):
    owned(session, Pet, pid, user.id)
    row = session.exec(select(PetNutritionProfile).where(
        PetNutritionProfile.pet_id == pid, PetNutritionProfile.user_id == user.id
    )).first()
    return row


def profile_response(session, user, pid):
    row = get_profile(session, user, pid)
    data = NutritionInput.model_validate(row.data) if row else NutritionInput()
    result = {"profile": data.model_dump(mode="json"), "revision": row.revision if row else 0,
              "active_plan_id": row.active_plan_id if row else None, "needs_reassessment": False}
    if row and row.active_plan_id:
        plan = owned(session, CarePlan, row.active_plan_id, user.id)
        result["needs_reassessment"] = (plan.provenance or {}).get("evidence_digest") != assess(session, user, pid, data)["evidence_digest"]
    return result


def care_history(session, user, pid, days=30):
    owned(session, Pet, pid, user.id)
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    rows = session.exec(select(CareLog).where(
        CareLog.user_id == user.id, CareLog.pet_id == pid, CareLog.occurred_at >= since
    ).order_by(CareLog.occurred_at.desc(), CareLog.id).limit(100)).all()
    return [row.model_dump() for row in rows]


def current_plans(session, user, pid):
    owned(session, Pet, pid, user.id)
    return [p.model_dump() for p in session.exec(select(CarePlan).where(
        CarePlan.user_id == user.id, CarePlan.pet_id == pid, CarePlan.status == "active"
    ).limit(10)).all()]


def source_cards(articles):
    return [{"id": a["id"], "title": a["title"], "url": a["source_url"],
             "organization": a["source_organization"]} for a in articles]


def kcal_per_gram(food):
    if food.energy is None:
        return None
    value = food.energy / (4.184 if food.energy_unit.startswith("kj") else 1)
    if food.energy_unit.endswith("portion"):
        density = value / food.portion_grams if food.portion_grams else None
    else:
        density = value / (1000 if food.energy_unit.endswith("kg") else 100)
    return density if density and math.isfinite(density) else None


def assess(session, user, pid, data: NutritionInput):
    p = pet_public(session, owned(session, Pet, pid, user.id))
    row = get_profile(session, user, pid)
    articles = search_knowledge(session, p["species"], "营养 热量 体况 肌肉 食物 标签 零食", limit=20)
    logs = care_history(session, user, pid)
    evidence = {"pet": p, "profile": data.model_dump(mode="json"), "logs": logs,
                "rules": RULE_VERSION, "articles": articles}
    digest = fingerprint("nutrition-evidence", evidence)
    result = {
        "pet_id": pid, "pet_name": p["name"], "status": "needs_info",
        "revision": row.revision if row else 0,
        "preview_token": fingerprint(f"nutrition:{user.id}:{pid}", [digest, row.revision if row else 0]),
        "evidence_digest": digest, "rule_version": RULE_VERSION,
        "input_snapshot": evidence, "sources": source_cards(articles),
        "questions": [], "warnings": [], "calculation": None, "foods": [],
        "weight": p["weight"], "weight_date": p["weight_date"], "urgent": False,
        "conditions": "健康成年、体况合适、肌肉正常的猫狗维持体重起始参考；需持续观察，个体需求可能不同。",
    }
    missing, risks = [], []
    if not supports(p["species"], "nutrition"):
        risks.append("该具体物种尚未开放营养评估，不能套用猫狗方法。")
    if data.life_stage == "unknown":
        missing.append("请确认生命阶段；犬只成年时间不能只按统一年龄判断。")
    elif data.life_stage != "adult" or (p["age_months"] is not None and p["age_months"] < 12):
        risks.append("成长或老年阶段需要单独的专业营养评估。")
    if data.health_status == "unknown":
        missing.append("请确认当前健康状态及是否有新的异常观察。")
    elif data.health_status != "healthy":
        risks.append("当前存在健康问题，饮食安排应由兽医评估。")
    if data.pregnancy_lactation == "unknown":
        missing.append("请确认是否处于孕期或哺乳期。")
    elif data.pregnancy_lactation == "yes":
        risks.append("孕哺阶段需要专业营养方案。")
    if data.bcs is None or not data.assessed_on or data.assessor == "unknown":
        missing.append("请填写体况评分、评估日期和填写者；可通过来源了解评估方法。")
    elif data.bcs not in (4, 5):
        risks.append("体况评分不在 4—5/9，需要扩展营养评估，不自动制定增减重目标。")
    if data.muscle == "unknown":
        missing.append("请确认肌肉状况，不清楚时向兽医了解。")
    elif data.muscle != "normal":
        risks.append("已报告肌肉损失，需要专业评估。")
    if data.activity_level == "unknown":
        missing.append("请确认活动水平。")
    elif data.activity_level == "high":
        risks.append("高强度活动需要专门的能量评估。")
    if data.diet_restrictions.strip() or data.current_symptoms.strip():
        risks.append("已填写饮食限制或症状；请按兽医建议安排，不自动更改食量。")
    # Free-text history is not parsed into an invented diagnosis or cleared by a checkbox.
    if p["medical_history"] or p["allergies"] or p["vet_advice"]:
        risks.append("档案含病史、过敏或兽医建议，需要确认专业饮食要求；可整理就医摘要。")
    if p["weight"] is None or not data.weight_confirmed:
        missing.append("请记录最新体重，并确认页面显示的体重和日期适用于本次评估。")
    if p["neutered"] is None and data.activity_level != "low":
        missing.append("请在档案中补充绝育情况。")
    if not data.treats_confirmed:
        missing.append("请确认所有零食均已列入；没有零食也需明确确认。")
    if not data.food_shares_confirmed:
        missing.append("请确认以当前主粮的热量比例分配方案。")
    mains = [f for f in data.foods if f.kind == "main"]
    if not mains:
        missing.append("请至少填写一种当前主粮及包装热量。")
    current_main, current_treat = 0.0, 0.0
    for food in data.foods:
        density = kcal_per_gram(food)
        if food.kind == "main" and food.complete_adult_food is not True:
            missing.append(f"请确认 {food.name} 是适用于当前物种成年阶段的全价主粮。")
        if density is None or food.daily_grams is None:
            missing.append(f"请补充 {food.name} 的热量、每日克数；按份热量还需每份克重。")
            continue
        energy = density * food.daily_grams
        if not math.isfinite(energy):
            missing.append(f"{food.name} 的单位与克重无法可靠换算，请核对包装信息。")
            continue
        current_main += energy if food.kind == "main" else 0
        current_treat += energy if food.kind == "treat" else 0
        result["foods"].append({"name": food.name, "kind": food.kind, "kcal_per_gram": density,
                                "current_daily_grams": food.daily_grams, "current_kcal": energy})
    if mains and current_main <= 0:
        missing.append("主粮的当前摄入量需要大于零，才能确定分配比例。")
    required = {"nutrition-energy", "nutrition-risk", "nutrition-feeding"}
    if not required.issubset({a["id"] for a in articles}):
        missing.append("本地营养计算依据尚未完整导入，暂不生成数量。")
    from app.agent import risks as emergency_risks
    urgent = emergency_risks(data.current_symptoms, p["species"])
    result["urgent"] = bool(urgent)
    if urgent:
        from app.models import KnowledgeArticle
        for rule in urgent:
            article = session.get(KnowledgeArticle, rule["article_id"])
            if article and article.id not in {a["id"] for a in result["sources"]}:
                result["sources"].extend(source_cards([article.model_dump()]))
        risks.insert(0, "请立即联系兽医或宠物急诊，不要等待完善营养资料。")
    result["warnings"] = risks
    result["questions"] = list(dict.fromkeys(missing))
    if risks:
        result["status"] = "professional_required"
    elif not missing:
        result["status"] = "ready"
        rer = 70 * p["weight"] ** 0.75
        if data.activity_level == "low":
            factors = (1.0, 1.0) if p["species"] == "cat" else (1.0, 1.2)
        elif p["species"] == "cat":
            factors = (1.2, 1.4) if p["neutered"] else (1.4, 1.6)
        else:
            factors = (1.4, 1.6) if p["neutered"] else (1.6, 1.8)
        low, high = rer * factors[0], rer * factors[1]
        result["calculation"] = {"rer_kcal": rer, "factor_range": factors,
            "daily_kcal_range": [low, high], "current_kcal": current_main + current_treat,
            "current_main_kcal": current_main, "current_treat_kcal": current_treat,
            "formula": "RER = 70 × 体重kg^0.75；维持热量 = RER × 活动/绝育状态系数"}
        for food in result["foods"]:
            if food["kind"] == "main":
                share = food["current_kcal"] / current_main
                food["calorie_share"] = share
                food["reference_grams_range"] = [max(0, v - current_treat) * share / food["kcal_per_gram"] for v in (low, high)]
        if current_treat > low * 0.1:
            result["warnings"].append("当前零食可能超过参考总热量的 10%；保存前请确认零食目标，主粮应提供至少 90% 热量。")
    return result


def store_profile(session, user, pid, data, revision):
    row = get_profile(session, user, pid)
    values = {"data": data.model_dump(mode="json"), "updated_at": now()}
    if row:
        changed = session.execute(update(PetNutritionProfile).where(
            PetNutritionProfile.id == row.id, PetNutritionProfile.revision == revision
        ).values(**values, revision=revision + 1), execution_options={"synchronize_session": False})
        if changed.rowcount != 1:
            raise HTTPException(409, "营养资料已变更，请刷新后重试")
        session.expire(row)
    else:
        if revision != 0:
            raise HTTPException(409, "营养资料版本已变更")
        row = PetNutritionProfile(user_id=user.id, pet_id=pid, **values)
        session.add(row)
        session.flush()
    return row


def save_nutrition_plan(session, user, pid, data: NutritionSave):
    preview = assess(session, user, pid, data.profile)
    if data.preview_token != preview["preview_token"] or data.revision != preview["revision"]:
        raise HTTPException(409, "档案、体重、记录或资料已变化，请重新评估后保存")
    if preview["urgent"]:
        raise HTTPException(422, "请优先联系兽医；当前不保存营养方案")
    tasks = []
    amounts = []
    if preview["status"] == "ready":
        target = data.daily_target_kcal
        low, high = preview["calculation"]["daily_kcal_range"]
        if target is None or not low <= target <= high:
            raise HTTPException(422, "请明确选择参考范围内的每日热量目标；范围外目标需要专业评估")
        if data.planned_treat_kcal > target * 0.1:
            raise HTTPException(422, "零食目标不可超过总热量 10%，请调整并确认")
        if data.planned_treat_kcal > 0 and preview["calculation"]["current_treat_kcal"] <= 0:
            raise HTTPException(422, "新增零食目标需要先提供零食热量与摄入资料，并重新预览")
        for food in preview["foods"]:
            if food["kind"] == "main":
                grams = (target - data.planned_treat_kcal) * food["calorie_share"] / food["kcal_per_gram"]
            else:
                current = preview["calculation"]["current_treat_kcal"]
                grams = data.planned_treat_kcal * (food["current_kcal"] / current) / food["kcal_per_gram"] if current > 0 else 0
            amounts.append({"name": food["name"], "kind": food["kind"], "daily_grams": grams, "per_meal_grams": grams / len(data.meal_times)})
        for time in data.meal_times:
            tasks.append(TaskDraft(title="按营养方案喂食", local_time=time,
                instructions="本餐：" + "；".join(f"{f['name']} 约 {f['per_meal_grams']:.1f} g" for f in amounts)
                    + f"。全天零食目标 {data.planned_treat_kcal:g} kcal，记录实际摄入与食欲。",
                basis=f"AAHA 2021 起始参考，用户确认每日 {target:g} kcal；包装热量由用户提供，餐次时间由用户安排。"))
    elif data.daily_target_kcal is not None or data.planned_treat_kcal != 0:
        raise HTTPException(422, "资料不足或存在风险，不能保存量化喂食目标")
    else:
        tasks.append(TaskDraft(title="核对饮食与观察", instructions="核对原有或兽医提供的饮食安排，记录实际摄入和食欲；不自行增加或减少食量。",
            basis="尚未确定可靠食量；补齐资料或向兽医咨询。", local_time=data.meal_times[0]))
    tasks.append(TaskDraft(title="记录与回顾", recurrence="weekly", weekday=5, local_time="09:00",
        instructions="记录体重、食欲与活动变化，有新信息时重新评估。", basis="每周为可编辑的管理安排，不是医疗频率。"))
    row = store_profile(session, user, pid, data.profile, data.revision)
    if row.active_plan_id:
        old = owned(session, CarePlan, row.active_plan_id, user.id)
        old.status = "paused"
        session.add(old)
        from app.models import CareTask
        ids = session.exec(select(CareTask.id).where(CareTask.plan_id == old.id)).all()
        session.exec(update(Reminder).where(Reminder.user_id == user.id, Reminder.task_id.in_(ids)).values(paused=True))
    result = add_plan(session, user, pid, PlanDraft(title=preview["pet_name"] + "的营养照护方案",
        basis=preview["conditions"] if preview["status"] == "ready" else "非量化观察方案；" + "；".join(preview["warnings"] + preview["questions"][:3]), tasks=tasks))
    plan = session.get(CarePlan, result["id"])
    plan.provenance = {"kind": "nutrition", "rule_version": RULE_VERSION,
        "input_snapshot": preview["input_snapshot"], "sources": preview["sources"],
        "evidence_digest": preview["evidence_digest"], "daily_target_kcal": data.daily_target_kcal,
        "planned_treat_kcal": data.planned_treat_kcal, "amounts": amounts}
    row.active_plan_id = plan.id
    session.add(plan)
    session.add(row)
    session.flush()
    return {**result, "provenance": plan.provenance, "nutrition_revision": row.revision}

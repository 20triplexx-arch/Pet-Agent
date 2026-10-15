import asyncio, json, re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, UTC
from fastapi import HTTPException
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits
from sqlmodel import Session
from app.core.config import settings
from app.models import Pet, ModelUsage, Breed, KnowledgeArticle, ProductAssessment
from sqlmodel import select
from app.schemas import *
from app.services import owned, pet_public, add_plan, add_reminder, add_log
from app.knowledge import search_knowledge, reading_excerpt
from app.species import supports
from app.nutrition import care_history, current_plans, assess, get_profile
from app.care_schemas import NutritionInput, VisitInput
from app.visit import build_summary
from app.execution import traced_tool
from app.chat_models import ModelSelection, select_model

DATA = Path(__file__).resolve().parents[1] / "data"
SYSTEM = Path(__file__).with_name("agent_system.txt").read_text(encoding="utf-8")
RISK_RULES = json.loads((DATA / "risk_rules.json").read_text(encoding="utf-8"))


@dataclass
class AgentContext:
    session: Session
    user: object
    pet_id: str | None
    retrieved: dict = field(default_factory=dict)
    # Issued by server only, never inferred from retrieved text or model output.
    authorization: str | None = None
    authorized_payload: dict | None = None
    species_scope: str | None = None
    breed_scope: str | None = None
    supplement: dict = field(default_factory=dict)
    answer_depth: str = "auto"
    resolved_depth: str = "standard"
    effective_context: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    model_attempt: object | None = None
    model_selection: ModelSelection | None = None
    sent_evidence: dict = field(default_factory=dict)
    read_cache: dict = field(default_factory=dict)

    @property
    def selected_model(self):
        return self.model_selection or select_model()


def profile(ctx):
    return (
        pet_public(ctx.session, owned(ctx.session, Pet, ctx.pet_id, ctx.user.id))
        if ctx.pet_id
        else None
    )


def authorize(ctx, action, payload):
    if (
        not ctx.pet_id
        or ctx.authorization != action
        or ctx.authorized_payload != payload
    ):
        raise HTTPException(403, "未获得对本次载荷的明确写入指令")
    owned(ctx.session, Pet, ctx.pet_id, ctx.user.id)
    # Consume once; a model cannot issue the same mutation twice in one run.
    ctx.authorization = None


def tool_get_pet_profile(ctx):
    return profile(ctx)


def profile_stage(p):
    # AAHA/AAFP 2021: knowledge matching only, not a medical assessment.
    # See actual seed article cat-life-stages for traceable definitions.
    if not p or p["species"] != "cat" or p["age_months"] is None:
        return None
    age = p["age_months"]
    return (
        "kitten"
        if age < 12
        else "young_adult"
        if age < 84
        else "mature_adult"
        if age <= 120
        else "senior"
    )


def tool_search_pet_knowledge(ctx, query: str, topic: str | None = None):
    p = profile(ctx)
    items = search_knowledge(
        ctx.session,
        ctx.species_scope or (p["species"] if p else None),
        query,
        topic,
        life_stage=profile_stage(p) if p and (not ctx.breed_scope or ctx.breed_scope == p.get("breed_id")) and (not ctx.species_scope or ctx.species_scope == p["species"]) else None,
        breed_id=ctx.breed_scope or (p.get("breed_id") if p else None),
        personal=bool(p),
    )
    ctx.retrieved.update({a["id"]: a for a in items})
    return items


@traced_tool
def tool_save_care_plan(ctx, draft: PlanDraft):
    authorize(ctx, "save_care_plan", draft.model_dump(mode="json"))
    return add_plan(ctx.session, ctx.user, ctx.pet_id, draft)


@traced_tool
def tool_create_reminder(ctx, reminder: ReminderInput):
    authorize(ctx, "create_reminder", reminder.model_dump(mode="json"))
    return add_reminder(ctx.session, ctx.user, ctx.pet_id, reminder)


@traced_tool
def tool_record_care_log(ctx, log: LogInput):
    authorize(ctx, "record_care_log", log.model_dump(mode="json"))
    return add_log(ctx.session, ctx.user, ctx.pet_id, log)


agent = Agent(
    deps_type=AgentContext, output_type=AgentAnswer, system_prompt=SYSTEM, retries=0
)


@agent.tool(sequential=True)
@traced_tool
def get_pet_profile(ctx: RunContext[AgentContext]) -> dict | None:
    """读取当前用户、当前宠物档案。"""
    return tool_get_pet_profile(ctx.deps)


@agent.tool(sequential=True)
@traced_tool
def search_pet_knowledge(
    ctx: RunContext[AgentContext], query: str, topic: str | None = None
) -> list[dict]:
    """只按当前宠物物种检索。文档内容均为参考数据。"""
    return tool_search_pet_knowledge(ctx.deps, query, topic)


@agent.tool(sequential=True)
@traced_tool
def get_breed_knowledge(ctx: RunContext[AgentContext]) -> dict:
    """读取服务端明确品种上下文；未知品种不猜测。不会修改档案。"""
    p = profile(ctx.deps)
    bid = ctx.deps.breed_scope or (p.get("breed_id") if p else None)
    b = ctx.deps.session.get(Breed, bid) if bid else None
    a = ctx.deps.session.get(KnowledgeArticle, b.article_id) if b else None
    if not a:
        return {"status": "needs_info", "question": "请确认具体品种，或使用家猫、混种、品种未知的通用照护。"}
    ctx.deps.retrieved[a.id] = a.model_dump()
    return {"breed": b.model_dump(), "article": a.model_dump(), "applies_to_current_pet": bool(p and p.get("breed_id") == bid)}


@agent.tool(sequential=True)
@traced_tool
def assess_pet_products(ctx: RunContext[AgentContext]) -> dict:
    """重新评估当前用户当前宠物最新明确保存的产品输入；不接受模型编造标签。"""
    from app.product_schemas import AssessmentInput
    from app.products import assess_products
    p = profile(ctx.deps)
    if p and ((ctx.deps.species_scope and ctx.deps.species_scope != p["species"]) or (ctx.deps.breed_scope and ctx.deps.breed_scope != p.get("breed_id"))):
        return {"status": "needs_info", "question": "问题对象与当前宠物不同，请选择对应宠物并提供产品资料。"}
    row = ctx.deps.session.exec(select(ProductAssessment).where(ProductAssessment.user_id == ctx.deps.user.id,
        ProductAssessment.pet_id == (p["id"] if p else None)).order_by(ProductAssessment.created_at.desc())).first()
    if not row:
        return {"status": "needs_info", "question": "请在产品比较页提供具体配方、规格和标签并确认。", "href": "/products"}
    result = assess_products(ctx.deps.session, ctx.deps.user, AssessmentInput.model_validate(row.inputs))
    for source in result["sources"]:
        a = ctx.deps.session.get(KnowledgeArticle, source["id"])
        if a:
            ctx.deps.retrieved[a.id] = a.model_dump()
    return {k: result[k] for k in ("products", "sources", "note", "rule_version", "origin")}


@agent.tool(sequential=True)
@traced_tool
def save_care_plan(ctx: RunContext[AgentContext], draft: PlanDraft) -> dict:
    """需要用户明确保存此草稿；只返回事务内结果，由外层提交后报告成功。"""
    return tool_save_care_plan(ctx.deps, draft)


@agent.tool(sequential=True)
@traced_tool
def create_reminder(ctx: RunContext[AgentContext], reminder: ReminderInput) -> dict:
    """需要用户明确创建指令及当地时间和时区。"""
    return tool_create_reminder(ctx.deps, reminder)


@agent.tool(sequential=True)
@traced_tool
def record_care_log(ctx: RunContext[AgentContext], log: LogInput) -> dict:
    """需要用户明确记录指令；验证实际发生时间与当前宠物权限。"""
    return tool_record_care_log(ctx.deps, log)


@agent.tool(sequential=True)
@traced_tool
def get_care_history(ctx: RunContext[AgentContext]) -> list[dict]:
    """读取当前宠物最近30天记录，最多20条，未知不推断。"""
    if not ctx.deps.pet_id:
        return []
    return [{**r, "note": r["note"][:500]} for r in care_history(ctx.deps.session, ctx.deps.user, ctx.deps.pet_id)[:20]]


@agent.tool(sequential=True)
@traced_tool
def get_current_care_plans(ctx: RunContext[AgentContext]) -> list[dict]:
    """读取当前宠物执行中的计划，不修改。"""
    if not ctx.deps.pet_id:
        return []
    return [{k: p[k] for k in ("id", "title", "basis", "revision")} for p in current_plans(ctx.deps.session, ctx.deps.user, ctx.deps.pet_id)]


@agent.tool(sequential=True)
@traced_tool
def get_care_review(ctx: RunContext[AgentContext], days: Literal[7, 30] = 7) -> dict:
    """按用户时区复盘当前宠物7/30天真实记录和打卡，不推断漏做或自动改计划。"""
    if not ctx.deps.pet_id:
        return {"status": "needs_info", "message": "请先选择要复盘的宠物。"}
    p = profile(ctx.deps)
    if ctx.deps.breed_scope and ctx.deps.breed_scope != p.get("breed_id"):
        return {"status": "needs_info", "message": "提问品种与当前宠物不同，请切换到对应档案后读取复盘。"}
    from app.care_review import build_review
    result = build_review(ctx.deps.session, ctx.deps.user, ctx.deps.pet_id, days)
    result["observations"] = [{**o, "note": o["note"][:500]} for o in result["observations"][:5]]
    result["weight"]["points"] = result["weight"]["points"][:1] + result["weight"]["points"][-1:] if len(result["weight"]["points"]) > 1 else result["weight"]["points"]
    result.pop("daily", None)
    result.pop("record_ids", None)
    result.pop("completion_ids", None)
    for source in result["sources"]:
        article = ctx.deps.session.get(KnowledgeArticle, source["id"])
        if article:
            ctx.deps.retrieved[article.id] = article.model_dump()
    return result


@agent.tool(sequential=True)
@traced_tool
def assess_nutrition(ctx: RunContext[AgentContext]) -> dict:
    """评估当前用户确认的档案及会话营养资料；不写入，不接受模型编造数值。"""
    if not ctx.deps.pet_id:
        return {"status": "needs_info", "questions": ["请先选择宠物并补充营养资料。"]}
    p = profile(ctx.deps)
    if ctx.deps.breed_scope and ctx.deps.breed_scope != p.get("breed_id"):
        return {"status": "needs_info", "questions": ["问题目标与当前档案不同，不能使用当前宠物的数值评估另一只宠物。"]}
    from app.deep_chat import nutrition_facts
    values = ctx.deps.effective_context.get("values", ctx.deps.supplement)
    result = nutrition_facts(ctx.deps, p, values, values.get("observations", ""))
    return result


@agent.tool(sequential=True)
@traced_tool
def search_nearby_hospitals(ctx: RunContext[AgentContext]) -> dict:
    """打开医院综合查询工具入口；两家地图由本地 Agent 统筹，位置仅在页面提供，不向模型传坐标。"""
    return {"type": "hospitals", "title": "找附近宠物医院", "href": "/hospitals", "status": "needs_user_location", "strategy": "combined_maps", "text": "输入地点后自动结合可用地图资料，核对重复登记并保留来源差异。"}


@agent.tool(sequential=True)
@traced_tool
def build_vet_visit_summary(ctx: RunContext[AgentContext]) -> dict:
    """从当前宠物真实记录生成就医摘要，不诊断或添加未报告症状。"""
    if not ctx.deps.pet_id:
        return {"status": "needs_info", "message": "请先选择宠物。"}
    result = build_summary(ctx.deps.session, ctx.deps.user, ctx.deps.pet_id, VisitInput())
    articles = search_knowledge(ctx.deps.session, profile(ctx.deps)["species"], "就医 观察 记录 准备", limit=3)
    ctx.deps.retrieved.update({a["id"]: a for a in articles})
    if len(result["text"]) > 12000:
        result["text"] = result["text"][:12000] + "\n[模型工具摘要已截断，请在就医资料页面查看完整记录]"
    return result


def risks(text, species):
    matches = []
    for rule in RISK_RULES:
        if species and species not in rule["species"]:
            continue
        for pattern in rule["patterns"]:
            positive = False
            for occurrence in re.finditer(re.escape(pattern), text):
                pos = occurrence.start()
                prefix = text[max(0, pos - 8) : pos]
                if not re.search(
                    r"(没有|并无|无|不曾|否认|未出现|没有出现)(明显|任何|出现)?$",
                    prefix,
                ):
                    positive = True
                    break
            if positive:
                matches.append(rule)
                break
    return matches


def infer_species(text):
    if "狗" in text or "犬" in text:
        return "dog"
    if "猫" in text:
        return "cat"
    for term in ("兔", "仓鼠", "豚鼠", "龟", "鹦鹉", "鸟", "鱼"):
        if term in text:
            return "unsupported"
    return None


def make_draft(ctx, minutes):
    p = profile(ctx)
    if not p:
        raise HTTPException(422, "个性化计划需要先选择宠物")
    if not supports(p["species"], "care_plan"):
        raise HTTPException(422, "暂不支持该物种的个性化计划")
    articles = search_knowledge(
        ctx.session,
        p["species"],
        "喂食 饮水 互动 清洁",
        limit=20,
        life_stage=profile_stage(p),
    )
    ctx.retrieved.update({a["id"]: a for a in articles})
    if not articles:
        raise HTTPException(422, "资料不足，无法可靠生成计划")
    cat = p["species"] == "cat"
    basis = "适用健康猫狗的日常观察；有病史或限制时先按兽医建议调整。每日/每周是可编辑的管理安排，不是医疗处方。"
    if p.get("vet_advice"):
        basis += " 已记录兽医建议：" + p["vet_advice"]
    if p.get("medical_history"):
        basis += " 已记录病史：" + p["medical_history"] + "；活动耐受需专业评估。"
    tasks = [
        TaskDraft(
            title="饮食与饮水检查",
            instructions="核对原有喂食安排，检查清洁饮水，记录食欲。不自动计算食量。",
            basis="依据检索："
            + ("cat-food" if cat else "dog-food")
            + "；食量需食物能量密度、体况和专业建议。",
            local_time="08:00",
        ),
        TaskDraft(
            title="互动与" + ("探索游戏" if cat else "嗅闻活动"),
            instructions=f"从舒适的短时互动开始，观察反应。今天预留约 {max(3, minutes - 10)} 分钟，可拆分；不适时停止并咨询兽医。",
            basis="依据检索："
            + ("cat-play" if cat else "dog-play")
            + "；分钟数来自用户可用时间，不代表运动需求已满足。",
            local_time="18:30",
        ),
        TaskDraft(
            title="清洁与状态观察",
            instructions="整理"
            + (
                "猫砂区，查看尿量和排泄变化。"
                if cat
                else "休息与排泄区域，观察皮肤、被毛和行动变化。"
            ),
            basis="依据检索："
            + ("cat-clean" if cat else "dog-clean")
            + "；每日是提醒检查的安排，具体护理按状态调整。",
            local_time="20:00",
        ),
        TaskDraft(
            title="体重与一周回顾",
            instructions="在相近条件下记录体重及食欲、活动变化，必要时向兽医提供趋势。",
            basis="每周是本应用的可编辑记录安排，非适用于所有年龄或疾病的医疗频率。",
            recurrence="weekly",
            local_time="09:00",
            weekday=5,
        ),
    ]
    return PlanDraft(title=p["name"] + "的日常照护计划", basis=basis, tasks=tasks)


def sources(ctx, ids):
    return [
        {
            "id": i,
            "title": ctx.retrieved[i]["title"],
            "url": ctx.retrieved[i]["source_url"],
            "organization": ctx.retrieved[i]["source_organization"],
        }
        for i in dict.fromkeys(ids)
        if i in ctx.retrieved
    ]


def explicit_write(ctx, text):
    """Only complete, unambiguous commands authorize writes, not general intent."""
    weight = re.fullmatch(
        r"(?:请|帮我)?(?:记录|记下)(?:今天的?)?体重\s*[：:]?\s*(\d+(?:\.\d+)?)\s*(?:kg|KG|公斤|千克)",
        text.strip(),
    )
    observation = re.fullmatch(
        r"(?:请|帮我)?记录(饮食|活动|护理|观察)\s*[：:]\s*(.+)", text.strip(), re.S
    )
    reminder = re.fullmatch(
        r"(?:请|帮我)?创建提醒\s*[：:]\s*(.+?)\s*[；;]\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})\s*(?:[；;]\s*(一次性|每日|每周))?",
        text.strip(),
    )
    if not (weight or observation or reminder):
        if text.strip().startswith(("创建提醒", "记录")):
            return {
                "answer": "当前尚未写入。请提供明确的事项与时间，例如「记录体重 3.6kg」「记录饮食：食欲正常」或「创建提醒：检查饮水；2026-10-10 08:00；每日」。历史记录请在照护记录页选择实际发生日期。",
                "mode": "tools",
                "sources": [],
                "draft": None,
                "urgent": False,
            }
        return None
    if not ctx.pet_id:
        return {
            "answer": "写入需要先选择一只宠物。当前尚未保存记录或提醒。",
            "mode": "tools",
            "sources": [],
            "draft": None,
            "urgent": False,
        }
    if weight or observation:
        names = {
            "饮食": "diet",
            "活动": "activity",
            "护理": "grooming",
            "观察": "observation",
        }
        log = LogInput(
            kind="weight" if weight else names[observation[1]],
            value=float(weight[1]) if weight else None,
            note="用户明确记录的当前体重" if weight else observation[2],
            occurred_at=datetime.now(UTC),
        )
        ctx.authorization = "record_care_log"
        ctx.authorized_payload = log.model_dump(mode="json")
        result = tool_record_care_log(ctx, log)
        return {
            "answer": "已为当前宠物保存照护记录（发生时间按本次记录时刻）。",
            "mode": "tools",
            "sources": [],
            "draft": None,
            "urgent": False,
            "saved_log_id": result["id"],
        }
    value = ReminderInput(
        title=reminder[1],
        due_local=datetime.fromisoformat(reminder[2]),
        timezone=ctx.user.timezone,
        recurrence={"一次性": "once", "每日": "daily", "每周": "weekly"}[
            reminder[3] or "一次性"
        ],
    )
    ctx.authorization = "create_reminder"
    ctx.authorized_payload = value.model_dump(mode="json")
    result = tool_create_reminder(ctx, value)
    return {
        "answer": "提醒已创建，使用账户时区 "
        + ctx.user.timezone
        + "。仅在页面打开或刷新时显示站内提醒。",
        "mode": "tools",
        "sources": [],
        "draft": None,
        "urgent": False,
        "saved_reminder_id": result["id"],
    }


def clean_answer(text):
    # Links are rendered separately from validated retrieved IDs.
    return re.sub(r"https?://\S+", "[外部链接已省略，请查看下方实际检索来源]", text)


async def respond(ctx, text, history, minutes):
    p = profile(ctx)
    species = p["species"] if p else infer_species(text)
    if not species and history:
        species = next(
            (
                infer_species(m["content"])
                for m in reversed(history)
                if m["role"] == "user" and infer_species(m["content"])
            ),
            None,
        )
    ctx.species_scope = species
    risk_text = text + " " + " ".join(v for v in ctx.supplement.values() if isinstance(v, str))
    if ctx.supplement.get("nutrition"):
        risk_text += " " + ctx.supplement["nutrition"].get("current_symptoms", "")
    found = risks(risk_text, species)
    demo = ctx.selected_model.demo
    if found:
        for r in found:
            items = search_knowledge(ctx.session, None, "")
            ctx.retrieved.update(
                {a["id"]: a for a in items if a["id"] == r["article_id"]}
            )
            # Risk source must exist even when not in top keyword results.

            a = ctx.session.get(KnowledgeArticle, r["article_id"])
            if a:
                ctx.retrieved[a.id] = a.model_dump()
        return {
            "answer": "请立即联系兽医或宠物急诊。\n"
            + "\n".join(r["message"] for r in found)
            + "\n准备症状开始时间、变化、接触物包装、病史与已用药物。不要自行用药或延迟就医。",
            "urgent": True,
            "mode": "demo" if demo else "safety",
            "sources": sources(ctx, [r["article_id"] for r in found]),
            "risk_rule_ids": [r["id"] for r in found],
            "draft": None,
            "cards": [{"type": "hospitals", "title": "找附近宠物医院", "href": "/hospitals"}, {"type": "visit_summary", "title": "整理就医资料", "href": "/hospitals#visit-summary"}],
        }
    from app.deep_chat import answer_question
    if re.search(r"照护复盘|照护周报|照护月报|复盘.{0,8}(?:照护|记录)|总结.{0,8}(?:照护|记录)", text):
        named_species = infer_species(text)
        if p and named_species and named_species != p["species"]:
            return {"answer": "本次提问的物种与当前宠物不同，请切换到对应宠物档案再复盘。没有它的实际记录，不能套用当前宠物的照护历史。", "mode": "demo" if demo else "local_review", "urgent": False, "sources": [], "draft": None}
        if not ctx.pet_id:
            return {"answer": "请先选择需要复盘的宠物。复盘只读取该宠物的真实记录，不会推断未记录的照护或修改计划。", "mode": "demo" if demo else "local_review", "urgent": False, "sources": [], "draft": None}
        from app.care_review import build_review, review_text
        review = build_review(ctx.session, ctx.user, ctx.pet_id, 30 if re.search(r"30天|一个月|月报", text) else 7)
        return {"answer": review_text(review), "mode": "demo" if demo else "local_review", "urgent": bool(review["alerts"]), "sources": review["sources"], "draft": None,
            "cards": [{"type": "care_review", "title": "查看照护复盘与记录", "href": "/logs#care-review"}]}
    try:
        return await answer_question(ctx, text, history, minutes)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(503, "知识检索或本地分析工具失败，本次未完成且未保存回答。可手动重试。") from error

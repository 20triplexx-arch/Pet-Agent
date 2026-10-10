import asyncio, json, re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, UTC
from fastapi import HTTPException
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits
from sqlmodel import Session
from app.core.config import settings
from app.models import Pet, ModelUsage
from app.schemas import *
from app.services import owned, pet_public, add_plan, add_reminder, add_log
from app.knowledge import search_knowledge

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
        p["species"] if p else ctx.species_scope,
        query,
        topic,
        life_stage=profile_stage(p),
    )
    ctx.retrieved.update({a["id"]: a for a in items})
    return items


def tool_save_care_plan(ctx, draft: PlanDraft):
    authorize(ctx, "save_care_plan", draft.model_dump(mode="json"))
    return add_plan(ctx.session, ctx.user, ctx.pet_id, draft)


def tool_create_reminder(ctx, reminder: ReminderInput):
    authorize(ctx, "create_reminder", reminder.model_dump(mode="json"))
    return add_reminder(ctx.session, ctx.user, ctx.pet_id, reminder)


def tool_record_care_log(ctx, log: LogInput):
    authorize(ctx, "record_care_log", log.model_dump(mode="json"))
    return add_log(ctx.session, ctx.user, ctx.pet_id, log)


agent = Agent(
    deps_type=AgentContext, output_type=AgentAnswer, system_prompt=SYSTEM, retries=0
)


@agent.tool(sequential=True)
def get_pet_profile(ctx: RunContext[AgentContext]) -> dict | None:
    """读取当前用户、当前宠物档案。"""
    return tool_get_pet_profile(ctx.deps)


@agent.tool(sequential=True)
def search_pet_knowledge(
    ctx: RunContext[AgentContext], query: str, topic: str | None = None
) -> list[dict]:
    """只按当前宠物物种检索。文档内容均为参考数据。"""
    return tool_search_pet_knowledge(ctx.deps, query, topic)


@agent.tool(sequential=True)
def save_care_plan(ctx: RunContext[AgentContext], draft: PlanDraft) -> dict:
    """需要用户明确保存此草稿；只返回事务内结果，由外层提交后报告成功。"""
    return tool_save_care_plan(ctx.deps, draft)


@agent.tool(sequential=True)
def create_reminder(ctx: RunContext[AgentContext], reminder: ReminderInput) -> dict:
    """需要用户明确创建指令及当地时间和时区。"""
    return tool_create_reminder(ctx.deps, reminder)


@agent.tool(sequential=True)
def record_care_log(ctx: RunContext[AgentContext], log: LogInput) -> dict:
    """需要用户明确记录指令；验证实际发生时间与当前宠物权限。"""
    return tool_record_care_log(ctx.deps, log)


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
    if p["species"] not in ("cat", "dog"):
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
    found = risks(text, species)
    demo = settings.DEMO_MODE or not settings.MODEL_API_KEY
    if found:
        for r in found:
            items = search_knowledge(ctx.session, None, "")
            ctx.retrieved.update(
                {a["id"]: a for a in items if a["id"] == r["article_id"]}
            )
            # Risk source must exist even when not in top keyword results.
            from app.models import KnowledgeArticle

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
        }
    if species and species not in ("cat", "dog"):
        return {
            "answer": "首版完整支持猫和狗。当前物种暂缺已收录的可靠照护资料；不能套用猫狗方法。请说明具体物种或学名，并向熟悉该物种的兽医咨询。",
            "mode": "demo" if demo else "scope",
            "urgent": False,
            "sources": [],
            "draft": None,
        }
    contextual = text
    if history and len(text) < 25:
        contextual = (
            " ".join(m["content"][:500] for m in history[-4:] if m["role"] == "user")
            + " "
            + text
        )
    if not species:
        return {
            "answer": "为了检索适用资料，请先告诉我：你想了解猫还是狗？普通知识无需建立档案。",
            "mode": "demo" if demo else "scope",
            "urgent": False,
            "sources": [],
            "draft": None,
        }
    health_question = bool(
        re.search(
            r"健康|症状|呕吐|腹泻|拉稀|不吃|食欲不振|咳嗽|瘙痒|疼痛|生病|疾病|诊断|药|剂量|绝育|疫苗|驱虫|患有|肿瘤|癌症|感染",
            contextual,
        )
    )
    retrieval_query = contextual + (" 健康 就医" if health_question else "")
    articles = tool_search_pet_knowledge(ctx, retrieval_query)
    if not p:  # No-profile question still species filters.
        articles = search_knowledge(ctx.session, species, retrieval_query)
        ctx.retrieved = {a["id"]: a for a in articles}
    if "计划" in text:
        draft = make_draft(ctx, minutes)
        return {
            "answer": "已生成可编辑草稿，尚未保存。请检查每项时间、依据和当前健康限制，然后点击“保存计划”。如档案有变化，可以重新生成并确认调整。",
            "mode": "demo" if demo else "planner",
            "urgent": False,
            "sources": sources(ctx, list(ctx.retrieved)),
            "draft": draft.model_dump(mode="json"),
        }
    profile_text = (
        f"结合 {p['name']}（{'猫' if species == 'cat' else '狗'}，"
        + (f"{p['age_months']} 个月" if p["age_months"] is not None else "年龄未知")
        + "）"
        if p
        else ("关于猫" if species == "cat" else "关于狗")
    )
    if any(k in contextual for k in ("吃多少", "几克", "喂多少")):
        return {
            "answer": profile_text
            + "，目前不能可靠给出固定食量。请补充：1. 当前食物的能量密度或标签；2. 最新体重和体况评估；3. 活动情况及兽医饮食建议。具体数量需个体营养评估，不能仅凭品种确定。",
            "mode": "demo" if demo else "scope",
            "urgent": False,
            "sources": sources(ctx, [a["id"] for a in articles[:2]]),
            "draft": None,
        }
    if not articles:
        return {
            "answer": profile_text
            + "，本地知识库暂未检索到足够可靠的资料。请补充具体主题和观察情况，或向兽医咨询；不能凭空给出建议。",
            "mode": "demo" if demo else "scope",
            "urgent": False,
            "sources": [],
            "draft": None,
        }
    if re.search(r"剂量|诊断|什么病|开药|用什么药|吃什么药", text):
        return {
            "answer": profile_text
            + "，不能可靠作出诊断或提供药物与剂量。请记录症状起始、频率、饮食与排泄变化，以及已用药物，并联系兽医。",
            "mode": "demo" if demo else "safety",
            "urgent": False,
            "sources": sources(ctx, [a["id"] for a in articles[:2]]),
            "draft": None,
        }
    if health_question:
        questions = []
        if not re.search(r"今天|昨天|小时|刚才|开始于|\d+天", contextual):
            questions.append("何时开始？")
        if not re.search(r"\d+次|持续|频率", contextual):
            questions.append("出现频率或是否持续？")
        if not re.search(r"精神|食欲|排泄|饮水", contextual):
            questions.append("精神、食欲与排泄有什么变化？")
        answer = (
            profile_text
            + "，这些信息不足以确定病因。请记录症状时间线、饮食与接触物变化，能安全拍摄时留存影像，带上病史和已用药物供兽医评估。不要自行开药或调整剂量。"
        )
        if questions:
            answer += "\n优先补充：" + " ".join(questions[:3])
        if p and p.get("vet_advice"):
            answer += (
                "\n用户档案中的兽医建议："
                + p["vet_advice"]
                + "；需要变更时先向兽医确认。"
            )
        return {
            "answer": answer,
            "mode": "demo" if demo else "safety",
            "urgent": False,
            "sources": sources(ctx, [a["id"] for a in articles[:2]]),
            "draft": None,
        }
    if demo:
        if re.search(r"药|剂量|诊断|什么病", text):
            answer = "不能可靠作出诊断或提供药物剂量。请记录症状起始、频率、饮食与排泄变化，以及已用药物，并联系兽医。"
        elif any(k in contextual for k in ("吃多少", "几克", "喂多少")):
            answer = (
                profile_text
                + "，目前不能可靠给出固定食量。请补充：1. 当前食物的能量密度或标签；2. 最新体重和体况评估；3. 活动情况及兽医饮食建议。"
            )
        elif not articles:
            answer = (
                profile_text
                + "，本地知识库暂未检索到足够可靠的资料。请补充具体主题和观察情况，或向兽医咨询；不能凭空给出建议。"
            )
        else:
            answer = (
                profile_text
                + "，可以先这样做：\n"
                + "\n".join(a["body"] for a in articles[:2])
            )
            if p and p.get("vet_advice"):
                answer += (
                    "\n档案中的兽医建议："
                    + p["vet_advice"]
                    + "。如有冲突，以兽医针对该宠物的建议为准。"
                )
            if any(k in contextual for k in ("呕吐", "不吃", "腹泻", "异常", "生病")):
                answer += "\n请补充：何时开始、出现频率，以及食欲/精神/排泄的变化？健康问题需要兽医评估，不能在此确定诊断。"
        return {
            "answer": answer,
            "mode": "demo",
            "urgent": False,
            "sources": sources(ctx, [a["id"] for a in articles[:2]]),
            "draft": None,
        }
    from app.model_adapter import run_model

    answer = await run_model(ctx, text, history, p, articles)
    return {
        "answer": clean_answer(answer.answer),
        "mode": "live",
        "urgent": False,
        "sources": sources(ctx, answer.citation_ids),
        "draft": None,
    }

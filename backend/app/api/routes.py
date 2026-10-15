import json
import asyncio
from datetime import timedelta, date
from typing import Annotated
from pathlib import Path
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from sqlalchemy import delete, update
from pydantic import ValidationError
from sqlmodel import select
from app.api.deps import SessionDep, CurrentUser
from app.core.config import settings
from app.core.security import *
from app.models import *
from app.schemas import *
from app.services import *
from app.knowledge import retriever, serialize_article
from app.agent import *
from app.species import registry
from app.breeds import validate_breed
from app.execution import current_execution

router = APIRouter(prefix="/api/v1")
Key = Annotated[str | None, Header(alias="Idempotency-Key")]


def public_user(u):
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "timezone": u.timezone,
    }


@router.post("/users/signup")
def register(data: Register, session: SessionDep):
    email = str(data.email).lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(409, "邮箱已注册")
    u = User(
        email=email,
        full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
    )
    session.add(u)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "邮箱已注册")
    return public_user(u)


@router.post("/login/access-token")
def login(session: SessionDep, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    u = session.exec(select(User).where(User.email == form.username.lower())).first()
    if not u:
        raise HTTPException(401, "邮箱或密码不正确")
    valid, newhash = verify_password(form.password, u.hashed_password)
    if not valid or not u.is_active:
        raise HTTPException(401, "邮箱或密码不正确")
    if newhash:
        u.hashed_password = newhash
        session.add(u)
        session.commit()
    return {
        "access_token": create_access_token(
            u.id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        ),
        "token_type": "bearer",
    }


@router.get("/users/me")
def me(user: CurrentUser):
    return public_user(user)


@router.patch("/users/me")
def settings_update(data: SettingsUpdate, session: SessionDep, user: CurrentUser):
    user.full_name = data.full_name
    user.timezone = data.timezone
    session.add(user)
    session.commit()
    return public_user(user)


@router.get("/status")
def status(user: CurrentUser):
    return {
        "mode": settings.model_mode,
        "model": None
        if settings.DEMO_MODE
        else settings.model_name,
        "reminder_delivery": "in_app_only",
    }


@router.get("/chat/models")
def chat_models(user: CurrentUser):
    from app.chat_models import catalog
    return catalog()


@router.post("/time/convert")
def convert_time(data: TimeConvert, user: CurrentUser):
    return {"utc": iso(localize(data.local, data.timezone))}


@router.get("/species")
def species(user: CurrentUser):
    return registry()


@router.get("/pets")
def pets(session: SessionDep, user: CurrentUser):
    return [
        pet_public(session, p)
        for p in session.exec(
            select(Pet).where(Pet.user_id == user.id).order_by(Pet.created_at)
        ).all()
    ]


@router.post("/pets")
def create_pet(data: PetInput, session: SessionDep, user: CurrentUser, key: Key = None):
    validate_breed(session, data.species, data.breed_id)
    def action():
        values = data.model_dump(mode="json")
        if values["estimated_age_months"] is not None:
            values["age_estimated_on"] = utc_now().date().isoformat()
        p = Pet(user_id=user.id, **values)
        session.add(p)
        session.flush()
        return pet_public(session, p)

    return mutate(
        session, user.id, key, "pet:create", data.model_dump(mode="json"), action
    )


@router.get("/pets/{pid}")
def get_pet(pid: str, session: SessionDep, user: CurrentUser):
    return pet_public(session, owned(session, Pet, pid, user.id))


@router.put("/pets/{pid}")
def edit_pet(pid: str, data: PetInput, session: SessionDep, user: CurrentUser):
    p = owned(session, Pet, pid, user.id)
    validate_breed(session, data.species, data.breed_id)
    age_changed = data.estimated_age_months != p.estimated_age_months
    for k, v in data.model_dump(mode="json").items():
        setattr(p, k, v)
    if p.estimated_age_months is None:
        p.age_estimated_on = None
    elif age_changed or not p.age_estimated_on:
        p.age_estimated_on = utc_now().date().isoformat()
    session.add(p)
    session.commit()
    return pet_public(session, p)


@router.delete("/pets/{pid}")
def delete_pet(pid: str, session: SessionDep, user: CurrentUser):
    p = owned(session, Pet, pid, user.id)
    # Delete dependent rows in FK order, inside one transaction.
    convs = [
        c.id
        for c in session.exec(
            select(Conversation).where(Conversation.pet_id == pid)
        ).all()
    ]
    plans = [
        p.id for p in session.exec(select(CarePlan).where(CarePlan.pet_id == pid)).all()
    ]
    rems = [
        r.id for r in session.exec(select(Reminder).where(Reminder.pet_id == pid)).all()
    ]
    session.exec(delete(PetNutritionProfile).where(PetNutritionProfile.pet_id == pid))
    session.exec(delete(ProductAssessment).where(ProductAssessment.pet_id == pid))
    session.exec(delete(Message).where(Message.conversation_id.in_(convs)))
    session.exec(delete(Conversation).where(Conversation.id.in_(convs)))
    session.exec(delete(TaskCompletion).where(TaskCompletion.reminder_id.in_(rems)))
    session.exec(delete(Reminder).where(Reminder.id.in_(rems)))
    session.exec(delete(CareTask).where(CareTask.plan_id.in_(plans)))
    session.exec(delete(CarePlan).where(CarePlan.id.in_(plans)))
    session.exec(delete(CareLog).where(CareLog.pet_id == pid))
    session.delete(p)
    session.commit()
    return {"deleted": True}


@router.get("/knowledge")
def knowledge(
    session: SessionDep,
    user: CurrentUser,
    q: str = "",
    species: str | None = None,
    topic: str | None = None,
    favorites: bool = False,
    breed_id: str | None = None,
    content_kind: str | None = None,
    life_stage: str | None = None,
):
    if content_kind and content_kind not in ("care", "breed", "food", "supplies"):
        raise HTTPException(422, "未知知识分类")
    if breed_id:
        b = session.get(Breed, breed_id)
        if not b or (species and b.species != species):
            raise HTTPException(422, "品种与物种不匹配")
        species = b.species
    marks = {
        b.article_id
        for b in session.exec(select(Bookmark).where(Bookmark.user_id == user.id)).all()
    }
    return [
        serialize_article(a, a.id in marks)
        for a in retriever.search(session, species, q[:1000], topic, life_stage, breed_id, content_kind)
        if not favorites or a.id in marks
    ]


@router.get("/knowledge/{aid}")
def article(aid: str, session: SessionDep, user: CurrentUser):
    a = session.get(KnowledgeArticle, aid)
    if not a:
        raise HTTPException(404, "知识条目不存在")
    mark = session.exec(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.article_id == aid)
    ).first()
    return serialize_article(a, bool(mark))


@router.put("/knowledge/{aid}/bookmark")
def bookmark(aid: str, session: SessionDep, user: CurrentUser):
    if not session.get(KnowledgeArticle, aid):
        raise HTTPException(404, "知识条目不存在")
    b = session.exec(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.article_id == aid)
    ).first()
    if not b:
        session.add(Bookmark(user_id=user.id, article_id=aid))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    return {"bookmarked": True}


@router.delete("/knowledge/{aid}/bookmark")
def unbookmark(aid: str, session: SessionDep, user: CurrentUser):
    session.exec(
        delete(Bookmark).where(Bookmark.user_id == user.id, Bookmark.article_id == aid)
    )
    session.commit()
    return {"bookmarked": False}


@router.get("/pets/{pid}/logs")
def logs(pid: str, session: SessionDep, user: CurrentUser):
    owned(session, Pet, pid, user.id)
    return [
        l.model_dump()
        for l in session.exec(
            select(CareLog)
            .where(CareLog.user_id == user.id, CareLog.pet_id == pid)
            .order_by(CareLog.occurred_at.desc())
        ).all()
    ]


@router.post("/pets/{pid}/logs")
def log(
    pid: str, data: LogInput, session: SessionDep, user: CurrentUser, key: Key = None
):
    payload = data.model_dump(mode="json")

    def action():
        return tool_record_care_log(
            AgentContext(
                session,
                user,
                pid,
                authorization="record_care_log",
                authorized_payload=payload,
            ),
            data,
        )

    return mutate(session, user.id, key, "log:" + pid, payload, action)


@router.delete("/logs/{lid}")
def delete_log(lid: str, session: SessionDep, user: CurrentUser):
    l = owned(session, CareLog, lid, user.id)
    session.delete(l)
    session.commit()
    return {"deleted": True}


@router.get("/pets/{pid}/plans")
def plans(pid: str, session: SessionDep, user: CurrentUser):
    owned(session, Pet, pid, user.id)
    return [
        plan_public(session, p)
        for p in session.exec(
            select(CarePlan)
            .where(CarePlan.user_id == user.id, CarePlan.pet_id == pid)
            .order_by(CarePlan.created_at.desc())
        ).all()
    ]


@router.post("/pets/{pid}/plans/preview")
def preview(pid: str, data: PlanRequest, session: SessionDep, user: CurrentUser):
    ctx = AgentContext(session, user, pid)
    draft = make_draft(ctx, data.available_minutes)
    return {
        "draft": draft.model_dump(mode="json"),
        "sources": sources(ctx, list(ctx.retrieved)),
    }


@router.post("/pets/{pid}/plans")
def save_plan(
    pid: str, data: PlanDraft, session: SessionDep, user: CurrentUser, key: Key = None
):
    payload = data.model_dump(mode="json")

    def action():
        return tool_save_care_plan(
            AgentContext(
                session,
                user,
                pid,
                authorization="save_care_plan",
                authorized_payload=payload,
            ),
            data,
        )

    return mutate(session, user.id, key, "plan:" + pid, payload, action)


@router.put("/plans/{ident}")
def update_plan(
    ident: str, data: PlanEdit, session: SessionDep, user: CurrentUser, key: Key = None
):
    def action():
        p = owned(session, CarePlan, ident, user.id)
        if (p.provenance or {}).get("kind") == "nutrition":
            raise HTTPException(422, "营养数量需要重新评估；请在营养页面调整并确认方案")
        if p.revision != data.revision:
            raise HTTPException(409, "计划已被修改，请刷新后重试")
        changed = session.exec(
            update(CarePlan)
            .where(
                CarePlan.id == ident,
                CarePlan.user_id == user.id,
                CarePlan.revision == data.revision,
            )
            .values(title=data.title, basis=data.basis, revision=data.revision + 1)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "计划已被修改，请刷新后重试")
        session.refresh(p)
        old_tasks = session.exec(select(CareTask).where(CareTask.plan_id == p.id)).all()
        for t in old_tasks:
            t.active = False
            session.add(t)
            for r in session.exec(
                select(Reminder).where(Reminder.task_id == t.id)
            ).all():
                r.paused = True
                session.add(r)
        session.add(p)
        for d in data.tasks:
            t = CareTask(plan_id=p.id, **d.model_dump())
            session.add(t)
            session.flush()
            session.add(
                Reminder(
                    user_id=user.id,
                    pet_id=p.pet_id,
                    task_id=t.id,
                    title=t.title,
                    recurrence=t.recurrence,
                    timezone=user.timezone,
                    local_time=t.local_time,
                    weekday=t.weekday,
                    due_at=first_task_due(
                        t.local_time, t.recurrence, t.weekday, user.timezone
                    ),
                    paused=p.status != "active",
                )
            )
        session.flush()
        return plan_public(session, p)

    return mutate(
        session,
        user.id,
        key,
        "plan:update:" + ident,
        data.model_dump(mode="json"),
        action,
    )


@router.patch("/plans/{ident}/status")
def plan_status(ident: str, data: PlanStatus, session: SessionDep, user: CurrentUser):
    p = owned(session, CarePlan, ident, user.id)
    if data.status == "active" and (p.provenance or {}).get("kind") == "nutrition":
        from app.nutrition import profile_response
        nutrition = profile_response(session, user, p.pet_id)
        if nutrition["active_plan_id"] != p.id or nutrition["needs_reassessment"]:
            raise HTTPException(409, "这份营养方案已被替换或依据变化，请重新评估")
    p.status = data.status
    p.revision += 1
    session.add(p)
    for t in session.exec(
        select(CareTask).where(CareTask.plan_id == p.id, CareTask.active == True)
    ).all():
        for r in session.exec(select(Reminder).where(Reminder.task_id == t.id)).all():
            r.paused = data.status != "active"
            session.add(r)
    session.commit()
    return plan_public(session, p)


@router.get("/reminders")
def reminders(session: SessionDep, user: CurrentUser, pet_id: str | None = None):
    if pet_id:
        owned(session, Pet, pet_id, user.id)
    rows = session.exec(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.due_at)
    ).all()
    return [
        {
            **r.model_dump(),
            "completed": bool(
                session.exec(
                    select(TaskCompletion).where(TaskCompletion.reminder_id == r.id)
                ).first()
            )
            if r.recurrence == "once"
            else False,
            "due": not r.paused and parse_utc(r.due_at) <= utc_now(),
            "local_due": parse_utc(r.due_at)
            .astimezone(ZoneInfo(user.timezone))
            .isoformat(),
        }
        for r in rows
        if (not pet_id or r.pet_id == pet_id)
        and (not r.task_id or session.get(CareTask, r.task_id).active)
    ]


@router.post("/pets/{pid}/reminders")
def reminder(
    pid: str,
    data: ReminderInput,
    session: SessionDep,
    user: CurrentUser,
    key: Key = None,
):
    payload = data.model_dump(mode="json")

    def action():
        return tool_create_reminder(
            AgentContext(
                session,
                user,
                pid,
                authorization="create_reminder",
                authorized_payload=payload,
            ),
            data,
        )

    return mutate(session, user.id, key, "reminder:" + pid, payload, action)


@router.post("/reminders/{ident}/complete")
def complete(
    ident: str,
    data: CompletionInput,
    session: SessionDep,
    user: CurrentUser,
    key: Key = None,
):
    return mutate(
        session,
        user.id,
        key,
        "complete:" + ident,
        data.model_dump(),
        lambda: complete_reminder(session, user, ident, data.occurrence_at),
    )


@router.get("/pets/{pid}/completions")
def completions(pid: str, session: SessionDep, user: CurrentUser):
    owned(session, Pet, pid, user.id)
    rows = session.exec(
        select(TaskCompletion, Reminder)
        .join(Reminder, TaskCompletion.reminder_id == Reminder.id)
        .where(Reminder.pet_id == pid, Reminder.user_id == user.id)
        .order_by(TaskCompletion.completed_at.desc())
    ).all()
    return [{**c.model_dump(), "title": r.title} for c, r in rows]


@router.patch("/reminders/{ident}/pause")
def pause_reminder(ident: str, session: SessionDep, user: CurrentUser):
    r = owned(session, Reminder, ident, user.id)
    if r.task_id:
        raise HTTPException(422, "请通过计划状态调整计划提醒")
    if (
        r.recurrence == "once"
        and session.exec(
            select(TaskCompletion).where(TaskCompletion.reminder_id == r.id)
        ).first()
    ):
        raise HTTPException(409, "该一次性提醒已经完成，需要新建待办")
    r.paused = not r.paused
    session.add(r)
    session.commit()
    return r.model_dump()


@router.get("/conversations")
def conversations(session: SessionDep, user: CurrentUser, pet_id: str | None = None):
    if pet_id:
        owned(session, Pet, pet_id, user.id)
    rows = session.exec(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.pet_id == pet_id)
        .order_by(Conversation.created_at.desc())
    ).all()
    return [c.model_dump() for c in rows]


@router.get("/conversations/{ident}/messages")
def messages(ident: str, session: SessionDep, user: CurrentUser):
    c = owned(session, Conversation, ident, user.id)
    return [
        m.model_dump()
        for m in session.exec(
            select(Message)
            .where(Message.conversation_id == c.id)
            .order_by(Message.created_at)
        ).all()
    ]


@router.post("/chat")
async def chat(
    data: ChatInput, session: SessionDep, user: CurrentUser, key: Key = None
):
    from app.chat_requests import begin_chat, run_registered
    registry, replay = begin_chat(data, session, user, key)
    if replay is not None:
        if trace := current_execution.get():
            trace.replayed = True
        return replay
    return await run_registered(data, session, user, key, registry)


async def perform_chat(data, session, user, key):
    payload = data.model_dump()
    if data.model_id == "default":
        payload.pop("model_id")  # Preserve fingerprints for clients predating model selection.
    fp = fingerprint("chat", payload)
    old = lookup_idempotent(session, user.id, key, fp)
    if old is not None:
        if trace := current_execution.get():
            trace.replayed = True
        return old
    if data.pet_id:
        owned(session, Pet, data.pet_id, user.id)
    if data.conversation_id:
        c = owned(session, Conversation, data.conversation_id, user.id)
        if c.pet_id != data.pet_id:
            raise HTTPException(409, "会话与当前宠物不匹配")
    else:
        c = Conversation(user_id=user.id, pet_id=data.pet_id)
    history = [
        m.model_dump()
        for m in session.exec(
            select(Message)
            .where(Message.conversation_id == c.id)
            .order_by(Message.created_at)
        ).all()
    ]
    ctx = AgentContext(session, user, data.pet_id, supplement=data.context.model_dump(mode="json", exclude_none=True) if data.context else {}, answer_depth=data.answer_depth, model_selection=select_model(data.model_id))
    # No provisional inserts hold SQLite's writer lock while awaiting a model.
    session.commit()
    try:
        p = profile(ctx)
        risk_text = data.text + " " + " ".join(v for v in ctx.supplement.values() if isinstance(v, str))
        if ctx.supplement.get("nutrition"):
            risk_text += " " + ctx.supplement["nutrition"].get("current_symptoms", "")
        urgent = risks(risk_text, p["species"] if p else infer_species(data.text))
        write = None if urgent else explicit_write(ctx, data.text)
        # Only explicit instructions can consume the latest draft, never the model.
        if urgent:
            result = await respond(ctx, data.text, history, data.available_minutes)
        elif write:
            result = write
        elif data.text.strip() in ("保存计划", "保存这个计划", "确认保存计划"):
            latest = next(
                (
                    m
                    for m in reversed(history)
                    if m["role"] == "assistant" and m["metadata_json"].get("draft")
                ),
                None,
            )
            if not latest:
                result = {
                    "answer": "还没有可保存的草稿，请先生成计划。",
                    "mode": "demo"
                    if ctx.selected_model.demo
                    else "tools",
                    "sources": [],
                    "draft": None,
                    "urgent": False,
                }
            elif latest["metadata_json"].get("saved_plan_id"):
                result = {
                    "answer": "这份草稿已经保存，请在计划页查看或编辑。",
                    "mode": "tools",
                    "sources": [],
                    "draft": None,
                    "urgent": False,
                    "saved_plan_id": latest["metadata_json"]["saved_plan_id"],
                }
            else:
                draft = PlanDraft.model_validate(latest["metadata_json"]["draft"])
                ctx.authorization = "save_care_plan"
                ctx.authorized_payload = draft.model_dump(mode="json")
                plan = tool_save_care_plan(ctx, draft)
                draft_message = session.get(Message, latest["id"])
                draft_message.metadata_json = {
                    **draft_message.metadata_json,
                    "saved_plan_id": plan["id"],
                }
                session.add(draft_message)
                result = {
                    "answer": "计划已保存，任务已加入站内提醒。",
                    "mode": "tools",
                    "sources": [],
                    "draft": None,
                    "urgent": False,
                    "saved_plan_id": plan["id"],
                }
        else:
            result = await respond(ctx, data.text, history, data.available_minutes)
        result["model_selection"] = ctx.selected_model.public()
        result["model_used"] = ctx.selected_model.name if ctx.model_attempt else None
        if data.pet_id:
            owned(session, Pet, data.pet_id, user.id)
        if data.conversation_id:
            owned(session, Conversation, data.conversation_id, user.id)
        c.summary_json = ctx.memory
        session.add(c)
        if trace := current_execution.get():
            trace.mode = result["mode"]
            trace.retrieved(ctx.retrieved)
            result["execution"] = trace.summary()
        user_message = Message(conversation_id=c.id, role="user", content=data.text, metadata_json={"context": ctx.supplement, "answer_depth": data.answer_depth, "model_id": ctx.selected_model.id, "source": "用户本次提供，未自动更新档案"})
        session.add(user_message)
        for provenance in result.get("context_provenance", {}).values():
            if provenance["message_id"] == "current":
                provenance["message_id"] = user_message.id
        m = Message(
            conversation_id=c.id,
            role="assistant",
            content=result["answer"],
            metadata_json=result,
        )
        session.add(m)
        session.flush()
        response = {"conversation_id": c.id, "message": m.model_dump(), **result}
        if trace:
            trace.mark('commit_started')
        committed = commit_idempotent(session, user.id, key, fp, response)
        if trace:
            trace.mark('committed')
        return committed
    except ValidationError as e:
        session.rollback()
        raise HTTPException(
            422, "写入参数无效：" + "; ".join(x["msg"] for x in e.errors())
        )
    except (Exception, asyncio.CancelledError) as exc:
        if trace := current_execution.get():
            trace.retrieved(ctx.retrieved)
            trace.error_type = trace.error_type or type(exc).__name__
        session.rollback()
        # Preserve both the turn audit and known consumed tokens without counting twice.
        try:
            if ctx.model_attempt:
                session.add(ModelAttempt(id=ctx.model_attempt.id, user_id=user.id, status="failed", created_at=ctx.model_attempt.created_at))
            known = getattr(ctx, "known_model_usage", None)
            if known:
                session.add(known)
            elif trace and trace.model_requests and (trace.input_tokens or trace.output_tokens):
                session.add(ModelUsage(user_id=user.id, model=ctx.selected_model.name,
                                       requests=trace.model_requests, input_tokens=trace.input_tokens,
                                       output_tokens=trace.output_tokens))
            session.commit()
        except Exception:
            session.rollback()
        raise


@router.get("/usage")
def usage(session: SessionDep, user: CurrentUser):
    rows = session.exec(select(ModelUsage).where(ModelUsage.user_id == user.id)).all()
    return {
        "requests": sum(u.requests for u in rows),
        "input_tokens": sum(u.input_tokens for u in rows),
        "output_tokens": sum(u.output_tokens for u in rows),
    }


@router.get("/usage/quota")
def model_quota(session: SessionDep, user: CurrentUser):
    from app.model_adapter import quota_status
    return quota_status(session, user.id)

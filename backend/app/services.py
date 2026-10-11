import hashlib, json
from datetime import date, datetime, UTC
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from app.models import *
from app.schemas import PlanDraft, LogInput, ReminderInput
from app.clock import *
from app.species import supports, registry


def owned(session, model, ident, user_id):
    row = session.get(model, ident)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "数据不存在")
    return row


def pet_public(session, p):
    breed = session.get(Breed, p.breed_id) if p.breed_id else None
    weights = session.exec(
        select(CareLog)
        .where(CareLog.pet_id == p.id, CareLog.kind == "weight")
        .order_by(CareLog.occurred_at)
    ).all()
    months = p.estimated_age_months
    origin = p.birthday or p.age_estimated_on
    if origin:
        start = date.fromisoformat(origin)
        today = utc_now().date()
        elapsed = (
            (today.year - start.year) * 12
            + today.month
            - start.month
            - (today.day < start.day)
        )
        months = elapsed if p.birthday else (months or 0) + max(0, elapsed)
    return {
        **p.model_dump(),
        "breed_name": breed.name if breed else None,
        "capabilities": next((s["capabilities"] for s in registry() if s["id"] == p.species), {"profile": True, "manual_logs": True}),
        "age_months": months,
        "weight": weights[-1].value if weights else None,
        "weight_date": weights[-1].occurred_at if weights else None,
    }


def fingerprint(scope, payload):
    return hashlib.sha256(
        json.dumps(
            [scope, payload], ensure_ascii=False, sort_keys=True, default=str
        ).encode()
    ).hexdigest()


def lookup_idempotent(session, user_id, key, fp):
    if not key or len(key) > 200:
        raise HTTPException(400, "写入请求需要有效 Idempotency-Key")
    row = session.exec(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key
        )
    ).first()
    if row:
        if row.fingerprint != fp:
            raise HTTPException(409, "同一个幂等键不能用于不同请求")
        return row.result
    return None


def commit_idempotent(session, user_id, key, fp, result):
    session.add(
        IdempotencyRecord(user_id=user_id, key=key, fingerprint=fp, result=result)
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = lookup_idempotent(session, user_id, key, fp)
        if existing is not None:
            return existing
        raise HTTPException(409, "数据冲突，未完成写入")
    return result


def mutate(session, user_id, key, scope, payload, fn):
    fp = fingerprint(scope, payload)
    previous = lookup_idempotent(session, user_id, key, fp)
    if previous is not None:
        return previous
    try:
        result = fn()
        return commit_idempotent(session, user_id, key, fp, result)
    except (IntegrityError, HTTPException) as exc:
        session.rollback()
        # Initial profile insertion or optimistic revision checks may lose a race
        # before commit_idempotent. A committed identical request still wins.
        if isinstance(exc, IntegrityError) or exc.status_code == 409:
            previous = lookup_idempotent(session, user_id, key, fp)
            if previous is not None:
                return previous
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "数据已变更，请刷新后重试；本次未重复创建")
        raise
    except Exception:
        session.rollback()
        raise


def plan_public(session, p):
    tasks = session.exec(
        select(CareTask).where(CareTask.plan_id == p.id, CareTask.active == True)
    ).all()
    return {**p.model_dump(), "tasks": [t.model_dump() for t in tasks]}


def add_plan(session, user, pet_id, draft: PlanDraft):
    pet = owned(session, Pet, pet_id, user.id)
    if not supports(pet.species, "care_plan"):
        raise HTTPException(422, "该物种暂不支持个性化照护计划")
    plan = CarePlan(
        user_id=user.id, pet_id=pet_id, title=draft.title, basis=draft.basis
    )
    session.add(plan)
    session.flush()
    for d in draft.tasks:
        task = CareTask(plan_id=plan.id, **d.model_dump())
        session.add(task)
        session.flush()
        session.add(
            Reminder(
                user_id=user.id,
                pet_id=pet_id,
                task_id=task.id,
                title=task.title,
                recurrence=task.recurrence,
                timezone=user.timezone,
                local_time=task.local_time,
                weekday=task.weekday,
                due_at=first_task_due(
                    task.local_time, task.recurrence, task.weekday, user.timezone
                ),
            )
        )
    session.flush()
    return plan_public(session, plan)


def add_log(session, user, pet_id, data: LogInput):
    owned(session, Pet, pet_id, user.id)
    log = CareLog(
        user_id=user.id,
        pet_id=pet_id,
        **{**data.model_dump(), "occurred_at": iso(data.occurred_at)},
    )
    session.add(log)
    session.flush()
    return log.model_dump()


def add_reminder(session, user, pet_id, data: ReminderInput):
    owned(session, Pet, pet_id, user.id)
    local = localize(data.due_local, data.timezone)
    r = Reminder(
        user_id=user.id,
        pet_id=pet_id,
        title=data.title,
        recurrence=data.recurrence,
        timezone=data.timezone,
        local_time=local.strftime("%H:%M"),
        weekday=local.weekday(),
        due_at=iso(local),
    )
    session.add(r)
    session.flush()
    return r.model_dump()


def complete_reminder(session, user, rid, occurrence):
    r = owned(session, Reminder, rid, user.id)
    existing = session.exec(
        select(TaskCompletion).where(
            TaskCompletion.reminder_id == rid,
            TaskCompletion.occurrence_at == occurrence,
        )
    ).first()
    if existing:
        return {
            "completed": True,
            "reminder": r.model_dump(),
            "completion": existing.model_dump(),
        }
    if r.paused or occurrence != r.due_at:
        raise HTTPException(409, "该周期已变更或暂停，请刷新")
    if parse_utc(occurrence) > utc_now():
        raise HTTPException(409, "尚未到期待办不能打卡")
    c = TaskCompletion(user_id=user.id, reminder_id=rid, occurrence_at=occurrence)
    session.add(c)
    if r.recurrence == "once":
        r.paused = True
    else:
        next_due = next_occurrence(r, parse_utc(r.due_at))
        # Only the marked occurrence is recorded; intervening missed dates aren't marked complete.
        while next_due <= utc_now():
            next_due = next_occurrence(r, next_due)
        r.due_at = iso(next_due)
    session.add(r)
    session.flush()
    return {"completed": True, "reminder": r.model_dump(), "completion": c.model_dump()}

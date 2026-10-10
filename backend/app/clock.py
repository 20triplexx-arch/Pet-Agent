from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from fastapi import HTTPException


def utc_now():
    return datetime.now(UTC)


def parse_utc(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso(value: datetime):
    return value.astimezone(UTC).isoformat()


def localize(value: datetime, zone: str) -> datetime:
    # DST gaps reject; ambiguous wall time chooses first occurrence (fold=0).
    aware = value.replace(tzinfo=ZoneInfo(zone), fold=0)
    if aware.astimezone(UTC).astimezone(ZoneInfo(zone)).replace(tzinfo=None) != value:
        raise HTTPException(422, "该当地时间处于夏令时跳转缺口，请选择其他时间")
    return aware


def next_occurrence(reminder, current: datetime):
    local = current.astimezone(ZoneInfo(reminder.timezone))
    naive = local.replace(tzinfo=None) + timedelta(
        days=7 if reminder.recurrence == "weekly" else 1
    )
    hour, minute = map(int, reminder.local_time.split(":"))
    naive = naive.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Preserve local calendar time across DST. Gap moves forward to a valid instant.
    aware = naive.replace(tzinfo=ZoneInfo(reminder.timezone), fold=0)
    return aware.astimezone(UTC)


def first_task_due(local_time: str, recurrence: str, weekday: int, zone: str):
    current = utc_now().astimezone(ZoneInfo(zone))
    h, m = map(int, local_time.split(":"))
    candidate = current.replace(hour=h, minute=m, second=0, microsecond=0)
    if recurrence == "weekly":
        candidate += timedelta(days=(weekday - current.weekday()) % 7)
    # Today's unfinished daily task may already be due, so keep it today.
    return iso(candidate)

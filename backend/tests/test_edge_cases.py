from test_acceptance import post, chat
from app.models import Reminder
from app.clock import next_occurrence, parse_utc, ZoneInfo


def test_recurrence_dst_gap_returns_to_original_wall_time():
    r = Reminder(
        user_id="u",
        pet_id="p",
        title="daily",
        timezone="America/New_York",
        local_time="02:30",
        recurrence="daily",
        due_at="2026-03-07T07:30:00+00:00",
    )
    gap = next_occurrence(r, parse_utc(r.due_at))
    assert gap.astimezone(ZoneInfo(r.timezone)).hour == 3
    day_after = next_occurrence(r, gap)
    assert day_after.astimezone(ZoneInfo(r.timezone)).strftime("%H:%M") == "02:30"


def test_completed_once_cannot_be_resumed(client, headers, cat):
    r = post(
        client,
        headers,
        "/pets/" + cat["id"] + "/reminders",
        {"title": "once", "due_local": "2026-01-01T00:00", "timezone": "UTC"},
    ).json()
    post(
        client,
        headers,
        "/reminders/" + r["id"] + "/complete",
        {"occurrence_at": r["due_at"]},
    )
    assert (
        client.patch(
            "/api/v1/reminders/" + r["id"] + "/pause", headers=headers
        ).status_code
        == 409
    )
    assert client.get("/api/v1/reminders", headers=headers).json()[0]["completed"]


def test_young_cat_does_not_retrieve_senior_only_article(client, headers, cat):
    r = chat(client, headers, cat["id"], "年龄阶段").json()
    assert all(s["id"] != "cat-stage" for s in r["sources"])

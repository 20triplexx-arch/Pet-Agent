from datetime import timedelta
from pathlib import Path
import argparse
from alembic import command
from alembic.config import Config
from sqlmodel import Session, select
from app.core.db import engine
from app.core.security import get_password_hash
from app.models import *
from app.clock import utc_now, iso
from scripts.import_knowledge import import_file


def initialize(demo=False):
    command.upgrade(
        Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head"
    )
    with Session(engine) as s:
        import_file(Path(__file__).resolve().parents[1] / "data" / "knowledge.json", s)
        import_file(Path(__file__).resolve().parents[1] / "data" / "knowledge_nutrition.json", s)
        import_file(Path(__file__).resolve().parents[1] / "data" / "knowledge_care.json", s)
        if (
            demo
            and not s.exec(select(User).where(User.email == "demo@example.com")).first()
        ):
            u = User(
                email="demo@example.com",
                full_name="宠伴体验者",
                hashed_password=get_password_hash("Chongban2026!"),
            )
            s.add(u)
            s.flush()
            cat = Pet(
                user_id=u.id,
                name="奶糖",
                species="cat",
                estimated_age_months=8,
                age_estimated_on=utc_now().date().isoformat(),
                sex="female",
                neutered=False,
                diet="完整均衡幼猫粮",
                environment="室内生活，有安静的休息区",
                activity="喜欢逗猫棒",
            )
            dog = Pet(
                user_id=u.id,
                name="豆包",
                species="dog",
                estimated_age_months=36,
                age_estimated_on=utc_now().date().isoformat(),
                sex="male",
                neutered=True,
                diet="完整均衡成年犬粮",
                activity="每日外出，喜欢嗅闻",
                environment="公寓，与家人生活",
            )
            s.add(cat)
            s.add(dog)
            s.flush()
            for p, weight in [(cat, 3.1), (dog, 12.5)]:
                for n in range(4):
                    s.add(
                        CareLog(
                            user_id=u.id,
                            pet_id=p.id,
                            kind="weight",
                            value=round(weight + n * 0.1, 1),
                            occurred_at=iso(utc_now() - timedelta(days=(3 - n) * 7)),
                            note="示例体重记录",
                        )
                    )
                s.add(
                    Reminder(
                        user_id=u.id,
                        pet_id=p.id,
                        title="检查饮水并观察食欲",
                        timezone=u.timezone,
                        local_time="08:00",
                        due_at=iso(utc_now() - timedelta(hours=1)),
                        recurrence="daily",
                    )
                )
            s.commit()
    print(
        "Database initialized. Demo account: demo@example.com / Chongban2026!"
        if demo
        else "Database initialized."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    initialize(args.demo)

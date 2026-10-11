"""Explicit breed selection; coat colours and loose common names are not diagnoses."""
import json
from pathlib import Path
from fastapi import HTTPException
from sqlmodel import select
from app.models import Breed

DATA = Path(__file__).resolve().parents[1] / "data"
AMBIGUOUS = {"蓝猫": "蓝猫描述毛色，无法确定品种，请核对资料后选择。", "金渐层": "金渐层描述毛色，无法确定品种。", "柯基": "柯基有不同品种，本批详细资料为彭布罗克，请先确认。", "泰迪": "泰迪通常是贵宾的造型称呼；请确认是否为贵宾犬。"}


def seed_breeds(session):
    for item in json.loads((DATA / "breeds.json").read_text(encoding="utf-8")):
        row = session.get(Breed, item["id"])
        if row:
            for k, v in item.items():
                setattr(row, k, v)
        else:
            row = Breed(**item)
        session.add(row)
    session.flush()


def validate_breed(session, species, breed_id):
    if breed_id:
        breed = session.get(Breed, breed_id)
        if not breed or breed.species != species:
            raise HTTPException(422, "规范品种必须属于所选物种")


def find_breeds(session, species=None, query=""):
    rows = session.exec(select(Breed).order_by(Breed.species, Breed.name)).all()
    exact_query = query.strip().lower()
    candidates = [b.model_dump() for b in rows if (not species or b.species == species) and
        (not exact_query or exact_query in b.name.lower() or any(exact_query in a.lower() for a in b.aliases))]
    if query.strip() == "泰迪":
        candidates = [b.model_dump() for b in rows if b.id == "dog-poodle" and (not species or species == "dog")]
    if query.strip() in ("蓝猫", "金渐层"):
        candidates = []
    return {"items": candidates, "requires_confirmation": bool(query), "note": AMBIGUOUS.get(query.strip(), "选择后才关联档案；外观和商家称呼不等于血统证明。")}

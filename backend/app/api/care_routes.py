from typing import Annotated
from typing import Literal
from fastapi import APIRouter, Header, HTTPException, Query, Response
from app.api.deps import SessionDep, CurrentUser
from app.care_schemas import NutritionInput, NutritionProfileSave, NutritionSave, HospitalQuery, HospitalMapInput, VisitInput
from app.nutrition import profile_response, assess, store_profile, save_nutrition_plan
from app.hospitals import search_hospitals, map_usage, search_regions, hospital_map
from app.visit import build_summary
from app.services import mutate, owned
from app.models import Pet
from app.schemas import LogBatchInput
from app.services import add_log
from app.care_review import build_review, review_text

router = APIRouter(prefix="/api/v1")
Key = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("/pets/{pid}/care-review")
def care_review(pid: str, session: SessionDep, user: CurrentUser, days: int = 7):
    result = build_review(session, user, pid, days)
    return {**result, "text": review_text(result)}


@router.post("/pets/{pid}/logs/batch")
def batch_logs(pid: str, data: LogBatchInput, session: SessionDep, user: CurrentUser, key: Key = None):
    def action():
        owned(session, Pet, pid, user.id)
        return {"records": [add_log(session, user, pid, entry) for entry in data.entries], "saved": len(data.entries)}
    return mutate(session, user.id, key, f"care-log-batch:{pid}", data.model_dump(mode="json"), action)


@router.get("/pets/{pid}/nutrition/profile")
def nutrition_profile(pid: str, session: SessionDep, user: CurrentUser):
    return profile_response(session, user, pid)


@router.put("/pets/{pid}/nutrition/profile")
def save_profile(pid: str, data: NutritionProfileSave, session: SessionDep, user: CurrentUser, key: Key = None):
    def action():
        store_profile(session, user, pid, data.profile, data.revision)
        return profile_response(session, user, pid)
    return mutate(session, user.id, key, f"nutrition-profile:{pid}", data.model_dump(mode="json"), action)


@router.post("/pets/{pid}/nutrition/preview")
def nutrition_preview(pid: str, data: NutritionInput, session: SessionDep, user: CurrentUser):
    return assess(session, user, pid, data)


@router.post("/pets/{pid}/nutrition/plans")
def nutrition_save(pid: str, data: NutritionSave, session: SessionDep, user: CurrentUser, key: Key = None):
    return mutate(session, user.id, key, f"nutrition-plan:{pid}", data.model_dump(mode="json"),
                  lambda: save_nutrition_plan(session, user, pid, data))


@router.post("/hospitals/search")
async def hospitals(data: HospitalQuery, session: SessionDep, user: CurrentUser):
    if data.pet_id:
        owned(session, Pet, data.pet_id, user.id)
    return await search_hospitals(session.get_bind(), data, map_owner=user.id)


@router.get("/hospitals/usage")
def hospital_usage(session: SessionDep, user: CurrentUser, provider: Literal["auto", "amap", "tianditu"] | None = None):
    return map_usage(session.get_bind(), provider)


@router.get("/hospitals/regions")
async def hospital_regions(session: SessionDep, user: CurrentUser,
    keywords: Annotated[str, Query(min_length=2, max_length=80)],
    province_code: Annotated[str | None, Query(pattern=r"^[1-6]\d0000$")] = None):
    return await search_regions(session.get_bind(), keywords, province_code)


@router.post("/hospitals/map")
async def hospital_map_preview(data: HospitalMapInput, session: SessionDep, user: CurrentUser):
    content = await hospital_map(session.get_bind(), data.token, user.id)
    return Response(content=content, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/pets/{pid}/visit-summary/preview")
def visit_preview(pid: str, data: VisitInput, session: SessionDep, user: CurrentUser):
    return build_summary(session, user, pid, data)

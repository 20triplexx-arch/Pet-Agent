from typing import Annotated
from fastapi import APIRouter, Header, HTTPException
from app.api.deps import SessionDep, CurrentUser
from app.care_schemas import NutritionInput, NutritionProfileSave, NutritionSave, HospitalQuery, VisitInput
from app.nutrition import profile_response, assess, store_profile, save_nutrition_plan
from app.hospitals import search_hospitals, map_usage
from app.visit import build_summary
from app.services import mutate, owned
from app.models import Pet

router = APIRouter(prefix="/api/v1")
Key = Annotated[str | None, Header(alias="Idempotency-Key")]


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
    return await search_hospitals(session.get_bind(), data)


@router.get("/hospitals/usage")
def hospital_usage(session: SessionDep, user: CurrentUser):
    return map_usage(session.get_bind())


@router.post("/pets/{pid}/visit-summary/preview")
def visit_preview(pid: str, data: VisitInput, session: SessionDep, user: CurrentUser):
    return build_summary(session, user, pid, data)

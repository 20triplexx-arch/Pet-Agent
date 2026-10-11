from typing import Annotated
from fastapi import APIRouter, Header, HTTPException, UploadFile, File
from sqlmodel import select
from starlette.formparsers import MultiPartParser
from app.api.deps import CurrentUser, SessionDep
from app.models import Breed, ProductAssessment
from app.breeds import find_breeds
from app.product_schemas import AssessmentInput, AssessmentSave, NutritionFoodApply, LabelText
from app.products import assess_products, save_assessment, FOOD
from app import ocr
from app.services import mutate, owned
from app.nutrition import get_profile, store_profile, profile_response
from app.care_schemas import NutritionInput, FoodInput

router = APIRouter(prefix="/api/v1")
Key = Annotated[str | None, Header(alias="Idempotency-Key")]
MultiPartParser.spool_max_size = ocr.MAX_FILE + 1


@router.get("/breeds")
def breeds(session: SessionDep, user: CurrentUser, species: str | None = None, q: str = ""):
    return find_breeds(session, species, q[:100])


@router.get("/breeds/{bid}")
def breed(bid: str, session: SessionDep, user: CurrentUser):
    row = session.get(Breed, bid)
    if not row:
        raise HTTPException(404, "品种资料尚未收录")
    return row.model_dump()


@router.get("/products/ocr/status")
def ocr_status(user: CurrentUser):
    return ocr.status()


@router.post("/products/ocr")
def recognize_labels(user: CurrentUser, files: Annotated[list[UploadFile], File()]):
    try:
        if not 1 <= len(files) <= 3:
            raise HTTPException(422, "每次上传1至3张图片")
        return ocr.recognize([f.file.read(ocr.MAX_FILE + 1) for f in files])
    finally:
        for file in files:
            file.file.close()


@router.post("/products/assessments/preview")
def preview(data: AssessmentInput, session: SessionDep, user: CurrentUser):
    return assess_products(session, user, data)


@router.post("/products/label/parse")
def parse_label(data: LabelText, user: CurrentUser):
    return {"suggestions": ocr.extract_suggestions(data.raw_text), "confirmed": False}


@router.post("/products/assessments")
def save(data: AssessmentSave, session: SessionDep, user: CurrentUser, key: Key = None):
    return mutate(session, user.id, key, "product-assessment", data.model_dump(mode="json"), lambda: save_assessment(session, user, data))


@router.get("/products/assessments")
def history(session: SessionDep, user: CurrentUser, pet_id: str | None = None):
    if pet_id:
        from app.models import Pet
        owned(session, Pet, pet_id, user.id)
    rows = session.exec(select(ProductAssessment).where(ProductAssessment.user_id == user.id,
        ProductAssessment.pet_id == pet_id).order_by(ProductAssessment.created_at.desc()).limit(50)).all()
    return [{"id": r.id, "pet_id": r.pet_id, "created_at": r.created_at, "category": r.inputs["category"], "names": [p["name"] for p in r.inputs["products"]], "rule_version": r.rule_version} for r in rows]


@router.get("/products/assessments/{aid}")
def detail(aid: str, session: SessionDep, user: CurrentUser):
    return owned(session, ProductAssessment, aid, user.id).model_dump()


@router.delete("/products/assessments/{aid}")
def delete_assessment(aid: str, session: SessionDep, user: CurrentUser):
    row = owned(session, ProductAssessment, aid, user.id)
    session.delete(row)
    session.commit()
    return {"deleted": True}


@router.post("/products/assessments/{aid}/nutrition-food")
def apply_food(aid: str, data: NutritionFoodApply, session: SessionDep, user: CurrentUser, key: Key = None):
    row = owned(session, ProductAssessment, aid, user.id)
    def action():
        if not row.pet_id or row.inputs["category"] not in ("main", "treat"):
            raise HTTPException(422, "仅当前宠物的主粮或零食可添加到营养资料")
        inputs = AssessmentInput.model_validate(row.inputs)
        if data.product_index >= len(inputs.products):
            raise HTTPException(422, "产品序号不存在")
        fresh = assess_products(session, user, inputs)
        if fresh["preview_token"] != row.result["preview_token"]:
            raise HTTPException(409, "保存后档案或营养资料已变化，请重新比较并保存")
        if fresh["products"][data.product_index]["status"] in ("incompatible", "professional", "caution"):
            raise HTTPException(422, "该产品需先核对不匹配、风险或专业意见")
        product = inputs.products[data.product_index]
        nutrition = get_profile(session, user, row.pet_id)
        profile = NutritionInput.model_validate(nutrition.data) if nutrition else NutritionInput()
        if len(profile.foods) >= 15:
            raise HTTPException(422, "营养资料已有15种食物，请先在营养页整理")
        profile.foods.append(FoodInput(name=product.name[:100], kind="main" if inputs.category == "main" else "treat",
            complete_adult_food=product.adequacy == "complete" and product.life_stage in ("adult", "all", "senior"),
            energy=product.energy, energy_unit=product.energy_unit, portion_grams=product.portion_grams,
            daily_grams=None, label_note="用户从产品比较明确添加；未经厂家核实，实际摄入待补充"))
        profile.food_shares_confirmed = False
        profile.treats_confirmed = False
        store_profile(session, user, row.pet_id, profile, data.revision)
        return {**profile_response(session, user, row.pet_id), "message": "已添加食物资料，未修改喂食量、计划或提醒。请补充实际摄入后重新评估。"}
    return mutate(session, user.id, key, "product-food:" + aid, data.model_dump(mode="json"), action)

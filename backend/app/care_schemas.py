from datetime import date, datetime, UTC
from typing import Literal
from pydantic import Field, model_validator, field_validator
from app.schemas import Strict, TaskDraft


class FoodInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["main", "treat"] = "main"
    complete_adult_food: bool | None = None
    energy: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)
    energy_unit: Literal["kcal_100g", "kcal_kg", "kj_100g", "kj_kg", "kcal_portion", "kj_portion"] = "kcal_100g"
    portion_grams: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    daily_grams: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    label_note: str = Field(default="用户填写的包装信息，未经应用核实", max_length=500)


class NutritionInput(Strict):
    life_stage: Literal["adult", "growing", "senior", "unknown"] = "unknown"
    bcs: int | None = Field(default=None, ge=1, le=9)
    muscle: Literal["normal", "loss", "unknown"] = "unknown"
    assessed_on: date | None = None
    assessor: Literal["owner", "vet", "unknown"] = "unknown"
    activity_level: Literal["low", "normal", "high", "unknown"] = "unknown"
    health_status: Literal["healthy", "unwell", "unknown"] = "unknown"
    pregnancy_lactation: Literal["no", "yes", "unknown"] = "unknown"
    diet_restrictions: str = Field(default="", max_length=2000)
    current_symptoms: str = Field(default="", max_length=2000)
    weight_confirmed: bool = False
    treats_confirmed: bool = False
    food_shares_confirmed: bool = False
    foods: list[FoodInput] = Field(default_factory=list, max_length=15)

    @field_validator("assessed_on")
    @classmethod
    def assessment_date(cls, value):
        if value and value > datetime.now(UTC).date():
            raise ValueError("评估日期不能在未来")
        return value


class NutritionProfileSave(Strict):
    profile: NutritionInput
    revision: int = Field(ge=0)


class NutritionSave(NutritionProfileSave):
    preview_token: str = Field(min_length=64, max_length=64)
    daily_target_kcal: float | None = Field(default=None, gt=0, le=50000, allow_inf_nan=False)
    planned_treat_kcal: float = Field(default=0, ge=0, le=50000, allow_inf_nan=False)
    meal_times: list[str] = Field(default_factory=lambda: ["08:00", "18:00"], min_length=1, max_length=6)

    @field_validator("meal_times")
    @classmethod
    def times(cls, value):
        for t in value:
            TaskDraft.valid_time(t)
        if len(set(value)) != len(value):
            raise ValueError("餐次时间不能重复")
        return value


class HospitalQuery(Strict):
    provider: Literal["auto", "amap", "tianditu"] | None = None
    city: str = Field(default="", max_length=80)
    district: str = Field(default="", max_length=80)
    street: str = Field(default="", max_length=80)
    address_detail: str = Field(default="", max_length=160)
    region_adcode: str | None = Field(default=None, pattern=r"^[1-6]\d{5}$")
    longitude: float | None = Field(default=None, ge=73, le=136, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=18, le=54, allow_inf_nan=False)
    coordinate_system: Literal["wgs84", "gcj02"] = "wgs84"
    radius_km: Literal[1, 3, 5, 10, 20] = 5
    pet_id: str | None = None

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("经纬度需要成对提供")
        if self.longitude is None and not self.city.strip():
            raise ValueError("请提供城市或授权定位")
        if self.longitude is not None and (self.street.strip() or self.address_detail.strip()):
            raise ValueError("具体地点与浏览器定位请选择一种查询方式")
        return self


class HospitalMapInput(Strict):
    token: str = Field(min_length=32, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class VisitInput(Strict):
    started_at: datetime | None = None
    observation: str = Field(default="", max_length=3000)
    medicines_as_reported: str = Field(default="", max_length=2000)

    @field_validator("started_at")
    @classmethod
    def started(cls, value):
        if value and (value.tzinfo is None or value > datetime.now(UTC)):
            raise ValueError("症状时间需要包含时区且不能在未来")
        return value

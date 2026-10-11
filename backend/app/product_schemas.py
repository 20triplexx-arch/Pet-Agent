from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from app.schemas import Strict

Category = Literal["main", "complement", "treat", "bowls", "litter", "carriers", "beds", "scratch", "toys", "harness", "grooming", "dental", "cleaning"]
EnergyUnit = Literal["kcal_100g", "kcal_kg", "kj_100g", "kj_kg", "kcal_portion", "kj_portion"]


class AnalysisValue(Strict):
    nutrient: str = Field(min_length=1, max_length=60)
    value: float = Field(ge=0, le=100, allow_inf_nan=False)
    qualifier: Literal["min", "max", "typical"]
    unit: Literal["percent"] = "percent"


class ProductInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    brand: str = Field(default="", max_length=100)
    formula: str = Field(default="", max_length=200)
    market_version: str = Field(default="", max_length=200)
    target_species: list[Literal["cat", "dog"]] = Field(default_factory=list, max_length=2)
    life_stage: Literal["adult", "growing", "senior", "all", "unknown"] = "unknown"
    adequacy: Literal["complete", "complement", "unknown"] = "unknown"
    adequacy_statement: str = Field(default="", max_length=1000)
    energy: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)
    energy_unit: EnergyUnit = "kcal_100g"
    portion_grams: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    net_grams: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)
    daily_grams: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    price: float | None = Field(default=None, gt=0, le=1000000, allow_inf_nan=False)
    price_date: date | None = None
    currency: Literal["CNY", "USD", "EUR", "HKD"] = "CNY"
    ingredients: str = Field(default="", max_length=3000)
    analysis: list[AnalysisValue] = Field(default_factory=list, max_length=12)
    processing: Literal["cooked", "raw", "unknown"] = "unknown"
    therapeutic: bool = False
    material: str = Field(default="", max_length=500)
    dimensions: str = Field(default="", max_length=500)
    size_confirmed: bool | None = None
    cleaning_method: str = Field(default="", max_length=1000)
    warnings: str = Field(default="", max_length=2000)
    expected_lifetime_months: float | None = Field(default=None, gt=0, le=240, allow_inf_nan=False)
    monthly_consumables: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    manufacturer_evidence: str = Field(default="", max_length=2000)
    source_note: str = Field(default="用户提供的包装资料，未经厂家核实", max_length=2000)
    raw_label: str = Field(default="", max_length=12000)
    origin: Literal["manual", "ocr"] = "manual"
    label_confirmed: bool = False

    @model_validator(mode="after")
    def critical_values_confirmed(self):
        if not self.label_confirmed:
            raise ValueError("请先核对并确认产品资料，特别是热量、单位、净含量和适用声明")
        if not self.name.strip():
            raise ValueError("产品名称不能为空")
        if self.price_date and self.price_date > date.today():
            raise ValueError("价格日期不能在未来")
        return self


class AssessmentInput(Strict):
    pet_id: str | None = None
    species: Literal["cat", "dog"]
    category: Category
    products: list[ProductInput] = Field(min_length=1, max_length=3)


class AssessmentSave(Strict):
    inputs: AssessmentInput
    preview_token: str
    confirm: Literal[True]


class NutritionFoodApply(Strict):
    product_index: int = Field(ge=0, le=2)
    revision: int = Field(ge=0)
    confirm: Literal[True]


class LabelText(Strict):
    raw_text: str = Field(min_length=1, max_length=12000)

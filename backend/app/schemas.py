from datetime import date, datetime, UTC
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import (
    BaseModel,
    Field,
    EmailStr,
    field_validator,
    model_validator,
    ConfigDict,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Register(Strict):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=60)


class SettingsUpdate(Strict):
    full_name: str = Field(max_length=60)
    timezone: str

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, v):
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("需要有效 IANA 时区")
        return v


class PetInput(Strict):
    name: str = Field(min_length=1, max_length=60)
    species: str = Field(min_length=1, max_length=100)
    breed: str | None = Field(default=None, max_length=100)
    breed_id: str | None = Field(default=None, max_length=100)
    birthday: date | None = None
    estimated_age_months: int | None = Field(default=None, ge=0, le=600)
    sex: Literal["male", "female", "unknown"] | None = None
    neutered: bool | None = None
    diet: str | None = Field(default=None, max_length=2000)
    activity: str | None = Field(default=None, max_length=2000)
    environment: str | None = Field(default=None, max_length=2000)
    allergies: str | None = Field(default=None, max_length=2000)
    medical_history: str | None = Field(default=None, max_length=2000)
    vet_advice: str | None = Field(default=None, max_length=2000)

    @field_validator("birthday")
    @classmethod
    def no_future(cls, v):
        if v and v > date.today():
            raise ValueError("生日不能在未来")
        return v

    @field_validator("name", "species")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("不能为空")
        return v.strip()


class LogInput(Strict):
    kind: Literal["weight", "diet", "activity", "grooming", "observation"]
    value: float | None = Field(default=None, gt=0, le=200, allow_inf_nan=False)
    note: str = Field(default="", max_length=3000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("时间必须包含时区")
        if v > datetime.now(UTC):
            raise ValueError("不能记录未来发生的照护")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def weight_value(self):
        if self.kind == "weight" and self.value is None:
            raise ValueError("体重需要公斤数值")
        if self.kind != "weight" and not self.note.strip():
            raise ValueError("需要填写记录")
        return self


class TaskDraft(Strict):
    title: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=2000)
    basis: str = Field(min_length=1, max_length=2000)
    recurrence: Literal["daily", "weekly"] = "daily"
    local_time: str = "08:00"
    weekday: int = Field(default=0, ge=0, le=6)

    @field_validator("local_time")
    @classmethod
    def valid_time(cls, v):
        import re

        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("需要 HH:MM")
        return v


class PlanDraft(Strict):
    title: str = Field(min_length=1, max_length=100)
    basis: str = Field(min_length=1, max_length=3000)
    tasks: list[TaskDraft] = Field(min_length=1, max_length=30)


class PlanEdit(PlanDraft):
    revision: int = Field(ge=1)


class PlanStatus(Strict):
    status: Literal["active", "paused", "completed"]


class ReminderInput(Strict):
    title: str = Field(min_length=1, max_length=100)
    due_local: datetime
    recurrence: Literal["once", "daily", "weekly"] = "once"
    timezone: str

    @field_validator("timezone")
    @classmethod
    def zone(cls, v):
        return SettingsUpdate.valid_zone(v)

    @field_validator("due_local")
    @classmethod
    def local(cls, v):
        if v.tzinfo is not None:
            raise ValueError("due_local 使用不带偏移的当地时间，并另填 IANA 时区")
        return v


class CompletionInput(Strict):
    occurrence_at: str


class ChatContext(Strict):
    goal: str = Field(default="", max_length=2000)
    observations: str = Field(default="", max_length=3000)
    timeline: str = Field(default="", max_length=2000)
    diet_activity: str = Field(default="", max_length=3000)
    environment_changes: str = Field(default="", max_length=2000)
    professional_advice: str = Field(default="", max_length=3000)
    # Imported lazily below to avoid the care_schemas -> schemas cycle.
    nutrition: dict | None = None

    @field_validator("nutrition")
    @classmethod
    def nutrition_input(cls, value):
        if value is not None:
            from app.care_schemas import NutritionInput
            return NutritionInput.model_validate(value).model_dump(mode="json", exclude_unset=True)
        return None


class ChatInput(Strict):
    pet_id: str | None = None
    conversation_id: str | None = None
    text: str = Field(min_length=1, max_length=12000)
    available_minutes: int = Field(default=30, ge=5, le=240)
    context: ChatContext | None = None
    answer_depth: Literal["auto", "brief", "detailed"] = "auto"

    @field_validator("text")
    @classmethod
    def message_not_blank(cls, value):
        if not value.strip():
            raise ValueError("请填写提问内容")
        return value


class PlanRequest(Strict):
    available_minutes: int = Field(default=30, ge=5, le=240)


class TimeConvert(Strict):
    local: datetime
    timezone: str

    @field_validator("timezone")
    @classmethod
    def zone(cls, v):
        return SettingsUpdate.valid_zone(v)

    @field_validator("local")
    @classmethod
    def naive(cls, v):
        if v.tzinfo is not None:
            raise ValueError("需要不带偏移的当地时间")
        return v


class CitationSection(Strict):
    article_id: str
    heading: str


class AgentAnswer(Strict):
    answer: str
    citation_ids: list[str] = Field(default_factory=list)
    draft: PlanDraft | None = None
    citation_sections: list[CitationSection] = Field(default_factory=list, max_length=30)

from datetime import datetime, UTC
from uuid import uuid4
from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


class User(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    email: str = Field(unique=True, index=True)
    full_name: str = ""
    hashed_password: str
    timezone: str = "Asia/Shanghai"
    is_active: bool = True
    created_at: str = Field(default_factory=now)


class Pet(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    name: str
    species: str
    breed: str | None = None
    breed_id: str | None = Field(default=None, foreign_key="breed.id", index=True)
    birthday: str | None = None
    estimated_age_months: int | None = None
    age_estimated_on: str | None = None
    sex: str | None = None
    neutered: bool | None = None
    diet: str | None = None
    activity: str | None = None
    environment: str | None = None
    allergies: str | None = None
    medical_history: str | None = None
    vet_advice: str | None = None
    created_at: str = Field(default_factory=now)


class KnowledgeArticle(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    body: str
    species: list[str] = Field(sa_column=Column(JSON, nullable=False))
    life_stages: list[str] = Field(sa_column=Column(JSON, nullable=False))
    topic: str = Field(index=True)
    keywords: list[str] = Field(sa_column=Column(JSON, nullable=False))
    source_organization: str
    source_url: str
    source_version: str
    published_at: str | None = None
    ingested_at: str
    updated_at: str
    review_status: str = "editorial_summary_unreviewed"
    content_kind: str = Field(default="care", index=True)
    breed_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    references: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class Breed(SQLModel, table=True):
    id: str = Field(primary_key=True)
    species: str = Field(index=True)
    name: str
    classification: str = "pedigree"
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    summary: str
    article_id: str


class ProductAssessment(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str | None = Field(default=None, foreign_key="pet.id", index=True)
    inputs: dict = Field(sa_column=Column(JSON, nullable=False))
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    rule_version: str
    created_at: str = Field(default_factory=now)


class Bookmark(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "article_id"),)
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    article_id: str = Field(foreign_key="knowledgearticle.id")


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str | None = Field(default=None, foreign_key="pet.id", index=True)
    created_at: str = Field(default_factory=now)


class Message(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True)
    role: str
    content: str
    metadata_json: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    created_at: str = Field(default_factory=now)


class CarePlan(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str = Field(foreign_key="pet.id", index=True)
    title: str
    basis: str
    status: str = "active"
    revision: int = 1
    provenance: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: str = Field(default_factory=now)


class CareTask(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    plan_id: str = Field(foreign_key="careplan.id", index=True)
    title: str
    instructions: str
    basis: str
    recurrence: str = "daily"
    local_time: str = "08:00"
    weekday: int = 0
    active: bool = True


class Reminder(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str = Field(foreign_key="pet.id", index=True)
    task_id: str | None = Field(default=None, foreign_key="caretask.id", index=True)
    title: str
    recurrence: str = "once"
    timezone: str
    local_time: str
    weekday: int = 0
    due_at: str
    paused: bool = False
    created_at: str = Field(default_factory=now)


class TaskCompletion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("reminder_id", "occurrence_at"),)
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    reminder_id: str = Field(foreign_key="reminder.id")
    occurrence_at: str
    completed_at: str = Field(default_factory=now)


class CareLog(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str = Field(foreign_key="pet.id", index=True)
    kind: str
    value: float | None = None
    note: str = ""
    occurred_at: str
    created_at: str = Field(default_factory=now)


class IdempotencyRecord(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "key"),)
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    key: str
    fingerprint: str
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: str = Field(default_factory=now)


class ModelUsage(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    created_at: str = Field(default_factory=now)


class PetNutritionProfile(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    pet_id: str = Field(foreign_key="pet.id", unique=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    revision: int = 1
    active_plan_id: str | None = Field(default=None, foreign_key="careplan.id")
    updated_at: str = Field(default_factory=now)


class ExternalApiUsage(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("provider", "period"),)
    id: str = Field(default_factory=uid, primary_key=True)
    provider: str
    period: str
    requests: int = 0


class TokenPayload(SQLModel):
    sub: str | None = None

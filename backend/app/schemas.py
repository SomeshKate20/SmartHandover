from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TaskStatus = Literal["Open", "In Progress", "Blocked", "Completed"]


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    meeting_type: str = Field(default="Meeting", min_length=1, max_length=80)
    meeting_date: date
    agenda: str = Field(min_length=1)
    participants: list[str] = Field(default_factory=list)
    raw_notes: str = Field(min_length=1)

    @field_validator("participants")
    @classmethod
    def clean_participants(cls, value: list[str]) -> list[str]:
        return [participant.strip() for participant in value if participant.strip()]


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    meeting_type: str | None = Field(default=None, min_length=1, max_length=80)
    meeting_date: date | None = None
    agenda: str | None = Field(default=None, min_length=1)
    participants: list[str] | None = None
    raw_notes: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    decisions: str | None = None
    status: str | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("participants")
    @classmethod
    def clean_optional_participants(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return [participant.strip() for participant in value if participant.strip()]


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    meeting_type: str
    meeting_date: date
    agenda: str
    participants: list[str]
    raw_notes: str
    summary: str | None
    decisions: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    status: TaskStatus = "Open"
    origin_meeting_id: int | None = None
    completion_note: str | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    origin_meeting_id: int | None = None
    completion_note: str | None = None


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    owner: str | None
    assignee_clerk_id: str | None
    due_date: date | None
    status: TaskStatus
    origin_meeting_id: int | None
    completion_note: str | None
    created_at: datetime
    updated_at: datetime


class TaskHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    event_type: str
    details: str
    created_at: datetime


KnowledgeVisibility = Literal["private", "shared"]


class KnowledgeArticleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(default="General", min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    visibility: KnowledgeVisibility = "private"
    related_meeting_id: int | None = None

    @field_validator("title", "content", "category")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: dict[str, str] = {}
        for item in value:
            tag = item.strip().lower()
            if not tag:
                continue
            if len(tag) > 50:
                raise ValueError("Tags must be 50 characters or fewer")
            normalized.setdefault(tag, tag)
        return list(normalized.values())


class KnowledgeArticleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=30)
    visibility: KnowledgeVisibility | None = None
    related_meeting_id: int | None = None

    @field_validator("title", "content", "category")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("This field must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return KnowledgeArticleCreate.normalize_tags(value)


class KnowledgeArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str
    tags: list[str]
    creator_clerk_id: str
    visibility: KnowledgeVisibility
    related_meeting_id: int | None
    created_at: datetime
    updated_at: datetime


class CarryForwardRequest(BaseModel):
    meeting_id: int


class NotesProcessRequest(BaseModel):
    raw_notes: str = Field(min_length=1)
    meeting_date: date | None = None
    participants: list[str] = Field(default_factory=list)


class AiActionItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = Field(default=None, max_length=120)
    due_date: date | None = None
    blocker: str | None = None


class AiMeetingAnalysis(BaseModel):
    summary: str = Field(min_length=1)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[AiActionItem] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)

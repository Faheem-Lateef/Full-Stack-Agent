"""Validated support requests and structured model output."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkspaceInput(StrictRequest):
    name: str = Field(min_length=1, max_length=120)
    tone: str = Field(default="Friendly, concise and professional", max_length=500)
    escalation: str = Field(default="Ask a support team member to review.", max_length=1000)


class DeleteWorkspaceInput(StrictRequest):
    name: str = Field(min_length=1, max_length=120)


class InviteInput(StrictRequest):
    email: EmailStr
    role: Literal["admin", "agent"] = "agent"


class AcceptInput(StrictRequest):
    token: str = Field(min_length=32, max_length=200)


class RoleInput(StrictRequest):
    role: Literal["owner", "admin", "agent"]


class CaseInput(StrictRequest):
    question: str = Field(min_length=5, max_length=10000)


class GenerateInput(StrictRequest):
    request_key: UUID


class DraftInput(StrictRequest):
    version: int = Field(ge=1)
    reply: str = Field(min_length=1, max_length=15000)


class VersionInput(StrictRequest):
    version: int = Field(ge=1)


class FeedbackInput(StrictRequest):
    feedback: str = Field(min_length=1, max_length=1000)


class SupportAnswer(StrictRequest):
    outcome: Literal[
        "answerable", "needs_clarification", "insufficient_evidence", "conflicting_sources"
    ]
    reply: str = Field(min_length=1, max_length=15000)
    citation_ids: list[UUID] = Field(default_factory=list, max_length=8)

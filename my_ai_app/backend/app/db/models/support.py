"""Workspace-owned support data; personal chat and memory stay separate."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Workspace(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_workspaces"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    tone: Mapped[str] = mapped_column(String(500), default="Friendly, concise and professional")
    escalation: Mapped[str] = mapped_column(
        String(1000), default="Ask a support team member to review."
    )
    generation_limit: Mapped[int] = mapped_column(Integer, default=100)


class Membership(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_memberships"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(10))


class Invitation(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(10))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(default=False)


class Document(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_documents"
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(200))
    checksum: Mapped[str] = mapped_column(String(64))
    # Private originals live in PostgreSQL for the bounded native pilot.
    original: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    size: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(String(500))
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    embedding_model: Mapped[str | None] = mapped_column(String(100))


class Chunk(Base):
    __tablename__ = "support_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["support_documents.workspace_id", "support_documents.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "ordinal"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(JSONB)


class SupportCase(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_cases"
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="open")


class Draft(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "case_id"],
            ["support_cases.workspace_id", "support_cases.id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reply: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(30))
    citations: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    feedback: Mapped[str | None] = mapped_column(String(1000))


class SupportJob(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_jobs"
    __table_args__ = (UniqueConstraint("workspace_id", "request_key"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
    usage: Mapped[dict] = mapped_column(JSONB, default=dict)


class SupportAudit(Base, TimestampMixin):
    __mapper_args__ = {"eager_defaults": True}
    __tablename__ = "support_audit"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_workspaces.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

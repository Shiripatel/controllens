from datetime import datetime, date, timezone
from sqlalchemy import (String, Integer, Text, DateTime, Date, ForeignKey, JSON, Boolean,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


ROLES = ("admin", "manager", "reviewer", "preparer", "viewer")

# Control workflow states, in order
STATUSES = [
    "not_started",
    "design_in_progress", "design_prepared", "design_reviewed",
    "operating_in_progress", "operating_prepared", "operating_reviewed",
]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="preparer")
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Engagement(Base):
    __tablename__ = "engagements"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    client: Mapped[str] = mapped_column(String(255))
    engagement_type: Mapped[str] = mapped_column(String(50), default="SOX ITGC")
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | locked | archived
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    systems: Mapped[list["System"]] = relationship(back_populates="engagement", cascade="all, delete-orphan")
    controls: Mapped[list["Control"]] = relationship(back_populates="engagement", cascade="all, delete-orphan")
    members: Mapped[list["EngagementMember"]] = relationship(cascade="all, delete-orphan")


class EngagementMember(Base):
    __tablename__ = "engagement_members"
    __table_args__ = (UniqueConstraint("engagement_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped[User] = relationship()


class System(Base):
    """An in-scope application / layer (e.g. SAP ECC – application, Oracle DB, Linux OS)."""
    __tablename__ = "systems"
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    layer: Mapped[str] = mapped_column(String(50), default="Application")  # Application | Database | OS | Network | Tool
    description: Mapped[str] = mapped_column(Text, default="")
    engagement: Mapped[Engagement] = relationship(back_populates="systems")


class Control(Base):
    __tablename__ = "controls"
    id: Mapped[int] = mapped_column(primary_key=True)
    engagement_id: Mapped[int] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), index=True)
    system_id: Mapped[int | None] = mapped_column(ForeignKey("systems.id", ondelete="SET NULL"), nullable=True)
    library_ref: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ref: Mapped[str] = mapped_column(String(40))
    domain: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(Text, default="")
    frequency: Mapped[str] = mapped_column(String(40))
    nature: Mapped[str] = mapped_column(String(40))
    risk_rating: Mapped[str] = mapped_column(String(10), default="Moderate")  # Low | Moderate | High
    key_control: Mapped[bool] = mapped_column(Boolean, default=True)
    attributes: Mapped[list] = mapped_column(JSON, default=list)
    design_procedures: Mapped[list] = mapped_column(JSON, default=list)
    operating_procedures: Mapped[list] = mapped_column(JSON, default=list)
    expected_evidence: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    preparer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Human-confirmed conclusions (agents propose, humans decide)
    design_conclusion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    operating_conclusion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    engagement: Mapped[Engagement] = relationship(back_populates="controls")
    system: Mapped[System | None] = relationship()


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    purpose: Mapped[str] = mapped_column(String(20), default="general")  # design | operating | population | general
    description: Mapped[str] = mapped_column(Text, default="")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extraction_note: Mapped[str] = mapped_column(String(255), default="")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)  # soft delete, keeps the record
    # Intake check: what the file is, which attributes it supports, quality issues
    intake_status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | done | failed
    intake: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EvidenceRequest(Base):
    """An item on the evidence request (PBC) list for a control."""
    __tablename__ = "evidence_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | received | closed
    source: Mapped[str] = mapped_column(String(10), default="human")  # human | agent
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    population_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    population_size: Mapped[int] = mapped_column(Integer)
    sample_size: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(40))  # random | test_of_one | all_items
    seed: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSON)  # list of {index, row}
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(20))  # design | operating | reviewer
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | succeeded | failed
    provider: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)  # [{key, title, status, output, started, finished}]
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guardrail_flags: Mapped[list] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewNote(Base):
    __tablename__ = "review_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(10))  # design | operating
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="human")  # human | reviewer_agent
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | addressed | closed
    response: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Exception_(Base):
    __tablename__ = "exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    sample_item: Mapped[str] = mapped_column(String(255), default="")
    attribute_id: Mapped[str] = mapped_column(String(10), default="")
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="deficiency")  # deficiency | significant | material
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | accepted | remediated
    source: Mapped[str] = mapped_column(String(20), default="operating_agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SignOff(Base):
    __tablename__ = "signoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("controls.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(10))  # design | operating
    kind: Mapped[str] = mapped_column(String(10))  # prepare | review
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship()


class AuditLog(Base):
    """Append-only, hash-chained log. Each row's hash covers the previous row's hash,
    so any edit or deletion breaks the chain and is detected by /audit/verify."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    engagement_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    control_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

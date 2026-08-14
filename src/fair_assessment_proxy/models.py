# from enum import Enum
from __future__ import annotations
import enum
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
import uuid
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from fair_assessment_proxy.db import Base
from enum import Enum
from sqlalchemy import DateTime, Enum as SQLEnum, String, func


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )

    pid: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    assessors: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    cached: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class FairOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


fair_outcome = SQLEnum(
    FairOutcome,
    name="fair_outcome",
    values_callable=lambda enum: [e.value for e in enum],
)


class HarmonizedAssessment(Base):
    __tablename__ = "harmonized_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    assessment_id: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    doi: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    # Findable
    f: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    f4: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Accessible
    a: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1_1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a1_2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    a2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Interoperable
    i: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    i3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    # Reusable
    r: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_1: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_2: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)
    r1_3: Mapped[FairOutcome] = mapped_column(fair_outcome, nullable=False)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RawAssessment(Base):
    __tablename__ = "raw_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    assessment_id: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    doi: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
    )

    assessor_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    raw: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AssessmentMode(str, enum.Enum):
    public = "public"
    cached = "cached"
    offline = "offline"


class AssessmentRequest(BaseModel):
    pid: str = Field(..., examples=["https://doi.org/10.1594/PANGAEA.908011"])
    mode: AssessmentMode = AssessmentMode.public
    cached: bool = False
    assessors: list[str] | None = None


class AssessorResult(BaseModel):
    assessor_id: str
    name: str
    status: str
    version: str | None = None
    raw: Any | None = None
    # normalised: dict[str, Any] | None = None
    normalised: NormalizedAssessorResult | None = None
    error: str | None = None


class AssessorStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    completed_with_errors = "completed_with_errors"
    failed = "failed"


class FairOutcome(str, enum.Enum):
    pass_ = "pass"
    partial = "partial"
    fail = "fail"
    indeterminate = "indeterminate"
    error = "error"
    not_applicable = "not_applicable"


class AssessmentRaw(Base):
    """
    Stores the complete untouched response from each backend assessor.

    One row per:
        assessment_id + assessor

    Example assessors:
        fuji
        fair_champion
    """

    __tablename__ = "assessment_raw"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    assessment_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    doi: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )

    assessor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    assessor_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    assessor_version: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metric_version: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    mode: Mapped[AssessmentMode] = mapped_column(
        SAEnum(AssessmentMode, name="assessment_mode"),
        nullable=False,
    )

    status: Mapped[AssessorStatus] = mapped_column(
        SAEnum(AssessorStatus, name="assessor_status"),
        nullable=False,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "assessor",
            name="uq_assessment_raw_assessment_assessor",
        ),
        Index(
            "ix_assessment_raw_raw_gin",
            "raw",
            postgresql_using="gin",
        ),
    )


assessment_mode_enum = SAEnum(
    AssessmentMode,
    name="assessment_mode",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

assessor_status_enum = SAEnum(
    AssessorStatus,
    name="assessor_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)

fair_outcome_enum = SAEnum(
    FairOutcome,
    name="fair_outcome",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class AssessmentNormalized(Base):
    """
    Outcome-only FAIR summary.

    One row per:
        assessment_id + assessor + profile
    """

    __tablename__ = "assessment_normalized"

    id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    assessment_id: Mapped[PG_UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    doi: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )

    assessor: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    profile: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
    )

    mode: Mapped[AssessmentMode] = mapped_column(
        assessment_mode_enum,
        nullable=False,
    )

    status: Mapped[AssessorStatus] = mapped_column(
        assessor_status_enum,
        nullable=False,
    )

    overall: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    f: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    a: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    i: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    r: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    f1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    f2: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    f3: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    f4: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    a1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    a1_1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    a1_2: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    a2: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    i1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    i2: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    i3: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    r1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    r1_1: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    r1_2: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)
    r1_3: Mapped[FairOutcome | None] = mapped_column(fair_outcome_enum)

    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "assessor",
            "profile",
            name="uq_assessment_normalized_assessment_assessor_profile",
        ),
    )


class NormalizedAssessorResult(BaseModel):
    assessor: str
    profile: str
    status: str

    overall: FairOutcome | None = None

    f: FairOutcome | None = None
    a: FairOutcome | None = None
    i: FairOutcome | None = None
    r: FairOutcome | None = None

    f1: FairOutcome | None = None
    f2: FairOutcome | None = None
    f3: FairOutcome | None = None
    f4: FairOutcome | None = None

    a1: FairOutcome | None = None
    a1_1: FairOutcome | None = None
    a1_2: FairOutcome | None = None
    a2: FairOutcome | None = None

    i1: FairOutcome | None = None
    i2: FairOutcome | None = None
    i3: FairOutcome | None = None

    r1: FairOutcome | None = None
    r1_1: FairOutcome | None = None
    r1_2: FairOutcome | None = None
    r1_3: FairOutcome | None = None

    extra: dict[str, Any] = {}

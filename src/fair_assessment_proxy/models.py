from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssessmentMode(str, Enum):
    public = "public"
    cached = "cached"


class AssessmentRequest(BaseModel):
    pid: str = Field(..., examples=["https://doi.org/10.1594/PANGAEA.908011"])
    mode: AssessmentMode = AssessmentMode.public
    assessors: list[str] | None = None


class AssessorResult(BaseModel):
    assessor_id: str
    name: str
    status: str
    raw: Any | None = None
    normalised: dict[str, Any] | None = None
    error: str | None = None

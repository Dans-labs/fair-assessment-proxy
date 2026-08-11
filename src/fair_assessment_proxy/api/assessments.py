import logging
from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel
import uuid
import asyncio
from urllib.parse import unquote
from fastapi import HTTPException
from sqlalchemy import select
from fair_assessment_proxy.models import (
    AssessmentRequest,
    RawAssessment,
    HarmonizedAssessment,
    Assessment,
)
from fair_assessment_proxy.db import AsyncSessionLocal
from fair_assessment_proxy.plugin_loader import load_assessor_plugins
from fair_assessment_proxy.plugins.base import AssessmentContext

PLUGINS = load_assessor_plugins()
ASSESSMENTS: dict[str, dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


logger = logging.getLogger(__name__)
router = APIRouter()


def normalize_pid(pid: str) -> str:
    pid = unquote(pid).strip()

    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi.org/",
        "dx.doi.org/",
        "doi:",
    )

    lower = pid.lower()

    for prefix in prefixes:
        if lower.startswith(prefix):
            pid = pid[len(prefix) :]
            break

    return pid.strip()


class AssessmentCreated(BaseModel):
    id: str
    status: str


async def store_assessment_result(
    *,
    assessment_id: str,
    pid: str,
    mode: str,
    assessor_id: str,
    raw: dict,
    normalised: dict,
):
    async with AsyncSessionLocal() as db:
        raw_record = RawAssessment(
            assessment_id=assessment_id,
            doi=pid,
            mode=mode,
            assessor=assessor_id,
            raw=raw,
        )

        harmonized_record = HarmonizedAssessment(
            assessment_id=assessment_id,
            doi=pid,
            mode=mode,
            assessor=assessor_id,
            f=normalised["f"],
            f1=normalised["f1"],
            f2=normalised["f2"],
            f3=normalised["f3"],
            f4=normalised["f4"],
            a=normalised["a"],
            a1=normalised["a"],
            a1_1=normalised["a1_1"],
            a1_2=normalised["a1_2"],
            a2=normalised["a2"],
            i=normalised["i"],
            i1=normalised["i1"],
            i2=normalised["i2"],
            i3=normalised["i3"],
            r=normalised["r"],
            r1=normalised["r1"],
            r1_1=normalised["r1_1"],
            r1_2=normalised["r1_2"],
            r1_3=normalised["r1_3"],
        )

        db.add(raw_record)
        db.add(harmonized_record)

        await db.commit()


async def get_assessment_result(
    *,
    pid: str,
    mode: str,
    assessor_id: str,
) -> dict | None:
    async with AsyncSessionLocal() as db:
        raw_stmt = (
            select(RawAssessment)
            .where(
                RawAssessment.doi == pid,
                RawAssessment.mode == mode,
                RawAssessment.assessor == assessor_id,
            )
            .order_by(RawAssessment.timestamp.desc())
            .limit(1)
        )

        raw_result = await db.execute(raw_stmt)
        raw_record = raw_result.scalar_one_or_none()

        if raw_record is None:
            return None

        harmonized_stmt = (
            select(HarmonizedAssessment)
            .where(
                HarmonizedAssessment.assessment_id == raw_record.assessment_id,
                HarmonizedAssessment.assessor == assessor_id,
            )
            .limit(1)
        )

        harmonized_result = await db.execute(harmonized_stmt)
        h = harmonized_result.scalar_one_or_none()

        if h is None:
            return None

        return {
            "raw": raw_record.raw,
            "normalised": {
                "assessor": assessor_id,
                "f": h.f,
                "f1": h.f1,
                "f2": h.f2,
                "f3": h.f3,
                "f4": h.f4,
                "a": h.a,
                "a1": h.a1,
                "a1_1": h.a1_1,
                "a1_2": h.a1_2,
                "a2": h.a2,
                "i": h.i,
                "i1": h.i1,
                "i2": h.i2,
                "i3": h.i3,
                "r": h.r,
                "r1": h.r1,
                "r1_1": h.r1_1,
                "r1_2": h.r1_2,
                "r1_3": h.r1_3,
            },
        }


async def run_assessment(assessment_id: str):
    async with AsyncSessionLocal() as db:
        assessment = await db.get(
            Assessment,
            assessment_id,
        )

        if assessment is None:
            return

        pid = assessment.pid
        mode = assessment.mode
        assessors = assessment.assessors
        use_cache = assessment.cached

        assessment.status = "running"
        await db.commit()

    context = AssessmentContext(
        pid=pid,
        mode=mode,
    )

    async def run_assessor(assessor_id: str):
        try:
            if use_cache:
                stored_result = await get_assessment_result(
                    pid=pid,
                    mode=mode,
                    assessor_id=assessor_id,
                )

                if stored_result is not None:
                    return {
                        "assessor": assessor_id,
                        "status": "completed",
                        "cached": True,
                    }

            result = await PLUGINS[assessor_id].assess(context)
            result_data = result.model_dump()

            await store_assessment_result(
                assessment_id=assessment_id,
                pid=pid,
                mode=mode,
                assessor_id=assessor_id,
                raw=result_data["raw"],
                normalised=result_data["normalised"],
            )

            return {
                "assessor": assessor_id,
                "status": result_data["status"],
                "cached": False,
            }

        except Exception as exc:
            return {
                "assessor": assessor_id,
                "status": "failed",
                "cached": False,
                "error": str(exc),
            }

    results = await asyncio.gather(
        *[run_assessor(assessor_id) for assessor_id in assessors]
    )

    has_failure = any(result["status"] == "failed" for result in results)

    final_status = "completed_with_errors" if has_failure else "completed"

    async with AsyncSessionLocal() as db:
        assessment = await db.get(
            Assessment,
            assessment_id,
        )

        assessment.status = final_status
        assessment.completed_at = datetime.now(timezone.utc)

        await db.commit()


async def create_assessment_record(
    assessment_id: str,
    pid: str,
    mode: str,
    assessors: list[str] | None = None,
    cached: bool = False,
):
    async with AsyncSessionLocal() as db:
        db.add(
            Assessment(
                id=assessment_id,
                pid=pid,
                mode=mode,
                assessors=assessors or list(PLUGINS.keys()),
                cached=cached,
                status="queued",
            )
        )

        await db.commit()


async def update_assessment_status(
    assessment_id: str,
    status: str,
    completed_at=None,
):
    async with AsyncSessionLocal() as db:
        assessment = await db.get(
            Assessment,
            assessment_id,
        )

        if assessment is None:
            return

        assessment.status = status

        if completed_at is not None:
            assessment.completed_at = completed_at

        await db.commit()


@router.post("/", response_model=AssessmentCreated, tags=["Assessments"])
async def create_assessment(req: AssessmentRequest):
    selected = req.assessors or list(PLUGINS.keys())

    unknown = [assessor_id for assessor_id in selected if assessor_id not in PLUGINS]

    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown assessor(s): {unknown}",
        )

    assessment_id = str(uuid.uuid4())

    await create_assessment_record(
        assessment_id=assessment_id,
        pid=normalize_pid(req.pid),
        mode=req.mode,
        assessors=selected,
        cached=req.cached,
    )

    asyncio.create_task(run_assessment(assessment_id))

    return AssessmentCreated(
        id=assessment_id,
        status="queued",
    )


@router.get("/latest", tags=["Assessments"])
async def get_latest_assessment(pid: str):
    pid = normalize_pid(pid)
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Assessment)
            .where(Assessment.pid == pid)
            .order_by(Assessment.created_at.desc())
            .limit(1)
        )

        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()

        if assessment is None:
            raise HTTPException(
                status_code=404,
                detail="No assessment found for PID",
            )

        harmonized_stmt = (
            select(HarmonizedAssessment)
            .where(HarmonizedAssessment.assessment_id == assessment.id)
            .order_by(HarmonizedAssessment.assessor)
        )

        result = await db.execute(harmonized_stmt)
        rows = result.scalars().all()

        return {
            "id": assessment.id,
            "pid": assessment.pid,
            "mode": assessment.mode,
            "assessors": assessment.assessors,
            "status": assessment.status,
            "created_at": assessment.created_at,
            "completed_at": assessment.completed_at,
            "results": [
                {
                    "assessor": row.assessor,
                    "f": row.f,
                    "f1": row.f1,
                    "f2": row.f2,
                    "f3": row.f3,
                    "f4": row.f4,
                    "a": row.a,
                    "a1": row.a1,
                    "a1_1": row.a1_1,
                    "a1_2": row.a1_2,
                    "a2": row.a2,
                    "i": row.i,
                    "i1": row.i1,
                    "i2": row.i2,
                    "i3": row.i3,
                    "r": row.r,
                    "r1": row.r1,
                    "r1_1": row.r1_1,
                    "r1_2": row.r1_2,
                    "r1_3": row.r1_3,
                }
                for row in rows
            ],
        }


@router.get("/{assessment_id}", tags=["Assessments"])
async def get_assessment_by_id(assessment_id: str):
    async with AsyncSessionLocal() as db:
        assessment = await db.get(
            Assessment,
            assessment_id,
        )

        if assessment is None:
            raise HTTPException(
                status_code=404,
                detail="Assessment not found",
            )

        stmt = (
            select(HarmonizedAssessment)
            .where(HarmonizedAssessment.assessment_id == assessment_id)
            .order_by(HarmonizedAssessment.assessor)
        )

        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {
            "id": assessment.id,
            "pid": assessment.pid,
            "mode": assessment.mode,
            "assessors": assessment.assessors,
            "status": assessment.status,
            "created_at": assessment.created_at,
            "completed_at": assessment.completed_at,
            "results": [
                {
                    "assessor": row.assessor,
                    "f": row.f,
                    "f1": row.f1,
                    "f2": row.f2,
                    "f3": row.f3,
                    "f4": row.f4,
                    "a": row.a,
                    "a1": row.a1,
                    "a1_1": row.a1_1,
                    "a1_2": row.a1_2,
                    "a2": row.a2,
                    "i": row.i,
                    "i1": row.i1,
                    "i2": row.i2,
                    "i3": row.i3,
                    "r": row.r,
                    "r1": row.r1,
                    "r1_1": row.r1_1,
                    "r1_2": row.r1_2,
                    "r1_3": row.r1_3,
                }
                for row in rows
            ],
        }


@router.get("/{assessment_id}/raw", tags=["Assessments"])
async def get_raw_assessment(assessment_id: str):
    async with AsyncSessionLocal() as db:
        assessment = await db.get(
            Assessment,
            assessment_id,
        )

        if assessment is None:
            raise HTTPException(
                status_code=404,
                detail="Assessment not found",
            )

        stmt = (
            select(RawAssessment)
            .where(RawAssessment.assessment_id == assessment_id)
            .order_by(RawAssessment.assessor)
        )

        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {
            "id": assessment.id,
            "pid": assessment.pid,
            "mode": assessment.mode,
            "status": assessment.status,
            "created_at": assessment.created_at,
            "completed_at": assessment.completed_at,
            "results": [
                {
                    "assessor": row.assessor,
                    "timestamp": row.timestamp,
                    "raw": row.raw,
                }
                for row in rows
            ],
        }


@router.get("/", tags=["Assessments"])
async def get_assessments(
    pid: str,
    assessor: str | None = None,
    mode: str | None = None,
):
    pid = normalize_pid(pid)
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Assessment)
            .where(Assessment.pid == pid)
            .order_by(Assessment.created_at.desc())
        )

        if mode is not None:
            stmt = stmt.where(Assessment.mode == mode)

        result = await db.execute(stmt)
        assessments = result.scalars().all()

        if assessor is not None:
            assessments = [a for a in assessments if assessor in a.assessors]

        return [
            {
                "id": assessment.id,
                "pid": assessment.pid,
                "mode": assessment.mode,
                "assessors": assessment.assessors,
                "status": assessment.status,
                "created_at": assessment.created_at,
                "completed_at": assessment.completed_at,
            }
            for assessment in assessments
        ]

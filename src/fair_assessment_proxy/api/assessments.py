import logging
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel
import uuid
import asyncio
from fastapi import FastAPI, HTTPException
from fair_assessment_proxy.config import get_app_version
from fair_assessment_proxy.security import validate_token, TOKEN_PORTAL
from fair_assessment_proxy.models import AssessmentRequest
from fair_assessment_proxy.plugin_loader import load_assessor_plugins
from fair_assessment_proxy.plugins.base import AssessmentContext

PLUGINS = load_assessor_plugins()
ASSESSMENTS: dict[str, dict[str, Any]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


logger = logging.getLogger(__name__)
router = APIRouter()


async def get_assessments():
    return {
        "status": "ok",
    }


class AssessmentCreated(BaseModel):
    id: str
    status: str


async def run_assessment(assessment_id: str):
    assessment = ASSESSMENTS[assessment_id]
    assessment["status"] = "running"

    context = AssessmentContext(
        pid=assessment["pid"],
        mode=assessment["mode"],
    )

    async def run_assessor(assessor_id: str):
        if assessment["cached"]:
            cached_result = await get_cached_result(
                pid=assessment["pid"],
                mode=assessment["mode"],
                assessor_id=assessor_id,
            )

            if cached_result is not None:
                return {
                    **cached_result,
                    "cached": True,
                }

        result = await PLUGINS[assessor_id].assess(context)

        result_data = result.model_dump()

        await store_cached_result(
            pid=assessment["pid"],
            mode=assessment["mode"],
            assessor_id=assessor_id,
            result=result_data,
        )

        return {
            **result_data,
            "cached": False,
        }

    results = await asyncio.gather(
        *[run_assessor(assessor_id) for assessor_id in assessment["assessors"]],
        return_exceptions=True,
    )

    stored_results = []
    has_failure = False

    for result in results:
        if isinstance(result, Exception):
            has_failure = True
            stored_results.append(
                {
                    "status": "failed",
                    "cached": False,
                    "error": str(result),
                }
            )
        else:
            stored_results.append(result)

            if result["status"] == "failed":
                has_failure = True

    assessment["results"] = stored_results
    assessment["completed_at"] = now_iso()
    assessment["status"] = "completed_with_errors" if has_failure else "completed"


# async def run_assessment(assessment_id: str):
#     assessment = ASSESSMENTS[assessment_id]
#
#     assessment["status"] = "running"
#
#     context = AssessmentContext(
#         pid=assessment["pid"],
#         mode=assessment["mode"],
#     )
#
#     results = await asyncio.gather(
#         *[
#             PLUGINS[assessor_id].assess(context)
#             for assessor_id in assessment["assessors"]
#         ],
#         return_exceptions=True,
#     )
#
#     has_failure = False
#     stored_results = []
#
#     for result in results:
#         if isinstance(result, Exception):
#             has_failure = True
#             stored_results.append(
#                 {
#                     "status": "failed",
#                     "error": str(result),
#                 }
#             )
#         else:
#             stored_results.append(result.model_dump())
#
#             if result.status == "failed":
#                 has_failure = True
#
#     assessment["results"] = stored_results
#     assessment["completed_at"] = now_iso()
#     assessment["status"] = "completed_with_errors" if has_failure else "completed"


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

    ASSESSMENTS[assessment_id] = {
        "id": assessment_id,
        "pid": req.pid,
        "mode": req.mode,
        "assessors": selected,
        "cached": req.cached,
        "status": "queued",
        "created_at": now_iso(),
        "completed_at": None,
        "results": [],
    }

    asyncio.create_task(run_assessment(assessment_id))

    return AssessmentCreated(
        id=assessment_id,
        status=ASSESSMENTS[assessment_id]["status"],
    )


@router.get("/{assessment_id}", tags=["Assessments"])
async def get_assessment(assessment_id: str):
    assessment = ASSESSMENTS.get(assessment_id)

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return assessment


@router.get("/{assessment_id}/results/{assessor_id}", tags=["Assessments"])
async def get_assessor_result(assessment_id: str, assessor_id: str):
    assessment = ASSESSMENTS.get(assessment_id)

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    for result in assessment["results"]:
        if result["assessor_id"] == assessor_id:
            return result

    raise HTTPException(
        status_code=404,
        detail=f"No result for assessor: {assessor_id}",
    )

import logging
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse
from fair_assessment_proxy.config import get_app_version
from fair_assessment_proxy.security import validate_token, TOKEN_PORTAL

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", tags=["Assessors"])
async def get_assessors():
    return {
        "status": "ok",
    }

import logging
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse
from fair_assessment_proxy.config import get_app_version
from fair_assessment_proxy.security import validate_token, TOKEN_PORTAL
from fair_assessment_proxy.plugin_loader import load_assessor_plugins

logger = logging.getLogger(__name__)
router = APIRouter()

PLUGINS = load_assessor_plugins()


@router.get("/", tags=["Assessors"])
async def list_assessors():
    return [
        {
            "id": assessor_id,
            "name": plugin.name,
        }
        for assessor_id, plugin in PLUGINS.items()
    ]

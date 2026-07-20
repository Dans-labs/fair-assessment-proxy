import logging

from fair_assessment_proxy.api import root, assessments, profiles, assessors
from fair_assessment_proxy.config import (
    load_service_config,
    init_logging,
    get_app_version,
    load_db_config,
)
import fair_assessment_proxy.security as security
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from typing import Any
from fair_assessment_proxy.models import AssessmentRequest
from fair_assessment_proxy.plugin_loader import load_assessor_plugins
from fair_assessment_proxy.plugins.base import AssessmentContext

init_logging()
logger = logging.getLogger(__name__)
service_config = load_service_config()
API_PREFIX = service_config.api_prefix
VERSION = get_app_version()
logger.info("Starting FAIR assessment proxy")
security.init_nonce_db()
ADMIN_TOKEN = security.generate_admin_token(service_config.admin_auth_key)
logger.info(f"Admin token: {ADMIN_TOKEN}")
PLUGINS = load_assessor_plugins()
ASSESSMENTS: dict[str, dict[str, Any]] = {}


app = FastAPI(
    # title=project_details["title"],
    # description=project_details["description"],
    # version=f"{project_details['version']} (Build Date: {build_date})",
)

app.include_router(root.router, prefix=API_PREFIX)
app.include_router(
    assessments.router, tags=["Assessments"], prefix=f"{API_PREFIX}/assessments"
)
app.include_router(profiles.router, tags=["Profiles"], prefix=f"{API_PREFIX}/profiles")
app.include_router(
    assessors.router, tags=["Assessors"], prefix=f"{API_PREFIX}/assessors"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

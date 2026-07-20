import os
from typing import Any

import httpx

from fair_assessment_proxy.models import AssessmentMode, AssessorResult
from fair_assessment_proxy.plugins.base import AssessmentContext, AssessorPlugin


class FujiAssessor(AssessorPlugin):
    async def assess(self, context: AssessmentContext) -> AssessorResult:
        try:
            raw = await self._run_fuji(context)

            return AssessorResult(
                assessor_id=self.assessor_id,
                name=self.name,
                status="completed",
                raw=raw,
                normalised=self._normalise(raw),
            )

        except Exception as exc:
            return AssessorResult(
                assessor_id=self.assessor_id,
                name=self.name,
                status="failed",
                error=str(exc),
            )

    async def _run_fuji(self, context: AssessmentContext) -> dict[str, Any]:
        base_url = self.config["base_url"].rstrip("/")
        url = f"{base_url}/evaluate"

        payload: dict[str, Any] = {
            "object_identifier": context.pid,
            "test_debug": True,
            "use_datacite": True,
            "use_github": False,
            "use_headless": False,
        }

        if context.mode == AssessmentMode.cached:
            cached = self.config.get("cached_mode", {})

            payload.update(
                {
                    "metadata_service_endpoint": cached.get(
                        "metadata_service_endpoint"
                    ),
                    "metadata_service_type": cached.get(
                        "metadata_service_type",
                        "oai_pmh",
                    ),
                    "use_datacite": False,
                }
            )

        username = os.getenv(self.config.get("username_env", "FUJI_USERNAME"))
        password = os.getenv(self.config.get("password_env", "FUJI_PASSWORD"))

        if not username or not password:
            raise RuntimeError("Missing FUJI basic-auth credentials")

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(username, password),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"F-UJI returned HTTP {response.status_code}: {response.text[:1000]}"
            )

        return response.json()

    def _normalise(self, raw: dict[str, Any]) -> dict[str, Any]:
        summary = raw.get("summary", {})

        score_earned = summary.get("score_earned", {})
        score_total = summary.get("score_total", {})
        score_percent = summary.get("score_percent", {})
        maturity = summary.get("maturity", {})

        return {
            "assessor": "fuji",
            "overall": {
                "score_earned": score_earned.get("FAIR"),
                "score_total": score_total.get("FAIR"),
                "score_percent": score_percent.get("FAIR"),
                "maturity": maturity.get("FAIR"),
            },
            "principles": {
                principle: {
                    "score_earned": score_earned.get(principle),
                    "score_total": score_total.get(principle),
                    "score_percent": score_percent.get(principle),
                    "maturity": maturity.get(principle),
                }
                for principle in ["F", "A", "I", "R"]
            },
        }

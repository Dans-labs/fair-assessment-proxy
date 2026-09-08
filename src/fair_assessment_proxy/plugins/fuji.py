import os
import re
from typing import Any

import httpx

from fair_assessment_proxy.models import AssessmentMode, AssessorResult
from fair_assessment_proxy.plugins.base import AssessmentContext, AssessorPlugin
from fair_assessment_proxy.models import NormalizedAssessorResult, FairOutcome


METRIC_PATTERN = re.compile(r"^FsF-([FAIR]\d(?:\.\d)?)-")


def cell_for(metric_identifier):
    match = METRIC_PATTERN.match(metric_identifier or "")
    return match.group(1).lower().replace(".", "_") if match else None


def outcome_of(result):
    status = str(result.get("test_status", "")).strip().lower()

    if status not in {"pass", "partial", "fail"}:
        return "indeterminate"
    if status == "fail":
        return "fail"

    score = result.get("score") or {}

    try:
        earned = float(score["earned"])
        total = float(score["total"])
    except (KeyError, TypeError, ValueError):
        return "partial" if status == "partial" else "pass"

    if total <= 0:
        return "indeterminate"
    if earned <= 0:
        return "fail"
    return "pass" if earned >= total else "partial"


def guidance_for(raw):
    entries = []

    for result in raw.get("results") or []:
        outcome = outcome_of(result)
        reasons = []

        if outcome in {"fail", "partial"}:
            reasons.extend(
                str(test.get("metric_test_name") or "Failed metric test")
                for test in (result.get("metric_tests") or {}).values()
                if test.get("metric_test_status") == "fail"
            )
            reasons.extend(
                str(message).split(": ", maxsplit=1)[-1]
                for message in result.get("test_debug") or []
                if str(message).startswith(("WARNING:", "ERROR:", "FAILURE:"))
            )

            if not reasons:
                score = result.get("score") or {}
                earned = score.get("earned")
                total = score.get("total")
                reasons.append(
                    f"Earned {earned} of {total} points"
                    if earned is not None and total is not None
                    else f"Metric reported {outcome}"
                )

        entries.append(
            {
                "assessor": "fuji",
                "cell": cell_for(result.get("metric_identifier") or ""),
                "test": result.get("metric_identifier"),
                "description": result.get("metric_name"),
                "outcome": outcome,
                "message": "; ".join(dict.fromkeys(reasons)) or None,
                "guidance": None,
            }
        )

    return entries


class FujiAssessor(AssessorPlugin):
    async def assess(self, context: AssessmentContext) -> AssessorResult:
        try:
            raw = await self._run_fuji(context)

            return AssessorResult(
                assessor_id=self.assessor_id,
                version=raw.get("software_version"),
                name=self.name,
                status="completed",
                raw=raw,
                normalised=self.normalize(raw, context),
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

        # username = os.getenv(self.config.get("username_env", "FUJI_USERNAME"))
        # password = os.getenv(self.config.get("password_env", "FUJI_PASSWORD"))
        username = os.getenv("FUJI_USERNAME")
        password = os.getenv("FUJI_PASSWORD")

        if not username or not password:
            raise RuntimeError("Missing FUJI basic-auth credentials")

        # print(f"[DEBUG] username: {username}, password: {'*' * len(password)}")

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

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
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

    def normalize(
        self, raw: dict[str, Any], context: AssessmentContext
    ) -> NormalizedAssessorResult:
        score_percent = raw.get("summary", {}).get("score_percent", {})

        def outcome_from_percent(value: float | int | None) -> FairOutcome:
            if value is None:
                return FairOutcome.indeterminate
            if value == 100:
                return FairOutcome.pass_
            if value == 0:
                return FairOutcome.fail
            return FairOutcome.partial

        def out(key: str) -> FairOutcome:
            return outcome_from_percent(score_percent.get(key))

        return NormalizedAssessorResult(
            assessor="fuji",
            profile="fuji",
            status="completed",
            overall=out("FAIR"),
            f=out("F"),
            a=out("A"),
            i=out("I"),
            r=out("R"),
            f1=out("F1"),
            f2=out("F2"),
            f3=out("F3"),
            f4=out("F4"),
            a1=out("A1"),
            a1_1=out("A1.1"),
            a1_2=out("A1.2"),
            a2=out("A2"),
            i1=out("I1"),
            i2=out("I2"),
            i3=out("I3"),
            r1=out("R1"),
            r1_1=out("R1.1"),
            r1_2=out("R1.2"),
            r1_3=out("R1.3"),
            extra={
                "source": "fuji",
                "metric_version": raw.get("metric_version"),
                "software_version": raw.get("software_version"),
                "resolved_url": raw.get("resolved_url"),
            },
        )

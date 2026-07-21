from typing import Any

import httpx


from fair_assessment_proxy.models import AssessmentMode, AssessorResult
from fair_assessment_proxy.models import NormalizedAssessorResult, FairOutcome
from fair_assessment_proxy.plugins.base import AssessmentContext, AssessorPlugin


def pid_to_doi(pid: str) -> str:
    return (
        pid.strip()
        .replace("https://doi.org/", "")
        .replace("http://doi.org/", "")
        .replace("doi:", "")
    )


class FairChampionAssessor(AssessorPlugin):
    async def assess(self, context: AssessmentContext) -> AssessorResult:
        try:
            raw = await self._run_champion_tests(context)

            return AssessorResult(
                assessor_id=self.assessor_id,
                name=self.name,
                status="completed",
                raw=raw,
                normalised=self._normalize(raw),
            )

        except Exception as exc:
            return AssessorResult(
                assessor_id=self.assessor_id,
                name=self.name,
                status="failed",
                error=str(exc),
            )

    async def _run_champion_tests(
        self,
        context: AssessmentContext,
    ) -> dict[str, Any]:
        champion_base_url = self.config["champion_base_url"].rstrip("/")
        fair_core_tests_base_url = self.config["fair_core_tests_base_url"].rstrip("/")

        proxy_url = f"{champion_base_url}/test-execution-proxy"

        resource_identifier = self._resource_identifier(context)
        test_ids = self.config.get("tests", [])

        results = []

        async with httpx.AsyncClient(timeout=180.0) as client:
            for test_id in test_ids:
                test_endpoint = f"{fair_core_tests_base_url}/assess/test/{test_id}"

                response = await client.post(
                    proxy_url,
                    data={
                        "endpoint": test_endpoint,
                        "resource_identifier": resource_identifier,
                    },
                    headers={
                        "Accept": "application/ld+json",
                    },
                )

                if response.status_code >= 400:
                    results.append(
                        {
                            "test_id": test_id,
                            "status": "failed",
                            "error": response.text[:1000],
                        }
                    )
                    continue

                try:
                    body = response.json()
                except Exception:
                    body = {
                        "content_type": response.headers.get("content-type"),
                        "body": response.text,
                    }

                results.append(
                    {
                        "test_id": test_id,
                        "status": "completed",
                        "raw": body,
                    }
                )

        return {
            "resource_identifier": resource_identifier,
            "tests": results,
        }

    def _resource_identifier(self, context: AssessmentContext) -> str:
        if context.mode == AssessmentMode.public:
            return context.pid

        doi = pid_to_doi(context.pid)
        gateway = self.config["metadata_gateway_base_url"].rstrip("/")

        return f"{gateway}/resource/doi/{doi}"

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        tests = raw.get("tests", [])

        total = len(tests)
        completed = len([t for t in tests if t.get("status") == "completed"])
        failed_to_run = len([t for t in tests if t.get("status") == "failed"])

        test_summaries = []

        for test in tests:
            outcome = self._extract_outcome(test)

            test_summaries.append(
                {
                    "test_id": test.get("test_id"),
                    "status": test.get("status"),
                    "outcome": outcome,
                }
            )

        passed = len([t for t in test_summaries if t["outcome"] == "pass"])
        failed = len([t for t in test_summaries if t["outcome"] == "fail"])
        indeterminate = len(
            [t for t in test_summaries if t["outcome"] == "indeterminate"]
        )

        return {
            "assessor": "fair_champion",
            "resource_identifier": raw.get("resource_identifier"),
            "overall": {
                "tests_total": total,
                "tests_completed": completed,
                "tests_failed_to_run": failed_to_run,
                "tests_passed": passed,
                "tests_failed": failed,
                "tests_indeterminate": indeterminate,
                "pass_percent": round((passed / total) * 100, 2) if total else None,
            },
            "tests": test_summaries,
        }

    def _extract_outcome(self, test: dict[str, Any]) -> str:
        if test.get("status") != "completed":
            return "indeterminate"

        raw = test.get("raw")
        text = str(raw).lower()

        if "pass" in text or "passed" in text:
            return "pass"

        if "fail" in text or "failed" in text:
            return "fail"

        return "indeterminate"

    def normalize(
        self, raw: dict[str, Any], context: AssessmentContext
    ) -> NormalizedAssessorResult:
        raise NotImplementedError

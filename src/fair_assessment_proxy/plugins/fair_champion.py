from __future__ import annotations
import httpx
from collections import defaultdict
from typing import Any, Iterable
from fair_assessment_proxy.models import AssessmentMode, AssessorResult
from fair_assessment_proxy.models import NormalizedAssessorResult, FairOutcome
from fair_assessment_proxy.plugins.base import AssessmentContext, AssessorPlugin

TEST_TO_PRINCIPLE = {
    # Findable
    "test_FM_F1_M_IdentUnique": "f1",
    "fc_structured_metadata": "f2",
    "test_FM_F3_M_MetaIdent": "f3",
    "fc_searchable": "f4",
    # Accessible
    "test_FM_A1_1_M_OpenProt": "a1_1",
    "test_FM_A1_2_M_Auth": "a1_2",
    "test_FM_A2_M_MetaLong": "a2",
    # Interoperable
    "test_FM_I1_M_FormalLangSyntax": "i1",
    "fc_metadata_uses_fair_vocabularies": "i2",
    "test_FM_I3_M_QualRef": "i3",
    # Reusable
    "test_FM_R1_1_M_StdLic": "r1_1",
}

TEST_TO_PRINCIPLE_FULL = {
    # Findable
    "fc_unique_identifier": "f1",
    "test_FM_F1_M_IdentUnique": "f1",
    "test_FM_F1_M_IdentPersistent": "f1",
    "fc_metadata_identifier_persistence": "f1",
    "fc_structured_metadata": "f2",
    "fc_grounded_metadata": "f2",
    "fc_metadata_identifier_in_metadata": "f3",
    "fc_data_identifier_in_metadata": "f3",
    "test_FM_F3_M_MetaIdent": "f3",
    "test_FM_F3_M_DataIdent": "f3",
    "fc_searchable": "f4",
    "fc_harvest_only": "f4",
    "test_FM_F4_M_MetaIndexed": "f4",
    # Accessible
    "fc_metadata_protocol": "a1_1",
    "fc_data_protocol": "a1_1",
    "test_FM_A1_1_M_OpenProt": "a1_1",
    "test_FM_A1_1_M_OpenProt_Data": "a1_1",
    "fc_metadata_authorization": "a1_2",
    "fc_data_authorization": "a1_2",
    "test_FM_A1_2_M_Auth": "a1_2",
    "test_FM_A1_2_M_DataAuth": "a1_2",
    "fc_metadata_persistence": "a2",
    "test_FM_A2_M_MetaLong": "a2",
    # Interoperable
    "fc_metadata_kr_language_strong": "i1",
    "fc_metadata_kr_language_weak": "i1",
    "fc_data_kr_language_strong": "i1",
    "fc_data_kr_language_weak": "i1",
    "test_FM_I1_M_FormLangSemantic_Data": "i1",
    "test_FM_I1_M_FormalLangSyntax": "i1",
    "fc_metadata_uses_fair_vocabularies": "i2",
    "fc_metadata_outward_links": "i3",
    "test_FM_I3_M_QualRef": "i3",
    # Reusable
    "fc_metadata_includes_license": "r1_1",
    "fc_metadata_includes_license_weak": "r1_1",
    "test_FM_R1_1_M_StdLic": "r1_1",
    "test_FM_R1_1_M_StdLic_strong": "r1_1",
}


def combine_outcomes(
    outcomes: Iterable[FairOutcome | None],
) -> FairOutcome | None:
    """
    Aggregate several test outcomes into one FAIR-principle outcome.

    Rules:
    - no applicable outcomes -> None
    - all pass -> pass
    - all error -> error
    - any fail -> fail
    - mixed pass/fail-free outcomes -> partial
    - otherwise indeterminate
    """
    values = [outcome for outcome in outcomes if outcome is not None]

    if not values:
        return None

    if all(outcome == FairOutcome.pass_ for outcome in values):
        return FairOutcome.pass_

    if all(outcome == FairOutcome.error for outcome in values):
        return FairOutcome.error

    if all(outcome == FairOutcome.not_applicable for outcome in values):
        return FairOutcome.not_applicable

    if any(outcome == FairOutcome.fail for outcome in values):
        return FairOutcome.fail

    if any(outcome == FairOutcome.partial for outcome in values):
        return FairOutcome.partial

    if FairOutcome.pass_ in values:
        # For example: pass + error, or pass + indeterminate.
        return FairOutcome.partial

    if any(outcome == FairOutcome.error for outcome in values):
        return FairOutcome.error

    return FairOutcome.indeterminate


def extract_test_outcome(test: dict[str, Any]) -> FairOutcome:
    """
    Extract a categorical result from one FAIR Champion test.

    An execution failure is returned as `error`, not `fail`.
    """
    execution_status = str(test.get("status", "")).lower()

    if execution_status in {"failed", "error", "timeout"}:
        return FairOutcome.error

    if execution_status not in {"completed", "success", "succeeded"}:
        return FairOutcome.indeterminate

    result = test.get("raw") or test.get("result")

    if result is None:
        return FairOutcome.indeterminate

    outcome = _find_outcome(result)

    return outcome or FairOutcome.indeterminate


def _find_outcome(value: Any) -> FairOutcome | None:
    """
    Recursively find a recognised FAIR test outcome in JSON/JSON-LD.

    This handles common fields such as:
      outcome
      status
      result
      testResult
      assertion
    """
    if isinstance(value, dict):
        preferred_keys = (
            "outcome",
            "testOutcome",
            "test_outcome",
            "testResult",
            "test_result",
            "assertion",
            "result",
            "status",
        )

        for key in preferred_keys:
            if key in value:
                outcome = _parse_outcome_value(value[key])
                if outcome is not None:
                    return outcome

        for nested_value in value.values():
            outcome = _find_outcome(nested_value)
            if outcome is not None:
                return outcome

    elif isinstance(value, list):
        for item in value:
            outcome = _find_outcome(item)
            if outcome is not None:
                return outcome

    return _parse_outcome_value(value)


def _parse_outcome_value(value: Any) -> FairOutcome | None:
    if isinstance(value, bool):
        return FairOutcome.pass_ if value else FairOutcome.fail

    if not isinstance(value, str):
        return None

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")

    # JSON-LD values may be complete URIs.
    normalized = normalized.rsplit("/", maxsplit=1)[-1]
    normalized = normalized.rsplit("#", maxsplit=1)[-1]

    aliases: dict[str, FairOutcome] = {
        "pass": FairOutcome.pass_,
        "passed": FairOutcome.pass_,
        "success": FairOutcome.pass_,
        "succeeded": FairOutcome.pass_,
        "compliant": FairOutcome.pass_,
        "true": FairOutcome.pass_,
        "partial": FairOutcome.partial,
        "partially_passed": FairOutcome.partial,
        "partially_compliant": FairOutcome.partial,
        "fail": FairOutcome.fail,
        "failed": FairOutcome.fail,
        "failure": FairOutcome.fail,
        "non_compliant": FairOutcome.fail,
        "false": FairOutcome.fail,
        "indeterminate": FairOutcome.indeterminate,
        "unknown": FairOutcome.indeterminate,
        "inconclusive": FairOutcome.indeterminate,
        "undetermined": FairOutcome.indeterminate,
        "error": FairOutcome.error,
        "errored": FairOutcome.error,
        "timeout": FairOutcome.error,
        "not_applicable": FairOutcome.not_applicable,
        "notapplicable": FairOutcome.not_applicable,
        "skipped": FairOutcome.not_applicable,
    }

    return aliases.get(normalized)


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
                normalised=self.normalize(raw, context),
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
        # test_ids = self.config.get("tests", [])
        test_ids = list(TEST_TO_PRINCIPLE.keys())

        results = []

        async with httpx.AsyncClient(timeout=180.0) as client:
            for test_id in test_ids:
                print(
                    f"Running FAIR Champion test: {test_id} for resource: {resource_identifier}"
                )
                test_endpoint = f"{fair_core_tests_base_url}/assess/test/{test_id}"
                print(f"Test endpoint: {test_endpoint}")

                # response = await client.post(
                #     proxy_url,
                #     data={
                #         "endpoint": test_endpoint,
                #         "resource_identifier": resource_identifier,
                #     },
                #     headers={
                #         "Accept": "application/ld+json",
                #     },
                # )
                response = await client.post(
                    test_endpoint,
                    data={
                        "resource_identifier": resource_identifier,
                    },
                    headers={
                        "Accept": "application/ld+json",
                    },
                )
                print(f"Response status code: {response.status_code}")
                # print(
                #     response.json()
                #     if response.headers.get("content-type") == "application/json"
                #     else response.text
                # )
                # break

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
                    print(
                        f"Failed to parse JSON response for test {test_id}. Falling back to raw text"
                    )
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
        self,
        raw: dict[str, Any],
        context: AssessmentContext,
    ) -> NormalizedAssessorResult:
        tests = raw.get("tests", [])

        outcomes_by_principle: dict[str, list[FairOutcome]] = defaultdict(list)
        unmapped_tests: list[str] = []

        for test in tests:
            test_id = test.get("test_id")
            outcome = extract_test_outcome(test)

            principle = TEST_TO_PRINCIPLE.get(test_id)

            if principle is None:
                if test_id:
                    unmapped_tests.append(test_id)
                continue

            outcomes_by_principle[principle].append(outcome)

        def outcome(principle: str) -> FairOutcome | None:
            return combine_outcomes(outcomes_by_principle.get(principle, []))

        # Subprinciples
        f1 = outcome("f1")
        f2 = outcome("f2")
        f3 = outcome("f3")
        f4 = outcome("f4")

        a1_1 = outcome("a1_1")
        a1_2 = outcome("a1_2")
        a2 = outcome("a2")

        i1 = outcome("i1")
        i2 = outcome("i2")
        i3 = outcome("i3")

        r1_1 = outcome("r1_1")
        r1_2 = outcome("r1_2")
        r1_3 = outcome("r1_3")

        # Parent principles derived from their children.
        a1 = combine_outcomes([a1_1, a1_2])
        r1 = combine_outcomes([r1_1, r1_2, r1_3])

        f = combine_outcomes([f1, f2, f3, f4])
        a = combine_outcomes([a1, a2])
        i = combine_outcomes([i1, i2, i3])
        r = combine_outcomes([r1])

        overall = combine_outcomes([f, a, i, r])

        execution_errors = sum(
            1 for test in tests if extract_test_outcome(test) == FairOutcome.error
        )

        status = "completed_with_errors" if execution_errors else "completed"

        return NormalizedAssessorResult(
            assessor=self.assessor_id,
            profile=self.config.get("profile", "fair-champion"),
            status=status,
            overall=overall,
            f=f,
            a=a,
            i=i,
            r=r,
            f1=f1,
            f2=f2,
            f3=f3,
            f4=f4,
            a1=a1,
            a1_1=a1_1,
            a1_2=a1_2,
            a2=a2,
            i1=i1,
            i2=i2,
            i3=i3,
            r1=r1,
            r1_1=r1_1,
            r1_2=r1_2,
            r1_3=r1_3,
            extra={
                "resource_identifier": raw.get("resource_identifier"),
                "tests_total": len(tests),
                "execution_errors": execution_errors,
                "unmapped_tests": unmapped_tests,
            },
        )

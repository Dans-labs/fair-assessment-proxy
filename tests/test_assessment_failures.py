from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fair_assessment_proxy.api import assessments
from fair_assessment_proxy.models import AssessorResult, RawAssessment


class ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, assessment):
        self.assessment = assessment
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_):
        return self.assessment

    async def commit(self):
        return None

    def add(self, row):
        self.added.append(row)

    async def execute(self, _):
        return ScalarResult(
            [row for row in self.added if isinstance(row, RawAssessment)]
        )


class FailedAssessor:
    async def assess(self, _context):
        return AssessorResult(
            assessor_id="fuji",
            name="F-UJI",
            status="failed",
            error="F-UJI returned HTTP 503",
        )


class RaisingAssessor:
    async def assess(self, _context):
        raise TimeoutError("F-UJI timed out")


class EmptyErrorAssessor:
    async def assess(self, _context):
        return AssessorResult(
            assessor_id="fuji",
            name="F-UJI",
            status="failed",
            error="",
        )


class AssessmentFailureTest(IsolatedAsyncioTestCase):
    async def run_with(self, plugin):
        assessment = SimpleNamespace(
            id="assessment-id",
            pid="10.1234/example",
            mode="public",
            assessors=["fuji"],
            cached=False,
            status="queued",
            created_at=None,
            completed_at=None,
        )
        session = FakeSession(assessment)

        with (
            patch.object(assessments, "AsyncSessionLocal", return_value=session),
            patch.object(assessments, "PLUGINS", {"fuji": plugin}),
        ):
            await assessments.run_assessment(assessment.id)
            return await assessments.get_raw_assessment(assessment.id)

    async def test_failed_assessor_error_is_available_from_raw_endpoint(self):
        response = await self.run_with(FailedAssessor())

        self.assertEqual("completed_with_errors", response["status"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual(
            {
                "status": "failed",
                "error": "F-UJI returned HTTP 503",
            },
            response["results"][0]["raw"],
        )

    async def test_raised_assessor_error_is_available_from_raw_endpoint(self):
        response = await self.run_with(RaisingAssessor())

        self.assertEqual("completed_with_errors", response["status"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual(
            {
                "status": "failed",
                "error": "F-UJI timed out",
            },
            response["results"][0]["raw"],
        )

    async def test_empty_assessor_error_is_preserved(self):
        response = await self.run_with(EmptyErrorAssessor())

        self.assertEqual("", response["results"][0]["raw"]["error"])

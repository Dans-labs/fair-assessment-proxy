from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fair_assessment_proxy.api import assessments
from fair_assessment_proxy.models import HarmonizedAssessment, RawAssessment
from fair_assessment_proxy.reporting import CELLS


class ScalarResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class FakeSession:
    def __init__(self, assessment, query_rows):
        self.assessment = assessment
        self.query_rows = iter(query_rows)
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_):
        return self.assessment

    async def execute(self, _):
        return ScalarResult(next(self.query_rows))

    async def commit(self):
        return None

    def add(self, row):
        self.added.append(row)


class UnexpectedAssessorCall:
    async def assess(self, _context):
        raise AssertionError("a cache hit must not call the assessor")


class AssessmentCacheTest(IsolatedAsyncioTestCase):
    async def test_cache_hit_materializes_results_for_new_assessment(self):
        assessment = SimpleNamespace(
            id="new-assessment",
            pid="10.1234/example",
            mode="public",
            assessors=["fuji"],
            cached=True,
            status="queued",
            completed_at=None,
        )
        cached_raw = SimpleNamespace(
            assessment_id="cached-assessment",
            raw={"source": "cached F-UJI response"},
        )
        cached_cells = dict.fromkeys(CELLS, "pass")
        cached_cells.update({"a": "partial", "a1": "fail"})
        cached_result = SimpleNamespace(
            assessor_version="3.5.1",
            f="pass",
            i="pass",
            r="pass",
            **cached_cells,
        )
        session = FakeSession(assessment, [cached_raw, cached_result])

        with (
            patch.object(assessments, "AsyncSessionLocal", return_value=session),
            patch.object(
                assessments,
                "PLUGINS",
                {"fuji": UnexpectedAssessorCall()},
            ),
        ):
            await assessments.run_assessment(assessment.id)

        raw_rows = [row for row in session.added if isinstance(row, RawAssessment)]
        result_rows = [
            row for row in session.added if isinstance(row, HarmonizedAssessment)
        ]

        self.assertEqual(1, len(raw_rows))
        self.assertEqual("new-assessment", raw_rows[0].assessment_id)
        self.assertEqual({"source": "cached F-UJI response"}, raw_rows[0].raw)
        self.assertEqual(1, len(result_rows))
        self.assertEqual("new-assessment", result_rows[0].assessment_id)
        self.assertEqual("3.5.1", result_rows[0].assessor_version)
        self.assertEqual("partial", result_rows[0].a)
        self.assertEqual("fail", result_rows[0].a1)
        self.assertEqual("completed", assessment.status)

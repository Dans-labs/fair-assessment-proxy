from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fastapi import HTTPException

from fair_assessment_proxy.api import assessments
from fair_assessment_proxy.reporting import CELLS


class ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, assessment, query_rows):
        self.assessment = assessment
        self.query_rows = iter(query_rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_):
        return self.assessment

    async def execute(self, _):
        return ScalarResult(next(self.query_rows))


class ResultEndpointTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.assessment = SimpleNamespace(
            id="id",
            pid="10/example",
            status="completed",
        )
        self.row = SimpleNamespace(
            assessor="fuji",
            assessor_version="3.5.1",
            **dict.fromkeys(CELLS, "pass"),
        )

    async def test_results_returns_toolkit_grid(self):
        session = FakeSession(self.assessment, [[self.row]])

        with patch.object(assessments, "AsyncSessionLocal", return_value=session):
            response = await assessments.get_results("id")

        self.assertEqual("fuji", response["results"][0]["assessor"])
        self.assertEqual(100.0, response["results"][0]["scores"]["overall"])

    async def test_single_assessor_result_includes_raw_response(self):
        raw_row = SimpleNamespace(raw={"source": "fuji"})
        session = FakeSession(self.assessment, [[self.row], [raw_row]])

        with patch.object(assessments, "AsyncSessionLocal", return_value=session):
            response = await assessments.get_result_for_assessor("id", "fuji")

        self.assertEqual({"source": "fuji"}, response["raw"])

    async def test_report_contains_cells_scores_and_guidance(self):
        raw_row = SimpleNamespace(
            assessor="fuji",
            raw={
                "results": [
                    {
                        "metric_identifier": "FsF-R1.1-01M",
                        "metric_name": "License information",
                        "test_status": "fail",
                        "score": {"earned": 0, "total": 1},
                        "metric_tests": {},
                        "test_debug": ["WARNING: No licence found"],
                    }
                ]
            },
        )
        session = FakeSession(self.assessment, [[self.row], [raw_row]])

        with patch.object(assessments, "AsyncSessionLocal", return_value=session):
            response = await assessments.get_report("id")

        self.assertEqual(15, len(response["cells"]))
        self.assertEqual(100.0, response["scores"]["fuji"]["overall"])
        self.assertEqual("fuji", response["guidance"][0]["assessor"])

    async def test_missing_assessment_is_404(self):
        session = FakeSession(None, [])

        with patch.object(assessments, "AsyncSessionLocal", return_value=session):
            with self.assertRaises(HTTPException) as raised:
                await assessments.get_results("missing")

        self.assertEqual(404, raised.exception.status_code)

    async def test_missing_assessor_result_is_404(self):
        session = FakeSession(self.assessment, [[]])

        with patch.object(assessments, "AsyncSessionLocal", return_value=session):
            with self.assertRaises(HTTPException) as raised:
                await assessments.get_result_for_assessor("id", "missing")

        self.assertEqual(404, raised.exception.status_code)

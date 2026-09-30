import logging
from unittest import TestCase

from fair_offline_assessor.models import MetricResult, Score

from fair_assessment_proxy.config import init_logging
from fair_assessment_proxy.offline import assess_metadata, cells_from_metrics
from fair_assessment_proxy.reporting import CELLS

SOIL_DATASET = {
    "@context": "https://schema.org/",
    "@type": "Dataset",
    "name": "Unpublished soil measurements",
    "description": "Soil moisture observations awaiting publication.",
    "creator": {"name": "Ada Example"},
    "publisher": {"name": "DANS"},
    "dateCreated": "2026-09-01",
    "keywords": ["soil", "moisture"],
    "license": "https://creativecommons.org/licenses/by/4.0/",
}


def metric(identifier, principle, earned=None, maximum=1.0, complete=True):
    score = (
        None
        if earned is None
        else Score(observed_earned=earned, maximum=maximum, complete=complete)
    )
    outcome = (
        "indeterminate"
        if score is None or not complete
        else "pass"
        if earned
        else "fail"
    )
    return MetricResult(
        id=identifier, principles=(principle,), outcome=outcome, score=score
    )


class CellsFromMetricsTest(TestCase):
    def test_combines_the_points_of_decided_metrics_per_principle(self):
        cells = cells_from_metrics(
            [
                metric("FsF-F1-01MD", "F1", earned=1.0),
                metric("FsF-F1-02MD", "F1", earned=0.0),
                metric("FsF-I3-01M", "I3", earned=2.0, maximum=2.0),
                metric("FsF-R1.1-01M", "R1.1", earned=0.0),
            ]
        )

        self.assertEqual("partial", cells["f1"])
        self.assertEqual("pass", cells["i3"])
        self.assertEqual("fail", cells["r1_1"])

    def test_undecided_metrics_leave_their_cell_indeterminate(self):
        cells = cells_from_metrics(
            [
                metric("FsF-F4-01M", "F4"),
                metric("FsF-A1.1-01MD", "A1.1", earned=0.0, complete=False),
                metric("FsF-R1.3-01M", "R1.3", earned=1.0),
                metric("FsF-R1.3-02D", "R1.3", earned=0.0, complete=False),
            ]
        )

        self.assertEqual("indeterminate", cells["f4"])
        self.assertEqual("indeterminate", cells["a1_1"])
        self.assertEqual("pass", cells["r1_3"])
        self.assertEqual("indeterminate", cells["a2"])
        self.assertEqual(set(CELLS), set(cells))


class AssessMetadataTest(TestCase):
    def test_returns_the_common_result_for_the_fuji_profile(self):
        result = assess_metadata(SOIL_DATASET)

        self.assertEqual(
            {
                "assessor",
                "status",
                "assessor_version",
                "profile_ref",
                "error",
                "cells",
                "scores",
                "scored",
                "derived",
                "unmapped",
                "guidance",
                "raw",
            },
            set(result),
        )
        self.assertEqual("offline", result["assessor"])
        self.assertEqual("completed", result["status"])
        self.assertEqual("3.5.1", result["assessor_version"])
        self.assertEqual("fusji-offline@3.5.1", result["profile_ref"])
        self.assertEqual("fusji-offline", result["raw"]["profile"]["id"])

    def test_cells_follow_fuji_metrics_and_proxy_derivation(self):
        cells = assess_metadata(SOIL_DATASET)["cells"]

        self.assertEqual("pass", cells["r1_1"])
        self.assertEqual("fail", cells["f3"])
        self.assertEqual("indeterminate", cells["f4"])
        self.assertEqual("indeterminate", cells["a1"])

    def test_guidance_describes_each_fuji_metric(self):
        result = assess_metadata(SOIL_DATASET)
        guidance = {entry["test"]: entry for entry in result["guidance"]}

        self.assertEqual(
            [metric["id"] for metric in result["raw"]["metrics"]], list(guidance)
        )
        licence = guidance["FsF-R1.1-01M"]
        self.assertEqual("offline", licence["assessor"])
        self.assertEqual("r1_1", licence["cell"])
        self.assertEqual("pass", licence["outcome"])
        self.assertIsNone(licence["message"])
        self.assertTrue(licence["description"])
        indexed = guidance["FsF-F4-01M"]
        self.assertEqual("indeterminate", indexed["outcome"])
        self.assertIn("unavailable to the offline evaluator", indexed["message"])

    def test_unwraps_a_datacite_json_api_envelope(self):
        result = assess_metadata(
            {
                "data": {
                    "id": "10.1234/example",
                    "type": "dois",
                    "attributes": {
                        "doi": "10.1234/example",
                        "titles": [{"title": "Example dataset"}],
                        "creators": [{"name": "Ada Example"}],
                        "publisher": "DANS",
                        "publicationYear": 2026,
                        "rightsList": [
                            {
                                "rightsUri": "https://creativecommons.org/licenses/by/4.0/"
                            }
                        ],
                    },
                }
            }
        )

        self.assertEqual([], result["raw"]["diagnostics"])
        self.assertEqual("pass", result["cells"]["r1_1"])

    def test_proxy_logging_omits_assessment_findings(self):
        init_logging()
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger().addHandler(handler)
        try:
            assess_metadata(SOIL_DATASET)
        finally:
            logging.getLogger().removeHandler(handler)

        self.assertEqual(
            [],
            [record for record in records if record.name.startswith("fair_offline")],
        )

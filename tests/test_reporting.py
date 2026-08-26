from types import SimpleNamespace
from unittest import TestCase

from fair_assessment_proxy.reporting import CELLS, combine, serialize_result


class ReportingTest(TestCase):
    def test_serializes_cells_and_excludes_parent_cells_from_scores(self):
        values = dict.fromkeys(CELLS, "pass")
        values["f2"] = "partial"
        values["r1_3"] = "not_applicable"
        row = SimpleNamespace(
            assessor="fair_champion",
            assessor_version="0.5.8",
            **values,
        )

        result = serialize_result(row)

        self.assertEqual("unmeasured", result["cells"]["r1_3"])
        self.assertEqual(87.5, result["scores"]["f"])
        self.assertEqual(2, result["scored"]["r"])
        self.assertEqual(["a1", "r1"], result["derived"])

    def test_combines_measured_outcomes(self):
        self.assertEqual("pass", combine(["pass", "unmeasured"]))
        self.assertEqual("fail", combine(["pass", "fail"]))
        self.assertEqual("partial", combine(["pass", "partial"]))
        self.assertEqual("unmeasured", combine(["unmeasured"]))

    def test_derives_parent_cells_instead_of_trusting_legacy_columns(self):
        values = dict.fromkeys(CELLS, "unmeasured")
        values.update(
            {
                "a1": "fail",
                "a1_1": "pass",
                "a1_2": "pass",
                "a2": "fail",
                "r1": "pass",
                "r1_1": "pass",
                "r1_2": "partial",
            }
        )
        row = SimpleNamespace(
            assessor="fair_champion",
            assessor_version="0.5.8",
            **values,
        )

        result = serialize_result(row)

        self.assertEqual("pass", result["cells"]["a1"])
        self.assertEqual("partial", result["cells"]["r1"])

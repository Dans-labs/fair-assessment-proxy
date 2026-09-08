from unittest import TestCase

from fair_assessment_proxy.models import AssessmentMode
from fair_assessment_proxy.plugins.base import AssessmentContext
from fair_assessment_proxy.plugins.fair_champion import (
    FairChampionAssessor,
    guidance_for,
)


class ChampionGuidanceTest(TestCase):
    def setUp(self):
        self.algorithm_result = {
            "tests": [
                {
                    "reference": "DiscoverableInBing",
                    "testid": "https://example.org/test_FM_F4_M_MetaIndexed",
                }
            ],
            "conditions": [
                {
                    "description": "Metadata can be found through a search engine",
                    "guidance": "Publish machine-readable metadata on the landing page",
                }
            ],
            "test_results": {"DiscoverableInBing": {"result": "fail"}},
            "narratives": ["The metadata record was not found"],
            "guidances": [
                [
                    "Expose the record through OAI-PMH",
                    None,
                ]
            ],
        }

    def test_extracts_algorithm_guidance(self):
        self.assertEqual(
            [
                {
                    "assessor": "fair_champion",
                    "cell": "f4",
                    "test": "DiscoverableInBing",
                    "description": "Metadata can be found through a search engine",
                    "outcome": "fail",
                    "message": "The metadata record was not found",
                    "guidance": ["Expose the record through OAI-PMH"],
                }
            ],
            guidance_for(self.algorithm_result),
        )

    def test_guidance_is_always_a_list_of_strings(self):
        for value, expected in (
            ("Publish metadata", ["Publish metadata"]),
            (["Publish metadata", None, "", 42], ["Publish metadata"]),
            (None, []),
        ):
            with self.subTest(value=value):
                self.algorithm_result["guidances"] = [value]
                entry = guidance_for(self.algorithm_result)[0]
                self.assertEqual(expected, entry["guidance"])

    def test_missing_or_unknown_outcome_is_indeterminate(self):
        for value, expected in (
            (None, "indeterminate"),
            ("unknown", "indeterminate"),
            ("error", "error"),
            ("not_applicable", "not_applicable"),
            ("unavailable", "unavailable"),
        ):
            with self.subTest(value=value):
                self.algorithm_result["test_results"] = {
                    "DiscoverableInBing": {"result": value}
                }
                self.algorithm_result["conditions"] = [{}]
                self.algorithm_result["narratives"] = []
                entry = guidance_for(self.algorithm_result)[0]
                self.assertEqual(expected, entry["outcome"])
                self.assertIsNone(entry["description"])
                self.assertIsNone(entry["message"])

    def test_non_text_details_are_null(self):
        self.algorithm_result["conditions"] = [
            {"description": {"text": "Metadata"}}
        ]
        self.algorithm_result["narratives"] = [42]

        entry = guidance_for(self.algorithm_result)[0]

        self.assertIsNone(entry["description"])
        self.assertIsNone(entry["message"])

    def test_normalizes_algorithm_results(self):
        assessor = FairChampionAssessor(
            "fair_champion",
            {"profile": "ostrails-core"},
        )

        result = assessor.normalize(
            self.algorithm_result,
            AssessmentContext(pid="10.1234/example", mode=AssessmentMode.public),
        )

        self.assertEqual("fail", result.f4)
        self.assertEqual("not_applicable", result.f1)
        self.assertEqual([], result.extra["unmapped_tests"])

    def test_extracts_failed_test_reason_from_jsonld(self):
        raw = {
            "tests": [
                {
                    "test_id": "fc_searchable",
                    "status": "completed",
                    "raw": {
                        "@graph": [
                            {
                                "@type": "ftr:TestResult",
                                "prov:value": {"@value": "fail"},
                                "ftr:log": {
                                    "@value": "FAILURE: Metadata was not indexed"
                                },
                                "dct:description": {
                                    "@value": "Checks metadata discoverability"
                                },
                            }
                        ]
                    },
                }
            ]
        }

        self.assertEqual(
            [
                {
                    "assessor": "fair_champion",
                    "cell": "f4",
                    "test": "fc_searchable",
                    "description": "Checks metadata discoverability",
                    "outcome": "fail",
                    "message": "FAILURE: Metadata was not indexed",
                    "guidance": [],
                }
            ],
            guidance_for(raw),
        )

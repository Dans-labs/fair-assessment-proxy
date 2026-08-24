from unittest import TestCase

from fair_assessment_proxy.plugins.fair_champion import guidance_for


class ChampionGuidanceTest(TestCase):
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
                    "guidance": None,
                }
            ],
            guidance_for(raw),
        )

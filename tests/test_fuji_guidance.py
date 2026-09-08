from unittest import TestCase

from fair_assessment_proxy.plugins.fuji import guidance_for


class FujiGuidanceTest(TestCase):
    def test_extracts_failed_metric_tests_and_debug_messages(self):
        raw = {
            "results": [
                {
                    "metric_identifier": "FsF-R1.1-01M",
                    "metric_name": "License information",
                    "test_status": "fail",
                    "score": {"earned": 0, "total": 1},
                    "metric_tests": {
                        "0": {
                            "metric_test_status": "fail",
                            "metric_test_name": "No license found",
                        }
                    },
                    "test_debug": [
                        "WARNING: Metadata has no recognised licence"
                    ],
                }
            ]
        }

        entry = guidance_for(raw)[0]

        self.assertEqual("fuji", entry["assessor"])
        self.assertEqual("r1_1", entry["cell"])
        self.assertEqual("fail", entry["outcome"])
        self.assertEqual("License information", entry["description"])
        self.assertEqual([], entry["guidance"])
        self.assertIn("No license found", entry["message"])
        self.assertIn("Metadata has no recognised licence", entry["message"])

from copy import deepcopy
from unittest import TestCase

try:
    from fair_assessment_proxy.offline import assess_metadata
except ModuleNotFoundError:
    assess_metadata = None


class OfflineAssessmentTest(TestCase):
    def test_licence_text_without_a_web_url_is_only_partial(self):
        for licence, expected in (
            ("banana", "partial"),
            ("MIT", "partial"),
            ("CC-BY-4.0", "partial"),
            ("https://creativecommons.org/licenses/by/4.0/", "pass"),
            ("https://[bad", "partial"),
            ("https://not a host/licence", "partial"),
            ("https://example.org:notaport/licence", "partial"),
            ("https://example.org:99999/licence", "partial"),
            (None, "fail"),
        ):
            with self.subTest(licence=licence):
                result = assess_metadata({"license": licence})
                self.assertEqual(expected, result["cells"]["r1_1"])

    def test_graph_dataset_inherits_context_without_overriding_its_own(self):
        for local_context, expected in (
            ({}, "pass"),
            ({"@context": None}, "partial"),
        ):
            with self.subTest(local_context=local_context):
                metadata = {
                    "@context": "https://schema.org/",
                    "@graph": [
                        {"@type": "Person", "name": "Ada Example"},
                        {
                            "@type": "Dataset",
                            "name": "Unpublished draft",
                            **local_context,
                        },
                    ],
                }
                original = deepcopy(metadata)

                result = assess_metadata(metadata)

                self.assertEqual(expected, result["cells"]["i1"])
                self.assertEqual(original, metadata)

    def test_assesses_locally_observable_jsonld_metadata(self):
        self.assertIsNotNone(assess_metadata, "offline assessor is not implemented")
        metadata = {
            "@context": "https://schema.org/",
            "@type": "Dataset",
            "@id": "https://doi.org/10.1234/example",
            "name": "Example dataset",
            "description": "Measurements collected for a FAIR assessment example.",
            "creator": [{"@type": "Person", "name": "Ada Example"}],
            "publisher": {"@type": "Organization", "name": "DANS"},
            "datePublished": "2026-08-24",
            "keywords": ["FAIR", "research data"],
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "citation": {"@id": "https://doi.org/10.1234/related"},
            "conformsTo": {
                "@id": "https://schema.datacite.org/meta/kernel-4.5/"
            },
        }
        original = deepcopy(metadata)

        result = assess_metadata(metadata)

        self.assertEqual("offline", result["assessor"])
        self.assertEqual("completed", result["status"])
        self.assertEqual("pass", result["cells"]["f1"])
        self.assertEqual("pass", result["cells"]["f2"])
        self.assertEqual("pass", result["cells"]["f3"])
        self.assertEqual("unmeasured", result["cells"]["f4"])
        self.assertEqual("unmeasured", result["cells"]["a1"])
        self.assertEqual("unmeasured", result["cells"]["a1_1"])
        self.assertEqual("unmeasured", result["cells"]["a1_2"])
        self.assertEqual("unmeasured", result["cells"]["a2"])
        self.assertEqual("pass", result["cells"]["i1"])
        self.assertEqual("unmeasured", result["cells"]["i2"])
        self.assertEqual("pass", result["cells"]["i3"])
        self.assertEqual("pass", result["cells"]["r1"])
        self.assertEqual("pass", result["cells"]["r1_1"])
        self.assertEqual("pass", result["cells"]["r1_2"])
        self.assertEqual("pass", result["cells"]["r1_3"])
        self.assertEqual(8, result["scored"]["overall"])
        self.assertEqual(15, len(result["guidance"]))
        self.assertEqual(original, metadata)

    def test_missing_fields_fail_only_checks_that_metadata_can_answer(self):
        self.assertIsNotNone(assess_metadata, "offline assessor is not implemented")

        result = assess_metadata({"title": "Unpublished draft"})

        self.assertEqual("fail", result["cells"]["f1"])
        self.assertEqual("fail", result["cells"]["f2"])
        self.assertEqual("fail", result["cells"]["f3"])
        self.assertEqual("unmeasured", result["cells"]["f4"])
        self.assertEqual("partial", result["cells"]["i1"])
        self.assertEqual("unmeasured", result["cells"]["i2"])
        self.assertEqual("fail", result["cells"]["i3"])
        self.assertEqual("fail", result["cells"]["r1"])
        self.assertIsNone(result["scores"]["a"])

    def test_understands_a_datacite_json_api_envelope(self):
        self.assertIsNotNone(assess_metadata, "offline assessor is not implemented")
        metadata = {
            "data": {
                "id": "10.1234/example",
                "type": "dois",
                "attributes": {
                    "doi": "10.1234/example",
                    "titles": [{"title": "Example dataset"}],
                    "descriptions": [
                        {
                            "description": "A complete DataCite metadata example.",
                            "descriptionType": "Abstract",
                        }
                    ],
                    "creators": [{"name": "Ada Example"}],
                    "publisher": "DANS",
                    "publicationYear": 2026,
                    "subjects": [{"subject": "FAIR"}],
                    "rightsList": [
                        {
                            "rights": "Creative Commons Attribution 4.0",
                            "rightsUri": "https://creativecommons.org/licenses/by/4.0/",
                        }
                    ],
                    "relatedIdentifiers": [
                        {
                            "relatedIdentifier": "10.1234/related",
                            "relatedIdentifierType": "DOI",
                            "relationType": "References",
                        }
                    ],
                    "schemaVersion": "http://datacite.org/schema/kernel-4",
                },
            }
        }

        result = assess_metadata(metadata)

        self.assertEqual("pass", result["cells"]["f1"])
        self.assertEqual("pass", result["cells"]["f2"])
        self.assertEqual("pass", result["cells"]["i1"])
        self.assertEqual("pass", result["cells"]["i3"])
        self.assertEqual("pass", result["cells"]["r1_1"])
        self.assertEqual("pass", result["cells"]["r1_3"])

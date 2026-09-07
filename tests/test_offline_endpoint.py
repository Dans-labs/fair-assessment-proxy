from unittest import IsolatedAsyncioTestCase

import httpx
from fastapi import FastAPI

from fair_assessment_proxy.api import assessments


class OfflineEndpointTest(IsolatedAsyncioTestCase):
    async def test_malformed_identifier_does_not_prevent_assessment(self):
        app = FastAPI()
        app.include_router(assessments.router, prefix="/assessments")

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/assessments/offline",
                json={"metadata": {"identifier": "https://[bad"}},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("completed", response.json()["status"])
        self.assertEqual("partial", response.json()["cells"]["f1"])

    async def test_assesses_unpublished_metadata_without_a_pid(self):
        app = FastAPI()
        app.include_router(assessments.router, prefix="/assessments")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/assessments/offline",
                json={
                    "metadata": {
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
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("completed", body["status"])
        self.assertEqual("fail", body["cells"]["f1"])
        self.assertEqual("fail", body["cells"]["f3"])
        self.assertEqual("pass", body["cells"]["f2"])
        self.assertEqual("pass", body["cells"]["r1_1"])
        for cell in ("f4", "a1_1", "a1_2", "a2", "i2"):
            self.assertEqual("unmeasured", body["cells"][cell])
        self.assertIsNone(body["scores"]["a"])
        identifier_guidance = next(
            entry for entry in body["guidance"] if entry["cell"] == "f1"
        )
        self.assertTrue(identifier_guidance["message"])

    async def test_returns_an_immediate_assessment_for_supplied_metadata(self):
        app = FastAPI()
        app.include_router(assessments.router, prefix="/assessments")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/assessments/offline",
                json={
                    "metadata": {
                        "@context": "https://schema.org/",
                        "@type": "Dataset",
                        "@id": "https://doi.org/10.1234/example",
                        "name": "Example dataset",
                        "description": "An offline FAIR assessment example.",
                        "creator": {"name": "Ada Example"},
                        "publisher": {"name": "DANS"},
                        "datePublished": "2026-08-24",
                        "keywords": ["FAIR"],
                        "license": "https://creativecommons.org/licenses/by/4.0/",
                        "citation": "https://doi.org/10.1234/related",
                        "conformsTo": "https://schema.org/Dataset",
                    }
                },
            )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("offline", body["assessor"])
        self.assertEqual("completed", body["status"])
        self.assertEqual("pass", body["cells"]["f1"])
        self.assertEqual(15, len(body["guidance"]))

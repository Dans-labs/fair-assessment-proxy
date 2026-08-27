from unittest import IsolatedAsyncioTestCase

import httpx
from fastapi import FastAPI

from fair_assessment_proxy.api import assessments


class OfflineEndpointTest(IsolatedAsyncioTestCase):
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

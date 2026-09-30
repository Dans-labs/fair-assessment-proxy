import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

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
        self.assertEqual("fail", body["cells"]["f3"])
        self.assertEqual("pass", body["cells"]["r1_1"])
        for cell in ("f4", "a1_1", "a1_2", "a2"):
            self.assertEqual("indeterminate", body["cells"][cell])
        self.assertIsNone(body["scores"]["a"])
        identifier_guidance = next(
            entry for entry in body["guidance"] if entry["cell"] == "f3"
        )
        self.assertTrue(identifier_guidance["message"])
        for entry in body["guidance"]:
            self.assertIsInstance(entry["guidance"], list)
            self.assertTrue(all(isinstance(text, str) for text in entry["guidance"]))
            if entry["outcome"] in {"pass", "indeterminate"}:
                self.assertEqual([], entry["guidance"])

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
        self.assertEqual("fusji-offline@3.5.1", body["profile_ref"])
        self.assertEqual(17, len(body["guidance"]))

    async def test_assessment_does_not_block_other_requests(self):
        app = FastAPI()
        app.include_router(assessments.router, prefix="/assessments")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            assessment = asyncio.create_task(
                client.post(
                    "/assessments/offline",
                    json={"metadata": {"@type": "Dataset", "name": "Example"}},
                )
            )
            other_work = asyncio.create_task(asyncio.sleep(0.1))
            done, _ = await asyncio.wait(
                {assessment, other_work}, return_when=asyncio.FIRST_COMPLETED
            )
            await assessment

        self.assertEqual({other_work}, done)

    async def post(self, body):
        app = FastAPI()
        app.include_router(assessments.router, prefix="/assessments")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post("/assessments/", json=body)

    async def test_returns_offline_results_with_the_assessment_request(self):
        metadata = {"@type": "Dataset", "name": "Example"}

        response = await self.post({"assessors": ["offline"], "metadata": metadata})
        missing = await self.post({"assessors": ["offline"]})
        empty = await self.post({})

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertIsNone(body["id"])
        self.assertEqual("completed", body["status"])
        self.assertEqual("offline", body["offline"]["assessor"])
        self.assertEqual(400, missing.status_code)
        self.assertEqual(400, empty.status_code)

    async def test_queues_online_assessors_next_to_offline_results(self):
        with (
            patch.object(
                assessments, "create_assessment_record", AsyncMock()
            ) as record,
            patch.object(assessments, "run_assessment", AsyncMock()),
        ):
            response = await self.post(
                {"pid": "10.1234/example", "metadata": {"@type": "Dataset"}}
            )

        body = response.json()
        self.assertEqual("queued", body["status"])
        self.assertEqual("offline", body["offline"]["assessor"])
        queued = record.call_args.kwargs["assessors"]
        self.assertTrue(queued)
        self.assertNotIn("offline", queued)

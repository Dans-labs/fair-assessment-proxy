import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from fair_assessment_proxy.api import assessments


class OfflineEndpointTest(IsolatedAsyncioTestCase):
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

    async def test_assessment_does_not_block_other_requests(self):
        assessment = asyncio.create_task(
            self.post({"assessors": ["offline"], "metadata": {"@type": "Dataset"}})
        )
        other_work = asyncio.create_task(asyncio.sleep(0.1))
        done, _ = await asyncio.wait(
            {assessment, other_work}, return_when=asyncio.FIRST_COMPLETED
        )
        await assessment

        self.assertEqual({other_work}, done)

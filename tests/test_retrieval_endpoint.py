import asyncio
from functools import partial
from unittest import IsolatedAsyncioTestCase

import httpx
from fastapi import FastAPI

from fair_assessment_proxy.api import retrieval
from fair_assessment_proxy.retrieval import RateLimiter, resolve, retrieve


async def public(host, port):
    return ["93.184.215.14"]


def serving(response):
    return httpx.MockTransport(lambda request: response)


def new_limits(requests=10, slots=4):
    return retrieval.Limits(
        RateLimiter(limit=requests, period=60), asyncio.Semaphore(slots)
    )


class RetrievalEndpointTest(IsolatedAsyncioTestCase):
    def app(self, response, limits=None, resolver=public):
        app = FastAPI()
        app.include_router(retrieval.router, prefix="/retrieve")
        app.dependency_overrides[retrieval.get_retriever] = lambda: partial(
            retrieve, resolver=resolver, transport=serving(response)
        )
        limits = limits or new_limits()
        app.dependency_overrides[retrieval.get_limits] = lambda: limits
        return app

    async def get(self, app, url="https://example.org/dataset"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/retrieve", params={"url": url})

    async def test_returns_the_retrieved_document(self):
        app = self.app(
            httpx.Response(
                200,
                headers={"Content-Type": "application/ld+json"},
                json={"@type": "Dataset"},
            )
        )

        response = await self.get(app)

        self.assertEqual(200, response.status_code)
        self.assertEqual({"@type": "Dataset"}, response.json())
        self.assertEqual("application/ld+json", response.headers["Content-Type"])
        self.assertEqual(
            "https://example.org/dataset", response.headers["Content-Location"]
        )
        self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])

    async def test_reports_rejected_and_failed_retrievals(self):
        for url, resolver, response, status in (
            ("http://10.0.0.1/", resolve, httpx.Response(200), 400),
            ("https://example.org/", public, httpx.Response(404), 502),
        ):
            with self.subTest(status=status):
                app = self.app(response, resolver=resolver)

                self.assertEqual(status, (await self.get(app, url)).status_code)

    async def test_limits_requests_per_client(self):
        app = self.app(
            httpx.Response(200, headers={"Content-Type": "application/json"}, json={}),
            new_limits(requests=1),
        )

        self.assertEqual(200, (await self.get(app)).status_code)
        response = await self.get(app)

        self.assertEqual(429, response.status_code)
        self.assertEqual("60", response.headers["Retry-After"])

    async def test_limits_concurrent_retrievals(self):
        app = self.app(httpx.Response(200), new_limits(slots=0))

        response = await self.get(app)

        self.assertEqual(429, response.status_code)
        self.assertEqual("1", response.headers["Retry-After"])

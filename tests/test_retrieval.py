import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx

from fair_assessment_proxy.retrieval import (
    MAX_BYTES,
    RateLimiter,
    RejectedURL,
    RetrievalFailed,
    retrieve,
)

PUBLIC = "93.184.215.14"
DOCUMENT = {"@context": "https://schema.org/", "@type": "Dataset", "name": "Soil"}


def resolver(addresses):
    async def resolve(host, port):
        return addresses.get(host, [PUBLIC])

    return resolve


def responding(handler):
    requests = []

    def record(request):
        requests.append(request)
        return handler(request)

    return httpx.MockTransport(record), requests


def jsonld(request):
    return httpx.Response(
        200,
        headers={"Content-Type": "application/vnd.schemaorg.ld+json; charset=utf-8"},
        content=json.dumps(DOCUMENT).encode(),
    )


def responding_with(status, media_type, content):
    return lambda request: httpx.Response(
        status, headers={"Content-Type": media_type}, content=content
    )


def redirecting(times):
    redirects = []

    def handle(request):
        if len(redirects) == times:
            return jsonld(request)
        redirects.append(request)
        return httpx.Response(302, headers={"Location": "https://example.org/"})

    return handle


class RetrieveTest(IsolatedAsyncioTestCase):
    async def fetch(self, url, handler=jsonld, addresses=None):
        transport, requests = responding(handler)
        document = await retrieve(
            url, resolver=resolver(addresses or {}), transport=transport
        )
        return document, requests

    async def test_retrieves_json_from_the_checked_address(self):
        document, requests = await self.fetch("https://example.org/dataset")

        self.assertEqual(DOCUMENT, json.loads(document.content))
        self.assertEqual("application/vnd.schemaorg.ld+json", document.media_type)
        self.assertEqual("https://example.org/dataset", document.url)
        request = requests[0]
        self.assertEqual(PUBLIC, request.url.host)
        self.assertEqual("example.org", request.headers["Host"])
        self.assertEqual("example.org", request.extensions["sni_hostname"])
        self.assertIn("application/ld+json", request.headers["Accept"])

    async def test_rejects_urls_outside_public_http(self):
        for url in (
            "file:///etc/passwd",
            "ftp://example.org/dataset",
            "http://example.org:5432/",
            "https://example.org:8443/",
            "https://user:secret@example.org/",
            "http://",
            "not a url",
        ):
            with self.subTest(url=url), self.assertRaises(RejectedURL):
                await self.fetch(url)

    async def test_rejects_hosts_with_any_internal_address(self):
        for address in (
            "127.0.0.1",
            "0.0.0.0",
            "10.0.0.5",
            "172.18.0.3",
            "192.168.1.1",
            "169.254.169.254",
            "100.64.0.1",
            "224.0.0.1",
            "::1",
            "fd00::1",
            "fe80::1",
            "::ffff:127.0.0.1",
            "64:ff9b::a00:1",
            "2002:a00:1::1",
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",
        ):
            with self.subTest(address=address), self.assertRaises(RejectedURL):
                await self.fetch(
                    "http://postgres/", addresses={"postgres": [PUBLIC, address]}
                )

    async def test_checks_every_redirect(self):
        def redirect(request):
            if request.headers["Host"] == "doi.org":
                return httpx.Response(302, headers={"Location": "http://fuji:1071/"})
            return jsonld(request)

        with self.assertRaises(RejectedURL):
            await self.fetch(
                "https://doi.org/10.1234/x",
                handler=redirect,
                addresses={"fuji": ["172.18.0.4"]},
            )

    async def test_follows_redirects_to_public_hosts(self):
        def redirect(request):
            if request.headers["Host"] == "doi.org":
                return httpx.Response(
                    302, headers={"Location": "https://data.crosscite.org/10.1234%2Fx"}
                )
            return jsonld(request)

        document, requests = await self.fetch(
            "https://doi.org/10.1234/x", handler=redirect
        )

        self.assertEqual("https://data.crosscite.org/10.1234%2Fx", document.url)
        self.assertEqual("data.crosscite.org", requests[1].extensions["sni_hostname"])

    async def test_rejects_unusable_responses(self):
        for name, handler in (
            ("redirect loop", redirecting(times=20)),
            (
                "status",
                responding_with(404, "application/json", b"{}"),
            ),
            ("type", responding_with(200, "text/html", b'"<script>alert(1)</script>"')),
            (
                "size",
                responding_with(
                    200, "application/json", b'"' + b"a" * MAX_BYTES + b'"'
                ),
            ),
        ):
            with self.subTest(name), self.assertRaises(RetrievalFailed):
                await self.fetch("https://example.org/", handler=handler)


class RateLimiterTest(TestCase):
    def test_limits_each_client_within_the_period(self):
        now = [0.0]
        limiter = RateLimiter(limit=2, period=60, clock=lambda: now[0])

        self.assertIsNone(limiter.check("a"))
        self.assertIsNone(limiter.check("a"))
        self.assertEqual(60, limiter.check("a"))
        self.assertIsNone(limiter.check("b"))

        now[0] = 30.0
        self.assertEqual(30, limiter.check("a"))
        now[0] = 60.0
        self.assertIsNone(limiter.check("a"))
        self.assertEqual({"a"}, set(limiter.windows))

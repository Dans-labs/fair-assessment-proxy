import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

ACCEPT = "application/ld+json, application/json;q=0.9"
PORTS = {"http": 80, "https": 443}
MAX_BYTES = 5_000_000
MAX_REDIRECTS = 5
TIMEOUT = 10.0
NAT64 = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)

Resolver = Callable[[str, int], Awaitable[list[str]]]


class RejectedURL(ValueError):
    pass


class RetrievalFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Document:
    content: bytes
    media_type: str
    url: str


async def resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    # is_global counts NAT64 and multicast addresses as public.
    return (
        ip.is_global
        and not ip.is_multicast
        and not any(ip in network for network in NAT64)
    )


async def _checked_address(url: httpx.URL, resolver: Resolver) -> str:
    if url.scheme not in PORTS or not url.host:
        raise RejectedURL("Only http and https URLs can be retrieved.")
    if url.port not in (None, PORTS[url.scheme]):
        raise RejectedURL("Only the standard http and https ports are allowed.")
    if url.userinfo:
        raise RejectedURL("URLs with credentials are not allowed.")
    try:
        addresses = await resolver(url.host, PORTS[url.scheme])
    except OSError as exc:
        raise RetrievalFailed(f"Could not resolve {url.host}.") from exc
    if not all(_public(address) for address in addresses):
        raise RejectedURL(f"{url.host} does not resolve to a public address.")
    return addresses[0]


async def _document(response: httpx.Response, url: httpx.URL) -> Document:
    if not response.is_success:
        raise RetrievalFailed(f"The server responded with {response.status_code}.")
    media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise RetrievalFailed("The URL did not return JSON-LD or JSON.")
    content = bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise RetrievalFailed("The document is larger than 5 MB.")
    return Document(content=bytes(content), media_type=media_type, url=str(url))


async def _follow(
    client: httpx.AsyncClient, url: httpx.URL, resolver: Resolver
) -> Document:
    for _ in range(MAX_REDIRECTS + 1):
        address = await _checked_address(url, resolver)
        request = client.build_request(
            "GET",
            url.copy_with(host=address),
            headers={"Host": url.netloc.decode(), "Accept": ACCEPT},
            extensions={"sni_hostname": url.host},
        )
        response = await client.send(request, stream=True)
        try:
            if not response.is_redirect:
                return await _document(response, url)
            url = url.join(response.headers["Location"])
        finally:
            await response.aclose()
    raise RetrievalFailed("The URL redirected too many times.")


async def retrieve(
    url: str,
    *,
    resolver: Resolver = resolve,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Document:
    """Retrieve a JSON-LD or JSON document from a public web address."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise RejectedURL("The URL is not valid.") from exc
    async with httpx.AsyncClient(
        transport=transport, timeout=None, trust_env=False
    ) as client:
        try:
            async with asyncio.timeout(TIMEOUT):
                return await _follow(client, parsed, resolver)
        except TimeoutError as exc:
            raise RetrievalFailed("The server did not respond in time.") from exc
        except httpx.HTTPError as exc:
            raise RetrievalFailed("The document could not be retrieved.") from exc


class RateLimiter:
    def __init__(
        self, limit: int, period: float, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.period = period
        self.clock = clock
        self.windows: dict[str, tuple[float, int]] = {}

    def check(self, client: str) -> float | None:
        """Count a request, or return the seconds until the client may retry."""
        now = self.clock()
        self.windows = {
            key: window
            for key, window in self.windows.items()
            if window[0] > now - self.period
        }
        start, count = self.windows.get(client, (now, 0))
        if count >= self.limit:
            return start + self.period - now
        self.windows[client] = (start, count + 1)
        return None

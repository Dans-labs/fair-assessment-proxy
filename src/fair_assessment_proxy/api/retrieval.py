import asyncio
import math
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from fair_assessment_proxy.config import settings
from fair_assessment_proxy.retrieval import (
    RateLimiter,
    RejectedURL,
    RetrievalFailed,
    retrieve,
)

router = APIRouter()


@dataclass(frozen=True)
class Limits:
    requests: RateLimiter
    slots: asyncio.Semaphore


LIMITS = Limits(
    RateLimiter(limit=settings.retrieval.requests_per_minute, period=60),
    asyncio.Semaphore(settings.retrieval.max_concurrent),
)


def get_retriever():
    return retrieve


def get_limits():
    return LIMITS


@router.get("")
async def retrieve_document(
    url: str,
    request: Request,
    fetch=Depends(get_retriever),
    limits: Limits = Depends(get_limits),
):
    """Retrieve a public JSON-LD or JSON document for offline assessment."""
    client = request.client.host if request.client else "unknown"
    if (wait := limits.requests.check(client)) is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many retrievals; try again later.",
            headers={"Retry-After": str(math.ceil(wait))},
        )
    if limits.slots.locked():
        raise HTTPException(
            status_code=429,
            detail="The proxy is busy; try again shortly.",
            headers={"Retry-After": "1"},
        )
    async with limits.slots:
        try:
            document = await fetch(url)
        except RejectedURL as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RetrievalFailed as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        document.content,
        media_type=document.media_type,
        headers={"Content-Location": document.url, "X-Content-Type-Options": "nosniff"},
    )

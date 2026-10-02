"""Fixed-window rate limiting stored in `rate_limits` so limits hold across workers (D-07)."""

from __future__ import annotations

import math
import time
from datetime import datetime

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.documents import IST
from app.core.errors import TooManyRequests


def _bucket(key: str, window: int) -> tuple[str, float]:
    start = int(time.time() // window) * window
    return f"{key}:{start}", start + window


async def peek(db: AsyncDatabase, key: str, window: int) -> int:
    bucket, _ = _bucket(key, window)
    doc = await db.rate_limits.find_one({"_id": bucket})
    return int(doc["count"]) if doc else 0


async def hit(db: AsyncDatabase, key: str, window: int) -> int:
    bucket, end = _bucket(key, window)
    for _ in range(2):
        try:
            doc = await db.rate_limits.find_one_and_update(
                {"_id": bucket},
                {"$inc": {"count": 1}, "$setOnInsert": {"expiresAt": datetime.fromtimestamp(end, IST)}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return int(doc["count"])
        except DuplicateKeyError:
            continue
    return await peek(db, key, window)


def too_many(window: int) -> TooManyRequests:
    _, end = _bucket("x", window)
    minutes = max(1, math.ceil((end - time.time()) / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return TooManyRequests(f"Too many attempts. Please try again in {minutes} {unit}.")


async def enforce(db: AsyncDatabase, key: str, limit: int, window: int, *, count: bool = True) -> None:
    """Raise 429 if the bucket is already at `limit`; otherwise optionally count this attempt."""
    if await peek(db, key, window) >= limit:
        raise too_many(window)
    if count:
        await hit(db, key, window)

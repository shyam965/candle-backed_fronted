"""Document metadata helpers mirroring Mongoose conventions (FR-010, D-09, D-10)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    """Current UTC time truncated to milliseconds (BSON date precision)."""
    now = datetime.now(UTC)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def new_meta(now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    return {"createdAt": now, "updatedAt": now, "__v": 0}


def touch(update: dict[str, Any], *, bump_version: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Add `updatedAt` (and optionally `$inc __v`) to a MongoDB update document."""
    update = {k: dict(v) for k, v in update.items()}
    update.setdefault("$set", {})["updatedAt"] = now or utcnow()
    if bump_version:
        update.setdefault("$inc", {})["__v"] = 1
    return update


def num(value: float | int) -> int | float:
    """Store integral numbers as int and others as double, like the Node BSON serializer."""
    if isinstance(value, bool):
        raise TypeError("booleans are not numbers")
    if isinstance(value, int):
        return value
    if math.isfinite(value) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return float(value)

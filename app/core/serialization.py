"""JSON serialization of MongoDB documents (FR-011, D-11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.core.documents import IST


def iso_ms(value: datetime) -> str:
    """ISO-8601 in IST with milliseconds, e.g. `2026-10-02T14:45:27.481+05:30` (stored values stay UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(IST)
    return value.isoformat(timespec="milliseconds")


def to_json(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return iso_ms(value)
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]
    return value

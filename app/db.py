"""MongoDB connection lifecycle and index management (FR-008, FR-009, D-08)."""

from __future__ import annotations

import logging

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure, PyMongoError

from app.config import Settings
from app.core.documents import IST

log = logging.getLogger("akrf.db")

# Existing indexes (BE §4.8) + indexes for the two new collections (D-04, D-07).
INDEXES: list[tuple[str, list[tuple[str, int]], dict]] = [
    ("users", [("email", ASCENDING)], {"unique": True}),
    ("categories", [("name", ASCENDING)], {"unique": True}),
    ("carts", [("user", ASCENDING)], {"unique": True}),
    ("orders", [("orderId", ASCENDING)], {"unique": True}),
    ("orders", [("user", ASCENDING)], {}),
    ("sessions", [("expiresAt", ASCENDING)], {"expireAfterSeconds": 0}),
    ("sessions", [("user", ASCENDING)], {}),
    ("rate_limits", [("expiresAt", ASCENDING)], {"expireAfterSeconds": 0}),
]

# MongoDB codes for an index that already exists with different options/name.
_INDEX_CONFLICT_CODES = {85, 86}


class DatabaseUnavailable(RuntimeError):
    pass


async def connect(settings: Settings) -> tuple[AsyncMongoClient, AsyncDatabase]:
    client: AsyncMongoClient = AsyncMongoClient(
        settings.mongo_uri, tz_aware=True, tzinfo=IST, serverSelectionTimeoutMS=settings.mongo_timeout_ms,
        appname="ak-royal-flames",
    )
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        log.error("MongoDB connection failed: %s", exc)
        await client.close()
        raise DatabaseUnavailable(str(exc)) from exc
    log.info("MongoDB connected successfully")
    return client, client[settings.database_name]


async def ensure_indexes(db: AsyncDatabase) -> None:
    for collection, keys, options in INDEXES:
        try:
            await db[collection].create_index(keys, **options)
        except OperationFailure as exc:
            if exc.code in _INDEX_CONFLICT_CODES:
                log.warning("Index on %s %s already exists with different options; left unchanged", collection, keys)
                continue
            raise

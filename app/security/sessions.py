"""Server-side sessions stored in `sessions` (D-04). Only the SHA-256 of the token is stored."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

from bson import ObjectId
from fastapi.responses import Response
from pymongo.asynchronous.database import AsyncDatabase

from app.config import Settings
from app.core.documents import now_ist

SESSION_COOKIE = "akrf_session"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(db: AsyncDatabase, user_id: ObjectId, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    now = now_ist()
    await db.sessions.insert_one(
        {
            "_id": hash_token(token),
            "user": user_id,
            "createdAt": now,
            "expiresAt": now + timedelta(seconds=settings.session_ttl_seconds),
            "pendingOrder": None,
        }
    )
    return token


async def get_session(db: AsyncDatabase, token: str) -> dict[str, Any] | None:
    if not token or len(token) > 200:
        return None
    session = await db.sessions.find_one({"_id": hash_token(token)})
    if not session or session["expiresAt"] <= now_ist():
        return None
    return session


async def delete_session(db: AsyncDatabase, token: str | None) -> None:
    if token:
        await db.sessions.delete_one({"_id": hash_token(token)})


async def set_pending_order(db: AsyncDatabase, session_id: str, pending: dict[str, Any] | None) -> None:
    await db.sessions.update_one({"_id": session_id}, {"$set": {"pendingOrder": pending}})


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )

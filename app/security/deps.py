"""Authentication state and role guards (BE §5.5–5.6, D-45, D-52)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from pymongo.errors import PyMongoError

from app.core.errors import AdminRequired, LoginRequired
from app.security.sessions import SESSION_COOKIE, get_session

log = logging.getLogger("akrf.auth")


@dataclass
class AuthState:
    user: dict[str, Any] | None
    session: dict[str, Any] | None
    token: str | None
    error: str | None


async def resolve_auth(request: Request) -> AuthState:
    """Load the session and the current user (without password) once per request (FR-032)."""
    cached = getattr(request.state, "auth", None)
    if cached is not None:
        return cached
    db = request.app.state.db
    token = request.cookies.get(SESSION_COOKIE)
    state = AuthState(user=None, session=None, token=token, error="Please login first")
    if token:
        try:
            session = await get_session(db, token)
            if session is None:
                state.error = "Invalid or expired session"
            else:
                state.session = session
                user = await db.users.find_one({"_id": session["user"]}, {"password": 0})
                if user is None:
                    state.error = "User not found"
                else:
                    state.user = user
                    state.error = None
        except PyMongoError as exc:
            log.warning("Auth middleware error: %s", type(exc).__name__)
            state.error = "Invalid or expired session"
    request.state.auth = state
    return state


async def current_user(request: Request) -> dict[str, Any] | None:
    return (await resolve_auth(request)).user


async def require_user(request: Request) -> dict[str, Any]:
    state = await resolve_auth(request)
    if state.user is None:
        raise LoginRequired(state.error or "Please login first")
    return state.user


async def require_admin(request: Request) -> dict[str, Any]:
    user = await require_user(request)
    if user.get("role") != "admin":
        raise AdminRequired()
    return user


def is_admin(user: dict[str, Any] | None) -> bool:
    return bool(user) and user.get("role") == "admin"

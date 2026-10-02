"""CSRF protection (D-06).

UI: signed double-submit token. An HttpOnly cookie holds a random secret; pages embed
HMAC(SECRET_KEY, secret) in a meta tag / hidden field; HTMX sends it as `X-CSRF-Token`.
API: state-changing requests must come from an allowed Origin (the legacy SPA sends no token).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import CsrfFailed, Forbidden

CSRF_COOKIE = "akrf_csrf"
CSRF_HEADER = "x-csrf-token"
CSRF_FIELD = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _signed(secret_key: str, value: str) -> str:
    return hmac.new(secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


class CsrfCookieMiddleware:
    """Guarantees every request has a CSRF secret, issuing the cookie when missing."""

    def __init__(self, app: ASGIApp, *, secure: bool) -> None:
        self.app = app
        self.secure = secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cookies = SimpleCookie()
        for name, value in scope.get("headers", []):
            if name == b"cookie":
                try:
                    cookies.load(value.decode("latin-1"))
                except Exception:  # noqa: BLE001 - malformed cookie header: treat as absent
                    pass
        existing = cookies.get(CSRF_COOKIE)
        secret = existing.value if existing and 20 <= len(existing.value) <= 100 else None
        issued = secret is None
        if issued:
            secret = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csrf_secret"] = secret
        scope["state"]["csrf_cookie_present"] = not issued

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and issued:
                attrs = f"{CSRF_COOKIE}={secret}; Path=/; HttpOnly; SameSite=Lax"
                if self.secure:
                    attrs += "; Secure"
                message.setdefault("headers", []).append((b"set-cookie", attrs.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_wrapper)


def csrf_token(request: Request) -> str:
    secret = request.state.csrf_secret
    return _signed(request.app.state.settings.secret_key, secret)


async def csrf_protect(request: Request) -> None:
    """Router dependency for every UI router: unsafe methods must carry a valid token."""
    if request.method in SAFE_METHODS:
        return
    if not request.state.csrf_cookie_present:
        raise CsrfFailed()
    supplied = request.headers.get(CSRF_HEADER)
    if not supplied:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form()
            value = form.get(CSRF_FIELD)
            supplied = value if isinstance(value, str) else None
    if not supplied or not hmac.compare_digest(supplied, csrf_token(request)):
        raise CsrfFailed()


def _origin_of(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def api_origin_check(request: Request) -> None:
    """Router dependency for `/api/*`: state-changing calls need an allowed Origin/Referer."""
    if request.method in SAFE_METHODS:
        return
    origin = _origin_of(request.headers.get("origin")) or _origin_of(request.headers.get("referer"))
    if origin is None or origin not in request.app.state.settings.allowed_origins:
        raise Forbidden("Request origin not allowed")

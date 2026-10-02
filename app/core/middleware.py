"""Pure-ASGI middleware: request id, path normalisation, body limits, security headers, API CORS."""

from __future__ import annotations

import json
import secrets

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings
from app.core.errors import BodyTooLarge
from app.logging_config import request_id_var

_EXEMPT_PREFIXES = ("/static/", "/uploads/")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id") or ""
        rid = incoming if incoming.isalnum() and len(incoming) <= 64 else secrets.token_hex(8)
        token = request_id_var.set(rid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


class PathNormalizeMiddleware:
    """Case-insensitive routing with optional trailing slash (FR-012, D-17)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if not path.startswith(_EXEMPT_PREFIXES):
                new_path = path.lower()
                if len(new_path) > 1 and new_path.endswith("/"):
                    new_path = new_path.rstrip("/") or "/"
                if new_path != path:
                    scope = dict(scope)
                    scope["path"] = new_path
                    scope["raw_path"] = new_path.encode()
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """Reject bodies above the limit with 413 (FR-005, D-18)."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.json_limit = settings.max_body_bytes
        self.multipart_limit = settings.max_upload_bytes + 1024 * 1024

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_type = _header(scope, b"content-type") or ""
        limit = self.multipart_limit if content_type.startswith("multipart/") else self.json_limit
        declared = _header(scope, b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await _send_413(scope, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        await self.app(scope, limited_receive, send)


async def _send_413(scope: Scope, send: Send) -> None:
    if scope["path"].startswith("/api"):
        body = json.dumps({"success": False, "message": "Request body is too large"}).encode()
        content_type = b"application/json"
    else:
        body = (
            b"<!doctype html><html lang=en><head><meta charset=utf-8><title>Too large</title></head>"
            b"<body><h1>Request too large</h1><p>The file or form you sent is too large.</p></body></html>"
        )
        content_type = b"text/html; charset=utf-8"
    await send({
        "type": "http.response.start",
        "status": 413,
        "headers": [(b"content-type", content_type), (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close")],
    })
    await send({"type": "http.response.body", "body": body})


PAGE_CSP = (
    "default-src 'self'; img-src 'self' data: blob: https:; media-src 'self'; "
    "frame-src https://www.youtube.com https://www.youtube-nocookie.com https://www.google.com; "
    "script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.hsts = settings.cookie_secure and settings.is_production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {k.lower() for k, _ in headers}
                defaults = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", PAGE_CSP.encode()),
                ]
                if self.hsts:
                    defaults.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                for key, value in defaults:
                    if key not in present:
                        headers.append((key, value))
            await send(message)

        await self.app(scope, receive, send_wrapper)


class ApiCorsMiddleware:
    """CORS for `/api/*` only, with an explicit origin allow-list (FR-003, FR-004, D-19)."""

    METHODS = b"GET,HEAD,PUT,PATCH,POST,DELETE"

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.allowed = settings.allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api"):
            await self.app(scope, receive, send)
            return
        origin = _header(scope, b"origin")
        allowed = origin is not None and origin.rstrip("/") in self.allowed
        if scope["method"] == "OPTIONS" and _header(scope, b"access-control-request-method"):
            headers = [(b"vary", b"Origin"), (b"content-length", b"0")]
            if allowed:
                headers += [
                    (b"access-control-allow-origin", origin.encode()),
                    (b"access-control-allow-credentials", b"true"),
                    (b"access-control-allow-methods", self.METHODS),
                ]
                requested = _header(scope, b"access-control-request-headers")
                if requested:
                    headers.append((b"access-control-allow-headers", requested.encode()))
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"vary", b"Origin"))
                if allowed:
                    headers.append((b"access-control-allow-origin", origin.encode()))
                    headers.append((b"access-control-allow-credentials", b"true"))
            await send(message)

        await self.app(scope, receive, send_wrapper)

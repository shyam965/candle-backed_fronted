"""One-shot toast messages carried across redirects in a signed, HttpOnly cookie."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi import Request
from fastapi.responses import Response

FLASH_COOKIE = "akrf_flash"


def _sign(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def set_flash(response: Response, request: Request, message: str, kind: str = "success") -> Response:
    settings = request.app.state.settings
    items = read_flash(request) + [{"type": kind, "message": message}]
    payload = base64.urlsafe_b64encode(json.dumps(items[-5:]).encode()).decode()
    value = f"{payload}.{_sign(settings.secret_key, payload.encode())}"
    response.set_cookie(
        FLASH_COOKIE, value, max_age=60, path="/", httponly=True,
        secure=settings.cookie_secure, samesite="lax",
    )
    return response


def read_flash(request: Request) -> list[dict[str, Any]]:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw or "." not in raw:
        return []
    payload, signature = raw.rsplit(".", 1)
    expected = _sign(request.app.state.settings.secret_key, payload.encode())
    if not hmac.compare_digest(signature, expected):
        return []
    try:
        items = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except ValueError:
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("message"), str)]


def clear_flash(response: Response, request: Request) -> None:
    if FLASH_COOKIE in request.cookies:
        response.delete_cookie(FLASH_COOKIE, path="/", secure=request.app.state.settings.cookie_secure,
                               httponly=True, samesite="lax")

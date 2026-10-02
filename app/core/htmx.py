"""HTMX helpers: request detection, toasts via HX-Trigger, client-side redirects."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import Request
from fastapi.responses import Response

ToastKind = Literal["success", "error", "info"]


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def add_trigger(response: Response, event: str, detail: Any = True) -> Response:
    existing = response.headers.get("HX-Trigger")
    events: dict[str, Any] = {}
    if existing:
        try:
            events = json.loads(existing)
        except ValueError:
            events = {name.strip(): True for name in existing.split(",") if name.strip()}
    if event == "toast":
        toasts = events.get("toast")
        items = toasts.get("items", []) if isinstance(toasts, dict) else []
        items.append(detail)
        events["toast"] = {"items": items}
    else:
        events[event] = detail
    response.headers["HX-Trigger"] = json.dumps(events, ensure_ascii=False)
    return response


def toast(response: Response, message: str, kind: ToastKind = "success") -> Response:
    return add_trigger(response, "toast", {"type": kind, "message": message})


def hx_redirect(url: str, *, status_code: int = 200) -> Response:
    response = Response(status_code=status_code)
    response.headers["HX-Redirect"] = url
    return response


def current_path(request: Request) -> str:
    """Path (+ query) of the page that issued an HTMX request, from HX-Current-URL."""
    from urllib.parse import urlsplit

    current = request.headers.get("hx-current-url")
    if current:
        parts = urlsplit(current)
        return parts.path + (f"?{parts.query}" if parts.query else "")
    return request.url.path

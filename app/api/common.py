"""Shared helpers for the JSON compatibility API (D-01, D-21)."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from app.core.errors import ValidationFailed
from app.core.serialization import to_json

_BRACKETS = re.compile(r"^([^\[\]]+)((?:\[[^\[\]]*\])+)$")


def _nest(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`customer[name]=X` → `{"customer": {"name": "X"}}` (BE §3.4 URL-encoded nested bodies)."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        match = _BRACKETS.match(key)
        if not match:
            result[key] = value
            continue
        parts = [match.group(1)] + re.findall(r"\[([^\[\]]*)\]", match.group(2))
        node = result
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
    return result


async def read_body(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        raw = await request.body()
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ValidationFailed("Invalid JSON body") from exc
        return data if isinstance(data, dict) else {}
    if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
        form = await request.form()
        return _nest([(k, v) for k, v in form.multi_items() if not isinstance(v, UploadFile)])
    return {}


def ok(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(to_json(payload), status_code=status_code)


def style_b(request: Request) -> None:
    """Router dependency: category/product endpoints use the `{message, success, error}` envelope."""
    request.state.api_style = "B"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

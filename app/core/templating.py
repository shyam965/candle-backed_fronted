"""Jinja2 environment, filters and the page/partial render helpers."""

from __future__ import annotations

import hashlib
from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, Settings
from app.core import formatting, links, validators
from app.core.flash import clear_flash, read_flash
from app.security.csrf import csrf_token
from app.security.deps import is_admin, resolve_auth

STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"


@lru_cache(maxsize=256)
def _static_version(path: str) -> str:
    file = STATIC_DIR / path
    try:
        return hashlib.md5(file.read_bytes(), usedforsecurity=False).hexdigest()[:10]
    except OSError:
        return "0"


def static_url(path: str) -> str:
    path = path.lstrip("/")
    return f"/static/{path}?v={_static_version(path)}"


def create_templates(settings: Settings) -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    env = templates.env
    env.trim_blocks = True
    env.lstrip_blocks = True
    tz = settings.tz
    env.filters.update(
        inr=formatting.inr,
        discount=formatting.discount_percent,
        date=lambda v: formatting.fmt_date(v, tz),
        datetime=lambda v: formatting.fmt_datetime(v, tz),
        image_url=formatting.image_url,
        cta_href=links.cta_href,
        safe_color=validators.safe_color,
        num=formatting.to_number,
    )
    env.tests["external_link"] = links.is_external
    from app.services.order_view import TEMPLATE_GLOBALS

    env.globals.update(settings=settings, static_url=static_url, is_admin=is_admin, **TEMPLATE_GLOBALS)
    if settings.app_env == "development":
        _static_version.cache_clear()
    return templates


async def base_context(request: Request, *, full_page: bool) -> dict[str, Any]:
    auth = await resolve_auth(request)
    context: dict[str, Any] = {
        "request": request,
        "current_user": auth.user,
        "csrf_token": csrf_token(request),
        "current_path": request.url.path,
        "now_year": datetime.now(request.app.state.settings.tz).year,
    }
    if full_page:
        from app.services.cart_service import count_items

        context["cart_count"] = await count_items(request.app.state.db, auth.user) if auth.user else 0
        context["flash_messages"] = read_flash(request)
    return context


async def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    full_page: bool = True,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    ctx = await base_context(request, full_page=full_page)
    ctx.update(context or {})
    response = request.app.state.templates.TemplateResponse(
        request, template, ctx, status_code=status_code, headers=headers
    )
    if full_page and ctx.get("flash_messages"):
        clear_flash(response, request)
    return response

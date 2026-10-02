"""Admin → Dashboard (FE §5.10, FR-UI-097–FR-UI-102, D-46)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from app.core.htmx import toast
from app.core.templating import render
from app.services import dashboard_service
from app.web.admin import admin_router

log = logging.getLogger("akrf.admin.dashboard")
router = admin_router(prefix="/admin")


async def _stats(request: Request) -> dict[str, Any]:
    try:
        return {"summary": await dashboard_service.summary(request.app.state.db)}
    except PyMongoError:
        log.exception("Dashboard stats failed")
        return {"stats_error": "Unable to load dashboard"}


async def _recent(request: Request) -> dict[str, Any]:
    try:
        orders, total = await dashboard_service.recent_orders(request.app.state.db)
        return {"recent": orders, "orders_total": total}
    except PyMongoError:
        log.exception("Dashboard recent orders failed")
        return {"recent_error": "Unable to load dashboard"}


def _with_error_toast(response: Response, context: dict[str, Any]) -> Response:
    message = context.get("stats_error") or context.get("recent_error")
    return toast(response, message, "error") if message else response


@router.get("")
async def page(request: Request) -> Response:
    return await render(request, "admin/dashboard.html")


@router.get("/_p/stats")
async def stats(request: Request) -> Response:
    context = await _stats(request)
    return _with_error_toast(await render(request, "admin/partials/dashboard_stats.html", context, full_page=False), context)


@router.get("/_p/recent-orders")
async def recent(request: Request) -> Response:
    context = await _recent(request)
    return _with_error_toast(await render(request, "admin/partials/recent_orders.html", context, full_page=False), context)


@router.get("/_p/dashboard")
async def refresh(request: Request) -> Response:
    """Refresh button: both sections at once, each with its own error state (FR-UI-102)."""
    context = {**await _stats(request), **await _recent(request), "oob": True}
    return _with_error_toast(await render(request, "admin/partials/dashboard_refresh.html", context, full_page=False), context)

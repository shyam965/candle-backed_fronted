"""Admin → Orders (FE §5.15, FR-UI-120–FR-UI-125, D-16, D-30, D-38)."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.htmx import toast
from app.core.templating import render
from app.services import dashboard_service, order_service
from app.web.admin import admin_router

log = logging.getLogger("akrf.admin.orders")
router = admin_router(prefix="/admin/orders")


def _filters(request: Request) -> dict[str, Any]:
    q = (request.query_params.get("q") or "").strip()[:100]
    status = request.query_params.get("status") or ""
    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except ValueError:
        page = 1
    return {"q": q, "status": status if status in order_service.STATUSES else "", "page": page}


def _query(filters: dict[str, Any]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if filters["status"]:
        query["status"] = filters["status"]
    if filters["q"]:
        pattern = {"$regex": re.escape(filters["q"]), "$options": "i"}
        query["$or"] = [{"customer.name": pattern}, {"customer.mobile": pattern}, {"orderId": pattern}]
    return query


async def _table_context(request: Request) -> dict[str, Any]:
    db, settings = request.app.state.db, request.app.state.settings
    filters = _filters(request)
    context: dict[str, Any] = {"filters": filters, "statuses": order_service.STATUSES}
    try:
        query = _query(filters)
        total = await db.orders.count_documents(query)
        size = settings.admin_orders_page_size
        pages = max(1, math.ceil(total / size))
        page = min(filters["page"], pages)
        orders = [o async for o in db.orders.find(query).sort("createdAt", -1).skip((page - 1) * size).limit(size)]
        context.update(orders=orders, total=total, page=page, pages=pages,
                       stats=await dashboard_service.status_counts(db))
    except PyMongoError:
        log.exception("Failed to load orders")
        context["load_error"] = "Unable to load orders"
    return context


@router.get("")
async def page(request: Request) -> Response:
    return await render(request, "admin/orders.html", {"filters": _filters(request), "statuses": order_service.STATUSES})


@router.get("/_table")
async def table(request: Request) -> Response:
    context = await _table_context(request)
    response = await render(request, "admin/partials/orders_table.html", context, full_page=False)
    if context.get("load_error"):
        toast(response, context["load_error"], "error")
    return response


@router.get("/{order_id}")
async def modal(order_id: str, request: Request) -> Response:
    order = await order_service.get_any(request.app.state.db, order_id)
    return await render(request, "admin/partials/order_modal.html", {"order": order, "statuses": order_service.STATUSES},
                        full_page=False)


@router.put("/{order_id}/status")
async def change_status(order_id: str, request: Request) -> Response:
    form = await request.form()
    statuses = [v for v in form.getlist("status") if isinstance(v, str)]
    data = {"status": statuses[0] if statuses else None, "source": form.get("source")}
    db = request.app.state.db
    try:
        order = await order_service.change_status(db, order_id, data["status"])
    except AppError as exc:
        if exc.status_code == 404:
            raise
        return toast(Response(status_code=exc.status_code), exc.message, "error")
    context = {"order": order, "statuses": order_service.STATUSES, "stats": await dashboard_service.status_counts(db),
               "from_modal": data.get("source") == "modal"}
    response = await render(request, "admin/partials/order_status_result.html", context, full_page=False)
    return toast(response, f"Order status changed to {order['status']}")

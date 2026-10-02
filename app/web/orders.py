"""Customer orders: My Orders and Order Details (FE §5.7–5.8, FR-UI-084–FR-UI-093, D-49, D-50)."""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from pymongo.errors import PyMongoError

from app.core.errors import NotFound
from app.core.flash import set_flash
from app.core.htmx import toast
from app.core.templating import render
from app.security.deps import require_user
from app.services import order_service
from app.web.common import ui_router

log = logging.getLogger("akrf.orders")
router = ui_router()


@router.get("/my-orders")
async def my_orders(request: Request, user: dict = Depends(require_user)) -> Response:
    return await render(request, "pages/orders/list.html")


@router.get("/my-orders/_list")
async def my_orders_list(request: Request, user: dict = Depends(require_user)) -> Response:
    try:
        orders = await order_service.list_for_user(request.app.state.db, user)
    except PyMongoError:
        log.exception("Failed to load orders")
        response = await render(request, "partials/orders/list.html", {"load_error": "Unable to load orders"}, full_page=False)
        return toast(response, "Unable to load orders", "error")
    return await render(request, "partials/orders/list.html", {"orders": orders}, full_page=False)


@router.get("/my-orders/{order_id}")
async def order_detail(order_id: str, request: Request, user: dict = Depends(require_user)) -> Response:
    try:
        order = await order_service.get_for_user(request.app.state.db, user, order_id)
    except NotFound:
        response = RedirectResponse("/my-orders", status_code=303)
        set_flash(response, request, "Order not found", "error")
        return response
    return await render(request, "pages/orders/detail.html", {"order": order})

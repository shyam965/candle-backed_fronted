"""Cart page and HTMX cart actions (FE §5.5, FR-UI-057–FR-UI-067, D-28, D-47)."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from fastapi.responses import Response

from app.core.errors import AppError
from app.core.htmx import toast
from app.core.templating import render
from app.core.validators import digits_only
from app.security.deps import current_user, require_user, resolve_auth
from app.services import cart_service
from app.web.common import form_data, ui_router

router = ui_router()


def delivery_defaults(user: dict[str, Any]) -> dict[str, str]:
    """Pre-fill from the profile (FR-UI-068); mobile/pincode keep digits only (FR-UI-069)."""
    return {
        "name": user.get("name") or "",
        "mobile": digits_only(user.get("phone") or "", 10),
        "address": user.get("address") or "",
        "city": user.get("city") or "",
        "pincode": digits_only(user.get("pincode") or "", 6),
        "message": "",
    }


async def cart_context(request: Request, user: dict[str, Any]) -> dict[str, Any]:
    settings = request.app.state.settings
    cart = await cart_service.load(request.app.state.db, user, prune=True)
    lines = [line for line in cart["items"] if line.get("product")]
    auth = await resolve_auth(request)
    return {
        "lines": lines,
        "totals": cart_service.totals(lines, settings.free_delivery_threshold),
        "cart_count": sum(int(line.get("quantity") or 1) for line in lines),
        "pending_order": (auth.session or {}).get("pendingOrder"),
    }


@router.get("/cart")
async def cart_page(request: Request, user: dict | None = Depends(current_user)) -> Response:
    if user is None:
        return await render(request, "pages/cart.html", {"guest": True})
    context = await cart_context(request, user)
    context.update(values=delivery_defaults(user), errors={})
    return await render(request, "pages/cart.html", context)


async def _after_change(request: Request, user: dict[str, Any], error: AppError | None = None) -> Response:
    context = await cart_context(request, user)
    if not context["lines"]:
        context.update(values=delivery_defaults(user), errors={})
        response = await render(request, "partials/cart/root.html", context, full_page=False)
        response.headers["HX-Retarget"] = "#cart-root"
        response.headers["HX-Reswap"] = "outerHTML"
    else:
        response = await render(request, "partials/cart/update.html", context, full_page=False)
    if error is not None:
        toast(response, error.message, "error")
    return response


async def _apply(request: Request, user: dict[str, Any], action) -> Response:
    try:
        await action()
    except AppError as exc:
        return await _after_change(request, user, exc)
    return await _after_change(request, user)


@router.put("/cart/items/{product_id}")
async def set_quantity(product_id: str, request: Request, user: dict = Depends(require_user)) -> Response:
    data = await form_data(request)
    db = request.app.state.db
    return await _apply(request, user, lambda: cart_service.set_quantity(db, user, product_id, data.get("quantity")))


@router.delete("/cart/items/{product_id}")
async def remove(product_id: str, request: Request, user: dict = Depends(require_user)) -> Response:
    db = request.app.state.db
    return await _apply(request, user, lambda: cart_service.remove(db, user, product_id))


@router.put("/cart/items/{product_id}/selected")
async def set_selected(product_id: str, request: Request, user: dict = Depends(require_user)) -> Response:
    data = await form_data(request)
    db = request.app.state.db
    return await _apply(request, user, lambda: cart_service.set_selected(db, user, product_id, data.get("selected", "false")))


@router.put("/cart/selection")
async def select_all(request: Request, user: dict = Depends(require_user)) -> Response:
    data = await form_data(request)
    db = request.app.state.db
    return await _apply(request, user, lambda: cart_service.select_all(db, user, data.get("selected", "false")))

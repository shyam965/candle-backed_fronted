"""WhatsApp checkout (FE §5.5–5.6, FR-UI-068–FR-UI-083, D-29, D-34, D-39)."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.core.errors import AppError
from app.core.flash import set_flash
from app.core.htmx import add_trigger, hx_redirect, toast
from app.core.templating import render
from app.security.deps import require_user, resolve_auth
from app.security.sessions import set_pending_order
from app.services import cart_service, order_service, whatsapp
from app.web.common import form_data, ui_router

router = ui_router()


async def _session(request: Request) -> dict[str, Any]:
    return (await resolve_auth(request)).session or {}


def _order_message(request: Request, pending: dict[str, Any]) -> str:
    return whatsapp.order_message(pending, request.app.state.settings.free_delivery_threshold)


@router.post("/cart/checkout")
async def checkout(request: Request, user: dict = Depends(require_user)) -> Response:
    db, settings = request.app.state.db, request.app.state.settings
    customer, errors = order_service.validate_customer(await form_data(request))

    async def form(status_code: int, form_error: str | None = None) -> Response:
        return await render(request, "partials/cart/delivery_form.html",
                            {"values": customer, "errors": errors, "form_error": form_error},
                            status_code=status_code, full_page=False)

    cart = await cart_service.load(db, user, prune=True)
    selected = [line for line in cart["items"] if line.get("product") and cart_service.is_selected(line)]
    if not selected:
        return toast(await form(422, "Please select at least one product."), "Please select at least one product.", "error")
    if errors:
        return await form(422)
    try:
        lines = await order_service.build_lines(db, [(line["product"]["_id"], int(line.get("quantity") or 1))
                                                     for line in selected])
    except AppError as exc:
        return toast(await form(422, exc.message), exc.message, "error")
    pending = order_service.pending_from_lines(customer, lines, settings.free_delivery_threshold)
    await set_pending_order(db, (await _session(request))["_id"], pending)
    response = hx_redirect("/whatsapp-confirm")
    add_trigger(response, "openWhatsApp", {"url": whatsapp.wa_me(settings.whatsapp_number, _order_message(request, pending))})
    set_flash(response, request, "WhatsApp opened. Send the message and return here.", "info")
    return response


@router.delete("/cart/pending-order")
async def discard_pending(request: Request, user: dict = Depends(require_user)) -> Response:
    await set_pending_order(request.app.state.db, (await _session(request))["_id"], None)
    return toast(Response(status_code=200), "Pending order discarded", "info")


def _valid_pending(pending: Any) -> bool:
    return isinstance(pending, dict) and isinstance(pending.get("items"), list) and bool(pending["items"]) \
        and isinstance(pending.get("customer"), dict) and bool(pending.get("orderId"))


@router.get("/whatsapp-confirm")
async def confirm_page(request: Request, user: dict = Depends(require_user)) -> Response:
    session = await _session(request)
    pending = session.get("pendingOrder")
    if pending is None:
        response = RedirectResponse("/cart", status_code=303)
        set_flash(response, request, "No pending WhatsApp order found.", "error")
        return response
    if not _valid_pending(pending):
        await set_pending_order(request.app.state.db, session["_id"], None)
        response = RedirectResponse("/cart", status_code=303)
        set_flash(response, request, "Pending order data is invalid.", "error")
        return response
    resend = whatsapp.api_send(request.app.state.settings.whatsapp_number, _order_message(request, pending))
    return await render(request, "pages/checkout/confirm.html", {"pending": pending, "resend_url": resend})


@router.post("/whatsapp-confirm")
async def confirm_order(request: Request, user: dict = Depends(require_user)) -> Response:
    db, settings = request.app.state.db, request.app.state.settings
    session = await _session(request)
    pending = session.get("pendingOrder")
    if not _valid_pending(pending):
        response = hx_redirect("/cart")
        set_flash(response, request, "Pending order information not found.", "error")
        return response
    try:
        await order_service.create_from_pending(db, user, pending, settings.free_delivery_threshold)
    except AppError as exc:
        return toast(Response(status_code=422), exc.message or "Failed to create order.", "error")
    await set_pending_order(db, session["_id"], None)
    response = hx_redirect("/my-orders")
    set_flash(response, request, "Order placed successfully!")
    return response

"""`/api/cart/*` (BE §6.5 + FE §6.2.6 select-all) — authenticated, own cart only (FR-065)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import ok, read_body
from app.security.csrf import api_origin_check
from app.security.deps import require_user
from app.services import cart_service

router = APIRouter(prefix="/api/cart", dependencies=[Depends(api_origin_check)])


def _respond(cart: dict, message: str | None = None) -> JSONResponse:
    payload: dict = {"success": True}
    if message:
        payload["message"] = message
    payload["cart"] = cart
    return ok(payload)


@router.get("")
async def get_cart(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    return _respond(await cart_service.load(request.app.state.db, user))


@router.post("/add")
async def add(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    body = await read_body(request)
    cart = await cart_service.add(request.app.state.db, user, body.get("productId"), body.get("quantity"))
    return _respond(cart, "Product added to cart")


@router.put("/update")
async def update(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    body = await read_body(request)
    cart = await cart_service.set_quantity(request.app.state.db, user, body.get("productId"), body.get("quantity"))
    return _respond(cart, "Cart updated")


@router.delete("/remove/{product_id}")
async def remove(product_id: str, request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    return _respond(await cart_service.remove(request.app.state.db, user, product_id), "Product removed")


@router.put("/toggle")
async def toggle(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    body = await read_body(request)
    cart = await cart_service.set_selected(request.app.state.db, user, body.get("productId"), body.get("selected"))
    return _respond(cart, "Selection updated")


@router.put("/select-all")
async def select_all(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    body = await read_body(request)
    return _respond(await cart_service.select_all(request.app.state.db, user, body.get("selected")), "Selection updated")


@router.delete("/clear")
async def clear(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    return _respond(await cart_service.clear(request.app.state.db, user), "Cart cleared")

"""`/api/order/*` (BE §6.6) — style-A envelope."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import ok, read_body
from app.security.csrf import api_origin_check
from app.security.deps import require_admin, require_user
from app.services import order_service

router = APIRouter(prefix="/api/order", dependencies=[Depends(api_origin_check)])


@router.post("/create")
async def create(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    db, settings = request.app.state.db, request.app.state.settings
    order = await order_service.create_from_items(db, user, await read_body(request), settings.free_delivery_threshold)
    populated = (await order_service.populate(db, [order], with_user=True))[0]
    return ok({"success": True, "message": "Order created successfully", "order": populated}, 201)


@router.get("/my-orders")
async def my_orders(request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    return ok({"success": True, "orders": await order_service.list_for_user(request.app.state.db, user)})


@router.get("/my-orders/{order_id}")
async def my_order(order_id: str, request: Request, user: dict = Depends(require_user)) -> JSONResponse:
    return ok({"success": True, "order": await order_service.get_for_user(request.app.state.db, user, order_id)})


@router.get("/all", dependencies=[Depends(require_admin)])
async def all_orders(request: Request) -> JSONResponse:
    return ok({"success": True, "orders": await order_service.list_all(request.app.state.db)})


@router.put("/status/{order_id}", dependencies=[Depends(require_admin)])
async def change_status(order_id: str, request: Request) -> JSONResponse:
    body = await read_body(request)
    order = await order_service.change_status(request.app.state.db, order_id, body.get("status"))
    return ok({"success": True, "message": f"Order status changed to {order['status']}", "order": order})

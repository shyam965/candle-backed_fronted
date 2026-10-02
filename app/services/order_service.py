"""Orders (BE §6.6, BR-19–BR-31, D-29–D-34)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.documents import num, now_ist
from app.core.errors import NotFound, ValidationFailed
from app.core.formatting import to_number
from app.core.ids import parse_object_id
from app.core.validators import Invalid, is_mobile, is_pincode, parse_int
from app.models import OrderDoc, check
from app.services.product_service import stock_of

STATUSES = ("Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled")
FLOW = STATUSES[:5]
TERMINAL = {"Delivered", "Cancelled"}
PAYMENT_METHOD = "WhatsApp Order"
DELIVERY_DAYS = 3

CUSTOMER_MESSAGES = {
    "name": "Please enter your full name.",
    "mobile": "Please enter your mobile number.",
    "address": "Please enter your complete address.",
    "city": "Please enter your city.",
    "pincode": "Please enter your pincode.",
}
MOBILE_INVALID = "Please enter a valid 10 digit mobile number."
PINCODE_INVALID = "Please enter a valid 6 digit pincode."
CUSTOMER_LIMITS = {"name": 120, "mobile": 10, "address": 500, "city": 80, "pincode": 6, "message": 500}


# ---------- pure rules ----------

def generate_order_id(now: datetime | None = None) -> str:
    """`AKRF-<epoch ms>-<1000–9999>` (BR-23, FR-087)."""
    now = now or now_ist()
    return f"AKRF-{int(now.timestamp() * 1000)}-{1000 + secrets.randbelow(9000)}"


def expected_delivery(now: datetime) -> datetime:
    """Order time + 72 hours, IST arithmetic (no DST) (BR-25, D-33)."""
    return now + timedelta(days=DELIVERY_DAYS)


def allowed_next(current: str) -> list[str]:
    """Forward moves along the flow plus Cancel; Delivered/Cancelled are terminal (D-30)."""
    if current in TERMINAL:
        return []
    if current not in FLOW:
        return list(STATUSES)
    index = FLOW.index(current)
    return [*FLOW[index + 1:], "Cancelled"]


def check_transition(current: str, new: str) -> None:
    if new not in STATUSES:
        raise ValidationFailed("Invalid order status")
    if new == current:
        raise ValidationFailed(f"Order is already {new}")
    if new not in allowed_next(current):
        raise ValidationFailed(f"Cannot change order status from {current} to {new}")


def apply_status(order: dict[str, Any], new: str, now: datetime) -> dict[str, Any]:
    """Return the `$set` for a status change (FR-099–FR-101)."""
    changes: dict[str, Any] = {"status": new, f"statusDates.{new}": now}
    if new == "Cancelled":
        changes["expectedDelivery"] = None
    elif order.get("expectedDelivery") is None:
        changes["expectedDelivery"] = expected_delivery(now)
    return changes


def validate_customer(data: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Trim and validate delivery details; returns (values, field errors) with the UI messages (FR-UI-070/071)."""
    source = data if isinstance(data, dict) else {}
    values: dict[str, str] = {}
    errors: dict[str, str] = {}
    for key in ("name", "mobile", "address", "city", "pincode", "message"):
        raw = source.get(key)
        values[key] = raw.strip() if isinstance(raw, str) else ""
        if raw is not None and not isinstance(raw, str):
            errors[key] = CUSTOMER_MESSAGES.get(key, "Invalid value")
    for key, message in CUSTOMER_MESSAGES.items():
        if key not in errors and not values[key]:
            errors[key] = message
    if "mobile" not in errors and not is_mobile(values["mobile"]):
        errors["mobile"] = MOBILE_INVALID
    if "pincode" not in errors and not is_pincode(values["pincode"]):
        errors["pincode"] = PINCODE_INVALID
    for key, limit in CUSTOMER_LIMITS.items():
        if key not in errors and len(values[key]) > limit:
            errors[key] = f"Must be at most {limit} characters."
    return values, errors


def summarize(items: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    items_total = num(round(sum(to_number(i["total"]) or 0 for i in items), 2))
    return {
        "itemsTotal": items_total,
        "shipping": 0,
        "shippingStatus": "FREE" if items_total >= threshold else "PAYABLE_SEPARATELY",
        "grandTotal": items_total,
    }


# ---------- server-priced lines (D-29) ----------

async def build_lines(db: AsyncDatabase, requested: list[tuple[ObjectId, int]]) -> list[dict[str, Any]]:
    merged: dict[ObjectId, int] = {}
    for pid, qty in requested:
        merged[pid] = merged.get(pid, 0) + qty
    products = {p["_id"]: p async for p in db.products.find({"_id": {"$in": list(merged)}})}
    lines = []
    for pid, qty in merged.items():
        product = products.get(pid)
        if product is None:
            raise ValidationFailed("Some products in your order are no longer available. Please review your cart.")
        stock = stock_of(product)
        if qty > stock:
            raise ValidationFailed(f"Only {stock} items available for {product.get('name', 'this product')}")
        price = to_number(product.get("price")) or 0
        lines.append({
            "product": pid,
            "name": product.get("name", ""),
            "image": product.get("image", "") or "",
            "price": num(price),
            "quantity": qty,
            "total": num(round(price * qty, 2)),
        })
    return lines


def pending_from_lines(customer: dict[str, str], lines: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    now = now_ist()
    return {"orderId": generate_order_id(now), "customer": customer, "items": lines,
            **summarize(lines, threshold), "createdAt": now}


# ---------- persistence ----------

def _order_doc(order_id: str, user_id: ObjectId, customer: dict[str, str], lines: list[dict[str, Any]],
               totals: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "orderId": order_id,
        "user": user_id,
        "customer": {k: customer.get(k, "") for k in ("name", "mobile", "address", "city", "pincode", "message")},
        "items": lines,
        **totals,
        "paymentMethod": PAYMENT_METHOD,
        "status": "Pending",
        "statusDates": {s: (now if s == "Pending" else None) for s in STATUSES},
        "expectedDelivery": expected_delivery(now),
        "createdAt": now,
        "updatedAt": now,
        "__v": 0,
    }


async def _insert(db: AsyncDatabase, doc: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(5):
        try:
            doc["_id"] = (await db.orders.insert_one(check(OrderDoc, doc))).inserted_id
            return doc
        except DuplicateKeyError:
            doc.pop("_id", None)
            if attempt == 4:
                raise
            doc["orderId"] = generate_order_id()
    return doc


async def cleanup_cart(db: AsyncDatabase, user_id: ObjectId, lines: list[dict[str, Any]]) -> None:
    """Remove the ordered quantities from the cart; lines reaching 0 disappear (BR-26, D-32)."""
    cart = await db.carts.find_one({"user": user_id})
    if not cart:
        return
    ordered = {line["product"]: line["quantity"] for line in lines}
    items, changed = [], False
    for item in cart.get("items", []):
        qty = ordered.get(item.get("product"))
        if qty is None:
            items.append(item)
            continue
        changed = True
        remaining = int(item.get("quantity") or 1) - qty
        if remaining > 0:
            items.append({**item, "quantity": remaining})
    if changed:
        await db.carts.update_one({"_id": cart["_id"]},
                                  {"$set": {"items": items, "updatedAt": now_ist()}, "$inc": {"__v": 1}})


async def create_from_pending(db: AsyncDatabase, user: dict[str, Any], pending: dict[str, Any],
                              threshold: float) -> dict[str, Any]:
    """Confirm a checkout: re-check availability, keep the quoted prices and order id (D-34, D-39)."""
    items = pending.get("items") or []
    if not items:
        raise ValidationFailed("No products found in this order.")
    lines = await build_lines(db, [(i["product"], int(i["quantity"])) for i in items])
    quoted = {i["product"]: i for i in items}
    for line in lines:
        quote = quoted[line["product"]]
        line.update(price=quote["price"], total=quote["total"], name=quote["name"], image=quote["image"])
    totals = summarize(lines, threshold)
    doc = _order_doc(pending["orderId"], user["_id"], pending["customer"], lines, totals, now_ist())
    order = await _insert(db, doc)
    await cleanup_cart(db, user["_id"], lines)
    return order


async def create_from_items(db: AsyncDatabase, user: dict[str, Any], data: dict[str, Any],
                            threshold: float) -> dict[str, Any]:
    """`POST /api/order/create`: only product ids and quantities are taken from the client (D-29)."""
    customer, errors = validate_customer(data.get("customer"))
    if any(errors.get(k) == CUSTOMER_MESSAGES[k] for k in CUSTOMER_MESSAGES):
        raise ValidationFailed("Please provide complete customer details", errors=errors)
    if errors:
        raise ValidationFailed(next(iter(errors.values())), errors=errors)
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationFailed("At least one product is required")
    requested: list[tuple[ObjectId, int]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValidationFailed("Invalid order product data")
        pid = parse_object_id(item.get("product") or item.get("productId"))
        try:
            qty = parse_int(item.get("quantity") if item.get("quantity") not in (None, "") else 1)
        except Invalid as exc:
            raise ValidationFailed("Invalid order product data") from exc
        if pid is None or not item.get("name") or qty <= 0:
            raise ValidationFailed("Invalid order product data")
        requested.append((pid, qty))
    lines = await build_lines(db, requested)
    now = now_ist()
    doc = _order_doc(generate_order_id(now), user["_id"], customer, lines, summarize(lines, threshold), now)
    order = await _insert(db, doc)
    await cleanup_cart(db, user["_id"], lines)
    return order


# ---------- queries ----------

async def populate(db: AsyncDatabase, orders: list[dict[str, Any]], *, with_user: bool) -> list[dict[str, Any]]:
    product_ids = {i.get("product") for o in orders for i in o.get("items", [])}
    products = {p["_id"]: p async for p in db.products.find({"_id": {"$in": list(product_ids)}})} if product_ids else {}
    users: dict[Any, dict[str, Any]] = {}
    if with_user:
        ids = list({o.get("user") for o in orders})
        users = {u["_id"]: u async for u in db.users.find({"_id": {"$in": ids}}, {"password": 0})}
    result = []
    for order in orders:
        copy = dict(order)
        copy["items"] = [{**i, "product": products.get(i.get("product"))} for i in order.get("items", [])]
        if with_user:
            copy["user"] = users.get(order.get("user"))
        result.append(copy)
    return result


async def list_for_user(db: AsyncDatabase, user: dict[str, Any]) -> list[dict[str, Any]]:
    orders = [o async for o in db.orders.find({"user": user["_id"]}).sort("createdAt", -1)]
    return await populate(db, orders, with_user=False)


async def get_for_user(db: AsyncDatabase, user: dict[str, Any], order_id: Any) -> dict[str, Any]:
    oid = parse_object_id(order_id)
    order = await db.orders.find_one({"_id": oid, "user": user["_id"]}) if oid else None
    if order is None:
        raise NotFound("Order not found")
    return (await populate(db, [order], with_user=False))[0]


async def get_any(db: AsyncDatabase, order_id: Any) -> dict[str, Any]:
    oid = parse_object_id(order_id)
    if oid is None:
        raise ValidationFailed("Invalid order ID")
    order = await db.orders.find_one({"_id": oid})
    if order is None:
        raise NotFound("Order not found")
    return (await populate(db, [order], with_user=True))[0]


async def list_all(db: AsyncDatabase) -> list[dict[str, Any]]:
    orders = [o async for o in db.orders.find({}).sort("createdAt", -1)]
    return await populate(db, orders, with_user=True)


async def change_status(db: AsyncDatabase, order_id: Any, status: Any) -> dict[str, Any]:
    if not isinstance(status, str) or status not in STATUSES:
        raise ValidationFailed("Invalid order status")
    oid = parse_object_id(order_id)
    if oid is None:
        raise ValidationFailed("Invalid order ID")
    order = await db.orders.find_one({"_id": oid})
    if order is None:
        raise NotFound("Order not found")
    current = order.get("status") or "Pending"
    check_transition(current, status)
    now = now_ist()
    changes = apply_status(order, status, now)
    changes["updatedAt"] = now
    updated = await db.orders.find_one_and_update(
        {"_id": oid, "status": order.get("status")}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    if updated is None:
        raise ValidationFailed("This order was just updated by someone else. Please refresh and try again.")
    return (await populate(db, [updated], with_user=True))[0]

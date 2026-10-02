"""Cart business logic (BE §6.5, BR-14–BR-18, D-28)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.documents import new_meta, utcnow
from app.core.errors import NotFound, ValidationFailed
from app.core.formatting import to_number
from app.core.ids import parse_object_id
from app.core.validators import Invalid, parse_bool, parse_int
from app.models import CartDoc

CART_NOT_FOUND_LINE = "Product not found in cart"


def _changed() -> dict[str, Any]:
    return {"$set": {"updatedAt": utcnow()}, "$inc": {"__v": 1}}


async def count_items(db: AsyncDatabase, user: dict[str, Any]) -> int:
    """Sum of quantities of all lines whose product still exists (FR-UI-005, FR-UI-058)."""
    cart = await db.carts.find_one({"user": user["_id"]}, {"items": 1})
    items = (cart or {}).get("items") or []
    if not items:
        return 0
    existing = set(await db.products.distinct("_id", {"_id": {"$in": [i["product"] for i in items]}}))
    return sum(int(i.get("quantity", 1)) for i in items if i.get("product") in existing)


def _new_cart() -> dict[str, Any]:
    doc = {"items": [], **new_meta()}
    CartDoc.model_validate({**doc, "user": ObjectId()})
    return doc


async def get_or_create(db: AsyncDatabase, user_id: ObjectId) -> dict[str, Any]:
    """Exactly one cart per user, created atomically (BR-14, KI-29)."""
    for _ in range(3):
        try:
            return await db.carts.find_one_and_update(
                {"user": user_id},
                {"$setOnInsert": _new_cart()},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            continue
    cart = await db.carts.find_one({"user": user_id})
    if cart is None:
        raise RuntimeError("cart could not be created")
    return cart


async def populate(db: AsyncDatabase, cart: dict[str, Any]) -> dict[str, Any]:
    """Replace `items[].product` with the product document, or None when it no longer exists (FR-067)."""
    items = cart.get("items") or []
    ids = [i.get("product") for i in items]
    products = {p["_id"]: p async for p in db.products.find({"_id": {"$in": ids}})} if ids else {}
    populated = dict(cart)
    populated["items"] = [{**i, "product": products.get(i.get("product"))} for i in items]
    return populated


async def load(db: AsyncDatabase, user: dict[str, Any], *, prune: bool = False) -> dict[str, Any]:
    cart = await populate(db, await get_or_create(db, user["_id"]))
    missing = [i for i in cart["items"] if i["product"] is None]
    if prune and missing:
        raw = await db.carts.find_one({"_id": cart["_id"]})
        dangling = [i["product"] for i in raw["items"] if i["product"] not in
                    {line["product"]["_id"] for line in cart["items"] if line["product"]}]
        update = _changed()
        update["$pull"] = {"items": {"product": {"$in": dangling}}}
        await db.carts.update_one({"_id": cart["_id"]}, update)
        cart["items"] = [i for i in cart["items"] if i["product"] is not None]
    return cart


def _quantity(value: Any, *, default: int | None, message: str) -> int:
    if value is None or value == "":
        if default is None:
            raise ValidationFailed(message)
        return default
    try:
        return parse_int(value)
    except Invalid as exc:
        raise ValidationFailed(message) from exc


async def _product(db: AsyncDatabase, product_id: Any) -> dict[str, Any]:
    oid = parse_object_id(product_id)
    if oid is None:
        raise ValidationFailed("Invalid product ID")
    product = await db.products.find_one({"_id": oid})
    if product is None:
        raise NotFound("Product not found")
    return product


def _stock(product: dict[str, Any]) -> int:
    value = to_number(product.get("stock"))
    return int(value) if value is not None else 0


def _over_stock(stock: int) -> ValidationFailed:
    return ValidationFailed(f"Only {stock} items available")


async def add(db: AsyncDatabase, user: dict[str, Any], product_id: Any, quantity: Any) -> dict[str, Any]:
    """Add `quantity` (default 1) or increase an existing line and re-select it (FR-068–FR-072)."""
    if not product_id:
        raise ValidationFailed("Product ID is required")
    product = await _product(db, product_id)
    qty = _quantity(quantity, default=1, message="Quantity must be at least 1")
    if qty < 1:
        raise ValidationFailed("Quantity must be at least 1")
    stock = _stock(product)
    if qty > stock:
        raise _over_stock(stock)
    cart = await get_or_create(db, user["_id"])
    pid = product["_id"]
    for _ in range(3):
        update = _changed()
        update["$inc"]["items.$.quantity"] = qty
        update["$set"]["items.$.selected"] = True
        result = await db.carts.update_one(
            {"_id": cart["_id"], "items": {"$elemMatch": {"product": pid, "quantity": {"$lte": stock - qty}}}}, update
        )
        if result.modified_count:
            break
        if await db.carts.find_one({"_id": cart["_id"], "items.product": pid}, {"_id": 1}):
            raise _over_stock(stock)
        push = _changed()
        push["$push"] = {"items": {"product": pid, "quantity": qty, "selected": True}}
        result = await db.carts.update_one({"_id": cart["_id"], "items.product": {"$ne": pid}}, push)
        if result.modified_count:
            break
    return await load(db, user)


async def set_quantity(db: AsyncDatabase, user: dict[str, Any], product_id: Any, quantity: Any) -> dict[str, Any]:
    """Set (not add) a line's quantity, checked against current stock (FR-073–FR-075)."""
    qty = _quantity(quantity, default=None, message="Invalid cart data")
    oid = parse_object_id(product_id)
    if not product_id or qty < 1:
        raise ValidationFailed("Invalid cart data")
    cart = await get_or_create(db, user["_id"])
    if oid is None or not any(i.get("product") == oid for i in cart.get("items", [])):
        raise NotFound(CART_NOT_FOUND_LINE)
    product = await db.products.find_one({"_id": oid})
    if product is not None and qty > _stock(product):
        raise _over_stock(_stock(product))
    update = _changed()
    update["$set"]["items.$.quantity"] = qty
    result = await db.carts.update_one({"_id": cart["_id"], "items.product": oid}, update)
    if not result.matched_count:
        raise NotFound(CART_NOT_FOUND_LINE)
    return await load(db, user)


async def remove(db: AsyncDatabase, user: dict[str, Any], product_id: Any) -> dict[str, Any]:
    """Remove a line; succeeds even when the line is absent (FR-076, D-28)."""
    cart = await get_or_create(db, user["_id"])
    oid = parse_object_id(product_id)
    if oid is not None and any(i.get("product") == oid for i in cart.get("items", [])):
        update = _changed()
        update["$pull"] = {"items": {"product": oid}}
        await db.carts.update_one({"_id": cart["_id"]}, update)
    return await load(db, user)


async def set_selected(db: AsyncDatabase, user: dict[str, Any], product_id: Any, selected: Any) -> dict[str, Any]:
    """Only an explicit false-like value deselects; a missing value selects (FR-077, KI-20)."""
    try:
        flag = parse_bool(selected, default=True)
    except Invalid as exc:
        raise ValidationFailed("Invalid cart data") from exc
    cart = await get_or_create(db, user["_id"])
    oid = parse_object_id(product_id)
    if oid is None or not any(i.get("product") == oid for i in cart.get("items", [])):
        raise NotFound(CART_NOT_FOUND_LINE)
    update = _changed()
    update["$set"]["items.$.selected"] = flag
    await db.carts.update_one({"_id": cart["_id"], "items.product": oid}, update)
    return await load(db, user)


async def select_all(db: AsyncDatabase, user: dict[str, Any], selected: Any) -> dict[str, Any]:
    try:
        flag = parse_bool(selected, default=True)
    except Invalid as exc:
        raise ValidationFailed("Invalid cart data") from exc
    cart = await get_or_create(db, user["_id"])
    if cart.get("items"):
        update = _changed()
        update["$set"]["items.$[].selected"] = flag
        await db.carts.update_one({"_id": cart["_id"]}, update)
    return await load(db, user)


async def clear(db: AsyncDatabase, user: dict[str, Any]) -> dict[str, Any]:
    cart = await get_or_create(db, user["_id"])
    if cart.get("items"):
        update = _changed()
        update["$set"]["items"] = []
        await db.carts.update_one({"_id": cart["_id"]}, update)
    return await load(db, user)


# ---------- totals (FR-UI-065–FR-UI-067, FR-UI-074) ----------

@dataclass(frozen=True)
class CartTotals:
    items_total: float
    selected_quantity: int
    all_quantity: int
    free_shipping: bool
    amount_for_free: float
    grand_total: float
    shipping_status: str


def is_selected(line: dict[str, Any]) -> bool:
    return line.get("selected") is not False


def line_total(line: dict[str, Any]) -> float:
    price = to_number((line.get("product") or {}).get("price")) or 0.0
    return price * int(line.get("quantity") or 1)


def totals(lines: list[dict[str, Any]], threshold: float) -> CartTotals:
    live = [line for line in lines if line.get("product")]
    selected = [line for line in live if is_selected(line)]
    items_total = round(sum(line_total(line) for line in selected), 2)
    free = items_total >= threshold
    return CartTotals(
        items_total=items_total,
        selected_quantity=sum(int(line.get("quantity") or 1) for line in selected),
        all_quantity=sum(int(line.get("quantity") or 1) for line in live),
        free_shipping=free,
        amount_for_free=round(max(threshold - items_total, 0), 2),
        grand_total=items_total,
        shipping_status="FREE" if free else "PAYABLE_SEPARATELY",
    )

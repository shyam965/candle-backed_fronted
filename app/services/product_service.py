"""Products (BE §6.4, BR-08–BR-13, D-24, D-25, D-26, D-35)."""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.documents import new_meta, num, touch, utcnow
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.formatting import to_number
from app.core.ids import parse_object_id
from app.core.validators import Invalid, parse_int, parse_number
from app.models import ProductDoc, check
from app.services import category_service
from app.services.upload_service import ImageUpload, UploadStore

MISSING: Any = object()
REQUIRED = "Name, category, price and stock are required"
INVALID_ID = "Invalid product ID"
NOT_FOUND = "Product not found"
EXISTS = "Product already exists"
OLD_BELOW = "Old price cannot be less than price"


# ---------- value parsers (raise Invalid) ----------

def parse_price(value: Any) -> float:
    price = parse_number(value)
    if price < 1:
        raise Invalid("price below 1")
    return price


def parse_old_price(value: Any) -> float | None:
    """`""`/None → no old price (FR-060, K-18); otherwise finite ≥ 1."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_price(value)


def parse_stock(value: Any) -> int:
    stock = parse_int(value)
    if stock < 0:
        raise Invalid("negative stock")
    return stock


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _name(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationFailed(message, field="name")
    name = value.strip()
    if len(name) > 120:
        raise ValidationFailed("Product name must be at most 120 characters", field="name")
    return name


def _description(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationFailed("Description must be text", field="description")
    description = value.strip()
    if len(description) > 2000:
        raise ValidationFailed("Description must be at most 2000 characters", field="description")
    return description


async def _category_id(db: AsyncDatabase, value: Any) -> ObjectId:
    oid = parse_object_id(value)
    if oid is None:
        raise ValidationFailed(category_service.INVALID_ID, field="category")
    if not await db.categories.find_one({"_id": oid}, {"_id": 1}):
        raise NotFound(category_service.NOT_FOUND, field="category")
    return oid


async def _ensure_unique(db: AsyncDatabase, name: str, category: ObjectId, exclude: ObjectId | None = None) -> None:
    query: dict[str, Any] = {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "category": category}
    if exclude is not None:
        query["_id"] = {"$ne": exclude}
    if await db.products.find_one(query, {"_id": 1}):
        raise Conflict(EXISTS, field="name")


# ---------- queries ----------

async def list_all(db: AsyncDatabase) -> list[dict[str, Any]]:
    return [doc async for doc in db.products.find({})]


async def get(db: AsyncDatabase, product_id: Any) -> dict[str, Any]:
    oid = parse_object_id(product_id)
    if oid is None:
        raise ValidationFailed(INVALID_ID)
    doc = await db.products.find_one({"_id": oid})
    if doc is None:
        raise NotFound(NOT_FOUND)
    return doc


async def image_in_use_by_orders(db: AsyncDatabase, image: str | None) -> bool:
    return bool(image) and await db.orders.find_one({"items.image": image}, {"_id": 1}) is not None


async def _release_image(db: AsyncDatabase, store: UploadStore, image: str | None) -> None:
    """Delete a product image unless order history still shows it (D-35)."""
    if image and not await image_in_use_by_orders(db, image):
        await store.delete(image)


# ---------- commands ----------

async def create(db: AsyncDatabase, store: UploadStore, data: dict[str, Any], image: ImageUpload | None) -> dict[str, Any]:
    if (_blank(data.get("name")) or not data.get("category") or data.get("price") in (None, "")
            or data.get("stock") in (None, "")):
        raise ValidationFailed(REQUIRED)
    if image is None:
        raise ValidationFailed("Please upload an image", field="image")
    name = _name(data["name"], REQUIRED)
    category = await _category_id(db, data["category"])
    try:
        price = parse_price(data["price"])
        old_price = parse_old_price(data.get("oldPrice"))
        stock = parse_stock(data["stock"])
    except Invalid as exc:
        raise ValidationFailed("Invalid price, old price or stock") from exc
    if old_price is not None and old_price < price:
        raise ValidationFailed(OLD_BELOW, field="oldPrice")
    description = _description(data.get("description"))
    await _ensure_unique(db, name, category)
    path = await store.save(image)
    doc: dict[str, Any] = {"name": name, "category": category, "price": num(price)}
    if old_price is not None:
        doc["oldPrice"] = num(old_price)
    doc.update({"stock": stock, "description": description, "image": path, **new_meta()})
    try:
        doc["_id"] = (await db.products.insert_one(check(ProductDoc, doc))).inserted_id
    except Exception:
        await store.delete(path)
        raise
    return doc


async def update(db: AsyncDatabase, store: UploadStore, product_id: Any, data: dict[str, Any],
                 image: ImageUpload | None) -> dict[str, Any]:
    current = await get(db, product_id)
    sets: dict[str, Any] = {}
    unsets: dict[str, Any] = {}
    name = current.get("name", "")
    category = current.get("category")
    if data.get("name", MISSING) is not MISSING:
        name = _name(data["name"], "Product name is required")
        sets["name"] = name
    if data.get("category", MISSING) is not MISSING:
        category = await _category_id(db, data["category"])
        sets["category"] = category
    price = current.get("price")
    if data.get("price", MISSING) is not MISSING:
        try:
            price = parse_price(data["price"])
        except Invalid as exc:
            raise ValidationFailed("Invalid price", field="price") from exc
        sets["price"] = num(price)
    old_price = current.get("oldPrice")
    if data.get("oldPrice", MISSING) is not MISSING:
        try:
            old_price = parse_old_price(data["oldPrice"])
        except Invalid as exc:
            raise ValidationFailed("Invalid old price", field="oldPrice") from exc
        if old_price is None:
            unsets["oldPrice"] = ""
        else:
            sets["oldPrice"] = num(old_price)
    touched_prices = "price" in sets or "oldPrice" in sets or "oldPrice" in unsets
    if touched_prices and old_price is not None and price is not None and old_price < price:
        raise ValidationFailed(OLD_BELOW, field="oldPrice")
    if data.get("stock", MISSING) is not MISSING:
        try:
            sets["stock"] = parse_stock(data["stock"])
        except Invalid as exc:
            raise ValidationFailed("Invalid stock", field="stock") from exc
    if data.get("description", MISSING) is not MISSING:
        sets["description"] = _description(data["description"])
    if ("name" in sets or "category" in sets) and category is not None:
        await _ensure_unique(db, name, category, exclude=current["_id"])

    new_path = await store.save(image) if image else None
    if new_path:
        sets["image"] = new_path
    update_doc = touch({"$set": sets})
    if unsets:
        update_doc["$unset"] = unsets
    try:
        updated = await db.products.find_one_and_update({"_id": current["_id"]}, update_doc,
                                                         return_document=ReturnDocument.AFTER)
    except DuplicateKeyError as exc:
        await store.delete(new_path)
        raise Conflict(EXISTS) from exc
    except Exception:
        await store.delete(new_path)
        raise
    if updated is None:
        await store.delete(new_path)
        raise NotFound(NOT_FOUND)
    if new_path and current.get("image") != new_path:
        await _release_image(db, store, current.get("image"))
    return updated


async def delete(db: AsyncDatabase, store: UploadStore, product_id: Any) -> dict[str, Any]:
    oid = parse_object_id(product_id)
    if oid is None:
        raise ValidationFailed(INVALID_ID)
    deleted = await db.products.find_one_and_delete({"_id": oid})
    if deleted is None:
        raise NotFound(NOT_FOUND)
    await db.carts.update_many(
        {"items.product": oid},
        {"$pull": {"items": {"product": oid}}, "$set": {"updatedAt": utcnow()}, "$inc": {"__v": 1}},
    )
    await _release_image(db, store, deleted.get("image"))
    return deleted


# ---------- presentation helpers ----------

def stock_of(product: dict[str, Any]) -> int:
    value = to_number(product.get("stock"))
    return int(value) if value is not None else 0


def category_name(product: dict[str, Any], names: dict[Any, str], fallback: str) -> str:
    category = product.get("category")
    if isinstance(category, dict):
        return category.get("name") or fallback
    return names.get(category, fallback)


def matches(product: dict[str, Any], query: str, names: dict[Any, str]) -> bool:
    q = query.casefold()
    haystack = (product.get("name") or "", category_name(product, names, ""), product.get("description") or "")
    return any(q in part.casefold() for part in haystack)

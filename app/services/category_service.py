"""Categories (BE §6.3, BR-06, BR-07, BR-12, D-24)."""

from __future__ import annotations

import re
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.documents import new_meta, touch
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import parse_object_id
from app.models import CategoryDoc, check
from app.services.upload_service import ImageUpload, UploadStore

MISSING: Any = object()
NAME_REQUIRED = "Category name is required"
EXISTS = "Category already exists"
NOT_FOUND = "Category not found"
INVALID_ID = "Invalid category ID"
HAS_PRODUCTS = "This category contains products. Delete or reassign those products first."


def name_query(name: str) -> dict[str, Any]:
    """Case-insensitive exact-name match (KI-31)."""
    return {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}


async def list_all(db: AsyncDatabase) -> list[dict[str, Any]]:
    return [doc async for doc in db.categories.find({})]


async def get(db: AsyncDatabase, category_id: Any) -> dict[str, Any]:
    oid = parse_object_id(category_id)
    if oid is None:
        raise ValidationFailed(INVALID_ID)
    doc = await db.categories.find_one({"_id": oid})
    if doc is None:
        raise NotFound(NOT_FOUND)
    return doc


def _clean_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationFailed(NAME_REQUIRED, field="name")
    name = value.strip()
    if len(name) > 120:
        raise ValidationFailed("Category name must be at most 120 characters", field="name")
    return name


def _clean_description(value: Any) -> str:
    description = value.strip() if isinstance(value, str) else ""
    if len(description) > 2000:
        raise ValidationFailed("Description must be at most 2000 characters", field="description")
    return description


async def create(db: AsyncDatabase, store: UploadStore, data: dict[str, Any], image: ImageUpload | None,
                 *, image_message: str = "Please upload an image") -> dict[str, Any]:
    name = _clean_name(data.get("name"))
    description = _clean_description(data.get("description"))
    if image is None:
        raise ValidationFailed(image_message, field="image")
    if await db.categories.find_one(name_query(name), {"_id": 1}):
        raise Conflict(EXISTS, field="name")
    path = await store.save(image)
    doc = {"name": name, "description": description, "image": path, **new_meta()}
    try:
        doc["_id"] = (await db.categories.insert_one(check(CategoryDoc, doc))).inserted_id
    except DuplicateKeyError as exc:
        await store.delete(path)
        raise Conflict(EXISTS, field="name") from exc
    except Exception:
        await store.delete(path)
        raise
    return doc


async def update(db: AsyncDatabase, store: UploadStore, category_id: Any, data: dict[str, Any],
                 image: ImageUpload | None) -> dict[str, Any]:
    current = await get(db, category_id)
    changes: dict[str, Any] = {}
    if data.get("name", MISSING) is not MISSING:
        name = _clean_name(data["name"])
        clash = await db.categories.find_one({**name_query(name), "_id": {"$ne": current["_id"]}}, {"_id": 1})
        if clash:
            raise Conflict(EXISTS, field="name")
        changes["name"] = name
    if data.get("description", MISSING) is not MISSING:
        changes["description"] = _clean_description(data["description"])
    new_path = await store.save(image) if image else None
    if new_path:
        changes["image"] = new_path
    try:
        updated = await db.categories.find_one_and_update(
            {"_id": current["_id"]}, touch({"$set": changes}), return_document=ReturnDocument.AFTER
        )
    except DuplicateKeyError as exc:
        await store.delete(new_path)
        raise Conflict(EXISTS, field="name") from exc
    except Exception:
        await store.delete(new_path)
        raise
    if updated is None:
        await store.delete(new_path)
        raise NotFound(NOT_FOUND)
    if new_path and current.get("image") != new_path:
        await store.delete(current.get("image"))
    return updated


async def delete(db: AsyncDatabase, store: UploadStore, category_id: Any) -> dict[str, Any]:
    current = await get(db, category_id)
    if await db.products.find_one({"category": current["_id"]}, {"_id": 1}):
        raise Conflict(HAS_PRODUCTS)
    result = await db.categories.delete_one({"_id": current["_id"]})
    if result.deleted_count == 0:
        raise NotFound(NOT_FOUND)
    await store.delete(current.get("image"))
    return current


def matches(category: dict[str, Any], query: str) -> bool:
    q = query.casefold()
    return q in (category.get("name") or "").casefold() or q in (category.get("description") or "").casefold()

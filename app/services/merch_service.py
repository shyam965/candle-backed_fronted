"""Banners and promotional cards (BE §6.7–6.8, BR-32–BR-35, D-27, D-36, D-37)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.documents import new_meta, num
from app.core.errors import NotFound, ValidationFailed
from app.core.ids import parse_object_id
from app.core.links import is_valid_button_link
from app.core.validators import DEFAULT_PROMO_BACKGROUND, Invalid, is_color, parse_number
from app.models import BannerDoc, PromoCardDoc, check
from app.services.upload_service import ImageUpload, UploadStore

SORT = [("order", 1), ("createdAt", -1)]


@dataclass(frozen=True)
class MerchKind:
    collection: str
    title_required: str
    image_required: str
    created: str
    deleted: str
    not_found: str
    invalid_id: str
    has_background: bool = False


BANNER = MerchKind(
    collection="banners",
    title_required="Banner title is required",
    image_required="Banner image is required",
    created="Banner created successfully",
    deleted="Banner deleted successfully",
    not_found="Banner not found",
    invalid_id="Invalid banner ID",
)
PROMO = MerchKind(
    collection="promocards",
    title_required="Promo card title is required",
    image_required="Promo card image is required",
    created="Promotional card created successfully",
    deleted="Promotional card deleted successfully",
    not_found="Promo card not found",
    invalid_id="Invalid promo card ID",
    has_background=True,
)


def _text(value: Any, limit: int, field: str, label: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if len(text) > limit:
        raise ValidationFailed(f"{label} must be at most {limit} characters", field=field)
    return text


def parse_status(value: Any) -> bool:
    """Omitted → true; `true` / `"true"` → true; any other supplied value → false (BR-34)."""
    if value is None:
        return True
    return value is True or value == "true"


def parse_order(value: Any) -> int | float:
    """`Number(order) || 0` (BE §6.7.1)."""
    try:
        return num(parse_number(value))
    except Invalid:
        return 0


async def create(db: AsyncDatabase, store: UploadStore, kind: MerchKind, data: dict[str, Any],
                 image: ImageUpload | None) -> dict[str, Any]:
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationFailed(kind.title_required, field="title")
    title = _text(title, 120, "title", "Title")
    subtitle = _text(data.get("subtitle"), 200, "subtitle", "Subtitle")
    button_text = _text(data.get("buttonText"), 40, "buttonText", "Button text") or "Shop Now"
    button_link = _text(data.get("buttonLink"), 500, "buttonLink", "Button link") or "/shop"
    if not is_valid_button_link(button_link):
        raise ValidationFailed("Button link must start with / or http(s)://", field="buttonLink")
    doc: dict[str, Any] = {"title": title, "subtitle": subtitle}
    if image is None:
        raise ValidationFailed(kind.image_required, field="image")
    if kind.has_background:
        background = _text(data.get("background"), 7, "background", "Background") or DEFAULT_PROMO_BACKGROUND
        if not is_color(background):
            raise ValidationFailed("Background must be a hex colour like #08aaa6", field="background")
    doc.update({"image": await store.save(image), "buttonText": button_text, "buttonLink": button_link})
    if kind.has_background:
        doc["background"] = background
    doc.update({"order": parse_order(data.get("order")), "status": parse_status(data.get("status")), **new_meta()})
    try:
        check(PromoCardDoc if kind.has_background else BannerDoc, doc)
        doc["_id"] = (await db[kind.collection].insert_one(doc)).inserted_id
    except Exception:
        await store.delete(doc["image"])
        raise
    return doc


async def list_active(db: AsyncDatabase, kind: MerchKind) -> list[dict[str, Any]]:
    return [d async for d in db[kind.collection].find({"status": True}).sort(SORT)]


async def list_all(db: AsyncDatabase, kind: MerchKind) -> list[dict[str, Any]]:
    return [d async for d in db[kind.collection].find({}).sort(SORT)]


async def delete(db: AsyncDatabase, store: UploadStore, kind: MerchKind, item_id: Any) -> dict[str, Any]:
    oid = parse_object_id(item_id)
    if oid is None:
        raise ValidationFailed(kind.invalid_id)
    deleted = await db[kind.collection].find_one_and_delete({"_id": oid})
    if deleted is None:
        raise NotFound(kind.not_found)
    await store.delete(deleted.get("image"))
    return deleted

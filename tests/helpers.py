"""Shared test helpers: users, login, CSRF/HTMX headers, image bytes and data factories."""

from __future__ import annotations

import hashlib
import hmac
import struct
import zlib
from datetime import timedelta
from typing import Any

from bson import ObjectId
from httpx import AsyncClient

from app.core.documents import new_meta, utcnow
from app.security.csrf import CSRF_COOKIE
from app.security.passwords import hash_password_sync
from app.security.sessions import SESSION_COOKIE, create_session

PASSWORD = "secret1"
_HASH = hash_password_sync(PASSWORD)
API_ORIGIN = {"Origin": "https://testserver"}


def _png(width: int = 1, height: int = 1) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x80\x20" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = _png()
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0d\x00\x00\x00\x2f\x00\x00\x00\x10\x07\x10\x11\x11\x88\x88\xfe\x07\x00"
FAKE_PNG = b"<html><script>alert(1)</script></html>"


def image_file(data: bytes = PNG, name: str = "photo.png", content_type: str = "image/png") -> dict[str, Any]:
    return {"image": (name, data, content_type)}


async def make_user(db, *, role: str = "user", email: str | None = None, name: str = "Asha Verma",
                    phone: str = "9876543210", **extra: Any) -> dict[str, Any]:
    doc = {
        "name": name,
        "email": email or f"user{ObjectId()}@example.com",
        "phone": phone,
        "password": _HASH,
        "address": extra.pop("address", ""),
        "city": extra.pop("city", ""),
        "pincode": extra.pop("pincode", ""),
        "role": role,
        **new_meta(),
        **extra,
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def login(client: AsyncClient, app, user: dict[str, Any]) -> str:
    token = await create_session(app.state.db, user["_id"], app.state.settings)
    client.cookies.set(SESSION_COOKIE, token)
    return token


async def login_as(client: AsyncClient, app, role: str = "user", **kwargs: Any) -> dict[str, Any]:
    user = await make_user(app.state.db, role=role, **kwargs)
    await login(client, app, user)
    return user


async def csrf_token(client: AsyncClient, app) -> str:
    if not client.cookies.get(CSRF_COOKIE):
        await client.get("/healthz")
    secret = client.cookies.get(CSRF_COOKIE)
    return hmac.new(app.state.settings.secret_key.encode(), secret.encode(), hashlib.sha256).hexdigest()


async def hx(client: AsyncClient, app, *, current_url: str | None = None) -> dict[str, str]:
    headers = {"HX-Request": "true", "X-CSRF-Token": await csrf_token(client, app)}
    if current_url:
        headers["HX-Current-URL"] = f"https://testserver{current_url}"
    return headers


# ---------- data factories ----------

async def make_category(db, name: str = "Jar Candles", **extra: Any) -> dict[str, Any]:
    doc = {"name": name, "description": extra.pop("description", "Soy wax candles"),
           "image": extra.pop("image", "/uploads/cat.png"), **new_meta(), **extra}
    doc["_id"] = (await db.categories.insert_one(doc)).inserted_id
    return doc


async def make_product(db, category: dict[str, Any] | None = None, name: str = "Lavender Jar Candle",
                       price: float = 499, stock: int = 25, **extra: Any) -> dict[str, Any]:
    if category is None:
        category = await make_category(db, name=f"Cat {ObjectId()}")
    doc = {"name": name, "category": category["_id"], "price": price, "stock": stock,
           "description": extra.pop("description", "Hand-poured lavender soy candle"),
           "image": extra.pop("image", "/uploads/prod.png"), **new_meta(), **extra}
    doc["_id"] = (await db.products.insert_one(doc)).inserted_id
    return doc


async def make_order(db, user: dict[str, Any], *, status: str = "Pending", products: list[dict[str, Any]] | None = None,
                     created_offset_minutes: int = 0, **extra: Any) -> dict[str, Any]:
    now = utcnow() - timedelta(minutes=created_offset_minutes)
    items = []
    for p in products or []:
        items.append({"product": p["_id"], "name": p["name"], "image": p["image"], "price": p["price"],
                      "quantity": 2, "total": p["price"] * 2})
    if not items:
        items = [{"product": ObjectId(), "name": "Rose Candle", "image": "/uploads/r.png", "price": 499,
                  "quantity": 2, "total": 998}]
    total = sum(i["total"] for i in items)
    dates = {s: None for s in ("Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled")}
    dates["Pending"] = now
    if status != "Pending":
        dates[status] = now
    doc = {
        "orderId": f"AKRF-{int(now.timestamp() * 1000)}-{1000 + int(str(ObjectId())[-4:], 16) % 9000}",
        "user": user["_id"],
        "customer": {"name": "Asha Verma", "mobile": "9876543210", "address": "12 MG Road", "city": "Jaipur",
                     "pincode": "302001", "message": extra.pop("message", "")},
        "items": items, "itemsTotal": total, "shipping": 0,
        "shippingStatus": "FREE" if total >= 1099 else "PAYABLE_SEPARATELY", "grandTotal": total,
        "paymentMethod": "WhatsApp Order", "status": status, "statusDates": dates,
        "expectedDelivery": None if status == "Cancelled" else now + timedelta(days=3),
        "createdAt": now, "updatedAt": now, "__v": 0, **extra,
    }
    doc["_id"] = (await db.orders.insert_one(doc)).inserted_id
    return doc

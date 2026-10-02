"""Admin dashboard and order statistics (FR-UI-099–FR-UI-101, FR-UI-121)."""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.documents import num
from app.services.order_service import STATUSES


async def status_counts(db: AsyncDatabase) -> dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    async for row in await db.orders.aggregate([{"$group": {"_id": {"$ifNull": ["$status", "Pending"]}, "n": {"$sum": 1}}}]):
        if row["_id"] in counts:
            counts[row["_id"]] += row["n"]
    return counts


async def delivered_revenue(db: AsyncDatabase) -> int | float:
    result = [r async for r in await db.orders.aggregate([
        {"$match": {"status": "Delivered"}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$grandTotal", 0]}}}},
    ])]
    return num(round(float(result[0]["total"]), 2)) if result else 0


async def summary(db: AsyncDatabase) -> dict[str, Any]:
    counts = await status_counts(db)
    return {
        "products": await db.products.count_documents({}),
        "categories": await db.categories.count_documents({}),
        "orders": sum(counts.values()),
        "revenue": await delivered_revenue(db),
        "status_counts": counts,
    }


async def recent_orders(db: AsyncDatabase, limit: int = 5) -> tuple[list[dict[str, Any]], int]:
    orders = [o async for o in db.orders.find({}).sort("createdAt", -1).limit(limit)]
    users = {u["_id"]: u async for u in db.users.find({"_id": {"$in": [o.get("user") for o in orders]}}, {"password": 0})}
    for order in orders:
        order["user"] = users.get(order.get("user"))
    return orders, await db.orders.count_documents({})

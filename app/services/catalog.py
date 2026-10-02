"""Storefront catalogue views: latest products, shop filter/search/sort, category counts (FR-UI-037, 045–053)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from app.core.documents import IST
from app.core.formatting import to_number
from app.core.ids import parse_object_id
from app.services.product_service import category_name

SORTS = {"default": "Featured", "low": "Price: Low to High", "high": "Price: High to Low", "name": "Name: A to Z"}
_EPOCH = datetime(1970, 1, 1, 5, 30, tzinfo=IST)


def _created(product: dict[str, Any]) -> datetime:
    value = product.get("createdAt")
    return value if isinstance(value, datetime) else _EPOCH


def _price(product: dict[str, Any]) -> float:
    return to_number(product.get("price")) or 0.0


def newest_first(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(products, key=_created, reverse=True)


def latest(products: list[dict[str, Any]], count: int = 8) -> list[dict[str, Any]]:
    return newest_first(products)[:count]


def category_counts(products: list[dict[str, Any]]) -> Counter:
    return Counter(str(p.get("category")) for p in products)


def shop_view(products: list[dict[str, Any]], names: dict[Any, str], *, category: str | None,
              search: str, sort: str) -> list[dict[str, Any]]:
    result = products
    if category:
        oid = parse_object_id(category)
        result = [p for p in result if oid is not None and p.get("category") == oid]
    if search:
        q = search.casefold()
        result = [
            p for p in result
            if q in (p.get("name") or "").casefold()
            or q in category_name(p, names, "").casefold()
            or q in (p.get("description") or "").casefold()
        ]
    if sort == "low":
        return sorted(result, key=_price)
    if sort == "high":
        return sorted(result, key=_price, reverse=True)
    if sort == "name":
        return sorted(result, key=lambda p: (p.get("name") or "").casefold())
    return newest_first(result)

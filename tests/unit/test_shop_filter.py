"""Shop filtering, search and sort (FR-UI-046, FR-UI-050, FR-UI-051) and Home latest-8 (FR-UI-037)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.services import catalog

JARS, PILLARS = ObjectId(), ObjectId()
NAMES = {JARS: "Jar Candles", PILLARS: "Pillar Candles"}
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def p(name, price, category, days, description=""):
    return {"name": name, "price": price, "category": category, "createdAt": BASE + timedelta(days=days),
            "description": description}


PRODUCTS = [p("Rose", 499, JARS, 1, "Floral soy wax"), p("vanilla", 299, PILLARS, 3), p("Amber", 899, JARS, 2)]


def names(items):
    return [i["name"] for i in items]


def test_sort_options():
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="", sort="default")) == ["vanilla", "Amber", "Rose"]
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="", sort="low")) == ["vanilla", "Rose", "Amber"]
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="", sort="high")) == ["Amber", "Rose", "vanilla"]
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="", sort="name")) == ["Amber", "Rose", "vanilla"]


def test_filter_by_category():
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=str(PILLARS), search="", sort="default")) == ["vanilla"]
    assert catalog.shop_view(PRODUCTS, NAMES, category="bogus", search="", sort="default") == []


def test_search_matches_fields_case_insensitive():
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="FLORAL", sort="name")) == ["Rose"]
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="pillar", sort="name")) == ["vanilla"]
    assert names(catalog.shop_view(PRODUCTS, NAMES, category=None, search="amb", sort="name")) == ["Amber"]


def test_latest_eight():
    many = [p(f"P{i}", 100, JARS, i) for i in range(12)]
    assert names(catalog.latest(many)) == [f"P{i}" for i in range(11, 3, -1)]


def test_category_counts():
    counts = catalog.category_counts(PRODUCTS)
    assert counts[str(JARS)] == 2 and counts[str(PILLARS)] == 1

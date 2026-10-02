"""Shop page (FR-UI-006, FR-UI-042–FR-UI-056, D-48) and add-to-cart from cards (FR-UI-059/060)."""

from __future__ import annotations

import json
import re
from datetime import timedelta

from app.core.documents import now_ist
from tests.helpers import hx, login_as, make_category, make_product


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def seed(app):
    db = app.state.db
    jars = await make_category(db, "Jar Candles")
    pillars = await make_category(db, "Pillar Candles")
    rose = await make_product(db, jars, name="Rose Jar", price=499, oldPrice=699, description="Floral soy",
                              createdAt=now_ist() - timedelta(days=2))
    vanilla = await make_product(db, pillars, name="Vanilla Pillar", price=299, stock=0)
    return jars, pillars, rose, vanilla


async def test_shop_lists_all(client, app):
    await seed(app)
    text = (await client.get("/shop")).text
    assert "Find Your Perfect Glow" in text and "Rose Jar" in text and "Vanilla Pillar" in text
    assert "All Candles" in text and "2 products found" in text


async def test_header_search_targets_shop(client, app):
    await seed(app)
    text = (await client.get("/shop?search=floral")).text
    assert 'value="floral"' in text and "Rose Jar" in text and "Vanilla Pillar" not in text


async def test_empty_search_redirects_to_shop(client):
    r = await client.get("/shop?search=")
    assert r.status_code == 303 and r.headers["location"] == "/shop"


async def test_filter_by_category(client, app):
    jars, *_ = await seed(app)
    text = (await client.get(f"/shop?category={jars['_id']}")).text
    assert "Rose Jar" in text and "Vanilla Pillar" not in text and "<h2 class=\"font-display text-2xl font-bold\">Jar Candles</h2>" in text


async def test_sidebar_links_set_category(client, app):
    jars, *_ = await seed(app)
    text = (await client.get("/shop?search=x&sort=low")).text
    assert f'hx-get="/shop?category={jars["_id"]}&amp;search=x&amp;sort=low"' in text
    assert 'data-close="#shop-drawer"' in text and 'hx-push-url="true"' in text


async def test_category_counts(client, app):
    await seed(app)
    text = (await client.get("/shop")).text
    assert text.count("1 products") == 2 and "2 products" in text


async def test_search_param_prefills_and_pushes_url(client, app):
    await seed(app)
    page = (await client.get("/shop?search=Rose")).text
    assert 'id="shop-search" name="search" type="search" value="Rose"' in page
    assert 'hx-push-url="true"' in page and 'hx-get="/shop"' in page
    r = await client.get("/shop?search=vanilla", headers={"HX-Request": "true", "HX-Target": "shop-results"})
    assert "<html" not in r.text and 'id="shop-results"' in r.text and "Vanilla Pillar" in r.text
    assert 'id="shop-categories" hx-swap-oob="true"' in r.text


async def test_heading_and_count(client, app):
    await seed(app)
    r = await client.get("/shop?sort=high", headers={"HX-Request": "true", "HX-Target": "shop-results"})
    assert "2 products found" in r.text and r.text.index("Rose Jar") < r.text.index("Vanilla Pillar")


async def test_no_candles_found(client, app):
    await seed(app)
    text = (await client.get("/shop?search=zzz")).text
    assert "No Candles Found" in text and "Try another search or category." in text and "View All Candles" in text


async def test_card_discount_badge(client, app):
    await seed(app)
    text = (await client.get("/shop")).text
    assert "29% OFF" in text and "line-through" in text


async def test_out_of_stock_card(client, app):
    await seed(app)
    text = (await client.get("/shop?search=vanilla")).text
    assert "SOLD OUT" in text and "● Out of Stock" in text and re.search(r"<button[^>]*disabled>Out of Stock</button>", text)


async def test_quantity_stepper_bounds(client, app):
    await make_product(app.state.db, name="Rose", stock=7)
    text = (await client.get("/shop")).text
    assert 'type="number" min="1" max="7" value="1"' in text and "data-stepper" in text and "7 In Stock" in text


async def test_wishlist_toggle_markup(client, app):
    product = await make_product(app.state.db)
    text = (await client.get("/shop")).text
    assert f'data-wishlist="{product["_id"]}"' in text and 'aria-pressed="false"' in text


async def test_guest_add_shows_message(client, app):
    product = await make_product(app.state.db)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "quantity": "1", "source": "shop"},
                          headers=await hx(client, app))
    assert toasts(r) == ["Please login first to add products to cart."]
    assert 'id="shop-status" hx-swap-oob="true"' in r.text and "Please login first to add products to cart." in r.text
    assert "redirectAfter" not in r.headers["HX-Trigger"]


async def test_add_success_message_and_reset(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=5)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "quantity": "3", "source": "shop"},
                          headers=await hx(client, app))
    assert toasts(r) == ["Product added to cart"] and "Add More" in r.text and 'value="1"' in r.text
    assert re.search(r'<span id="cart-badge" hx-swap-oob="true"[^>]*>3</span>', r.text)
    cart = await app.state.db.carts.find_one({"user": user["_id"]})
    assert cart["items"][0]["quantity"] == 3


async def test_add_over_stock_error(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=2)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "quantity": "3", "source": "shop"},
                          headers=await hx(client, app))
    assert toasts(r) == ["Only 2 items available"]

"""Home page and its independently loaded sections (FR-UI-030–FR-UI-040, D-46)."""

from __future__ import annotations

import json
from datetime import timedelta

from app.core.documents import new_meta, utcnow
from tests.helpers import hx, make_category, make_product

HX = {"HX-Request": "true"}


async def seed_banner(db, title, order=0, **kw):
    doc = {"title": title, "subtitle": kw.pop("subtitle", ""), "image": f"/uploads/{title or 'x'}.png", "buttonText": kw.pop("buttonText", ""),
           "buttonLink": kw.pop("buttonLink", "/shop"), "order": order, "status": kw.pop("status", True), **new_meta(), **kw}
    await db.banners.insert_one(doc)


async def test_home_shell_and_partials_load(client):
    text = (await client.get("/")).text
    for path in ("/_p/home/banners", "/_p/home/promo-cards", "/_p/home/categories", "/_p/home/products"):
        assert f'hx-get="{path}"' in text
        assert (await client.get(path, headers=HX)).status_code == 200
    assert "youtube.com/embed/dJJCayBThvY" in text and "Join Our Candle Making Community" in text


async def test_banner_slider_markup(client, app):
    await seed_banner(app.state.db, "Second", order=1)
    await seed_banner(app.state.db, "First", order=0, subtitle="Up to 30% off")
    text = (await client.get("/_p/home/banners", headers=HX)).text
    assert 'data-slider data-interval="4000"' in text
    assert text.index("First") < text.index("Second") and "Up to 30% off" in text
    assert text.count("data-slider-dot=") == 2 and "data-slider-prev" in text and "data-slider-next" in text


async def test_single_banner_has_no_arrows(client, app):
    await seed_banner(app.state.db, "Only")
    text = (await client.get("/_p/home/banners", headers=HX)).text
    assert "data-slider-prev" not in text


async def test_no_banners_message(client, app):
    await seed_banner(app.state.db, "Hidden", status=False)
    text = (await client.get("/_p/home/banners", headers=HX)).text
    assert "No banners available" in text


async def test_banner_cta_requires_title(client, app):
    await seed_banner(app.state.db, "", buttonText="Go")
    await seed_banner(app.state.db, "Titled", order=1, buttonText="", buttonLink="https://example.com/sale")
    text = (await client.get("/_p/home/banners", headers=HX)).text
    assert ">Go" not in text and "Shop Now" in text and 'href="https://example.com/sale"' in text
    assert 'alt="Candle banner 1"' in text


async def test_mid_page_banner(client, app):
    await seed_banner(app.state.db, "First", buttonLink="javascript:alert(1)")
    text = (await client.get("/_p/home/banners", headers=HX)).text
    assert 'id="home-mid-banner" hx-swap-oob="true"' in text and "javascript:" not in text and 'href="/shop"' in text


async def test_promo_cards_render_with_defaults(client, app):
    await app.state.db.promocards.insert_one({"title": "Gift Sets", "subtitle": "Perfect for Diwali", "image": "/uploads/g.png",
                                               "buttonText": "", "buttonLink": "/shop?category=1", "background": "",
                                               "order": 0, "status": True, **new_meta()})
    text = (await client.get("/_p/home/promo-cards", headers=HX)).text
    assert "background-color: #08aaa6" in text and "Shop Now" in text and 'href="/shop?category=1"' in text


async def test_category_tiles_link_to_shop(client, app):
    cat = await make_category(app.state.db, "Jar Candles")
    text = (await client.get("/_p/home/categories", headers=HX)).text
    assert f'href="/shop?category={cat["_id"]}"' in text and "Jar Candles" in text


async def test_latest_eight_products(client, app):
    cat = await make_category(app.state.db)
    for i in range(10):
        await make_product(app.state.db, cat, name=f"Candle {i:02d}",
                           createdAt=utcnow() - timedelta(days=10 - i), updatedAt=utcnow())
    text = (await client.get("/_p/home/products", headers=HX)).text
    assert text.count("<article") == 8 and "Candle 09" in text and "Candle 01" not in text and "Candle 00" not in text


async def test_sections_empty_messages(client):
    assert "No categories available yet." in (await client.get("/_p/home/categories", headers=HX)).text
    assert "No products available yet." in (await client.get("/_p/home/products", headers=HX)).text


async def test_section_error_with_retry(client, app, monkeypatch):
    from pymongo.errors import PyMongoError

    from app.services import category_service

    async def boom(db):
        raise PyMongoError("down")

    monkeypatch.setattr(category_service, "list_all", boom)
    r = await client.get("/_p/home/categories", headers=HX)
    assert r.status_code == 200 and "Unable to load categories" in r.text and "Retry" in r.text
    assert json.loads(r.headers["HX-Trigger"])["toast"]["items"][0]["message"] == "Unable to load categories"
    assert (await client.get("/_p/home/banners", headers=HX)).status_code == 200  # other sections unaffected


async def test_home_card_badges(client, app):
    await make_product(app.state.db, name="Sale", price=499, oldPrice=699, stock=0)
    text = (await client.get("/_p/home/products", headers=HX)).text
    assert "Save 29%" in text and "Sold Out" in text and "Out of Stock" in text and "₹699" in text


async def test_guest_add_to_cart_redirects_to_login(client, app):
    product = await make_product(app.state.db)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "quantity": "1", "source": "home"},
                          headers=await hx(client, app))
    trigger = json.loads(r.headers["HX-Trigger"])
    assert trigger["toast"]["items"][0]["message"] == "Please login first to add products to cart"
    assert trigger["redirectAfter"] == {"url": "/login?redirect=%2F", "delay": 1000}
    assert "Please login first" in r.text

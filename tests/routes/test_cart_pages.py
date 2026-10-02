"""Cart page and HTMX actions (FR-UI-029, FR-UI-057–FR-UI-067, D-47)."""

from __future__ import annotations

import json
import re

from bson import ObjectId

from app.core.documents import new_meta
from tests.helpers import hx, login_as, make_product


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def seed_cart(app, user, *lines):
    await app.state.db.carts.insert_one({"user": user["_id"], "items": list(lines), **new_meta()})


async def test_guest_sees_login_panel(client):
    r = await client.get("/cart")
    assert r.status_code == 200 and "Please Login" in r.text
    assert 'href="/login?redirect=%2Fcart"' in r.text and 'href="/register"' in r.text


async def test_empty_cart_state(client, app):
    await login_as(client, app)
    r = await client.get("/cart")
    assert "Your Cart Is Empty" in r.text and "Add your favourite candles to continue." in r.text and 'href="/shop"' in r.text


async def test_cart_belongs_to_user(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, name="Rose Jar")
    await seed_cart(app, user, {"product": product["_id"], "quantity": 2, "selected": True})
    assert "Rose Jar" in (await client.get("/cart")).text
    client.cookies.clear()
    await login_as(client, app)
    assert "Rose Jar" not in (await client.get("/cart")).text


async def test_lines_show_unit_and_item_total(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, name="Rose Jar", price=499)
    await seed_cart(app, user, {"product": product["_id"], "quantity": 3, "selected": True})
    text = (await client.get("/cart")).text
    assert "Unit Price:" in text and "₹499" in text and "Item Total:" in text and "₹1,497" in text
    assert "3 item(s) selected" in text


async def test_missing_product_lines_hidden_and_pruned(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, name="Rose Jar")
    await seed_cart(app, user, {"product": product["_id"], "quantity": 1, "selected": True},
                    {"product": ObjectId(), "quantity": 4, "selected": True})
    text = (await client.get("/cart")).text
    assert "1 item(s) selected" in text
    cart = await app.state.db.carts.find_one({"user": user["_id"]})
    assert [i["product"] for i in cart["items"]] == [product["_id"]]


async def test_quantity_buttons_bounds(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=2)
    await seed_cart(app, user, {"product": product["_id"], "quantity": 1, "selected": True})
    text = (await client.get("/cart")).text
    dec = re.search(r'<button[^>]*aria-label="Decrease quantity"', text, re.S).group(0)
    assert "disabled" in dec
    await app.state.db.carts.update_one({"user": user["_id"]}, {"$set": {"items.0.quantity": 2}})
    inc = re.search(r'<button[^>]*aria-label="Increase quantity"', (await client.get("/cart")).text, re.S).group(0)
    assert "disabled" in inc


async def test_quantity_update(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=5, price=100)
    await seed_cart(app, user, {"product": product["_id"], "quantity": 1, "selected": True})
    r = await client.put(f"/cart/items/{product['_id']}", data={"quantity": "3"}, headers=await hx(client, app))
    assert r.status_code == 200 and 'id="cart-summary" class="card card-pad" hx-swap-oob="true"' in r.text
    assert 'id="cart-badge"' in r.text and "₹300" in r.text and "3 item(s) selected" in r.text


async def test_quantity_over_stock_shows_toast(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=2)
    await seed_cart(app, user, {"product": product["_id"], "quantity": 2, "selected": True})
    r = await client.put(f"/cart/items/{product['_id']}", data={"quantity": "3"}, headers=await hx(client, app))
    assert r.status_code == 200 and toasts(r) == ["Only 2 items available"]


async def test_remove_line(client, app):
    user = await login_as(client, app)
    a = await make_product(app.state.db, name="A")
    b = await make_product(app.state.db, name="B")
    await seed_cart(app, user, {"product": a["_id"], "quantity": 1, "selected": True},
                    {"product": b["_id"], "quantity": 1, "selected": True})
    r = await client.delete(f"/cart/items/{a['_id']}", headers=await hx(client, app))
    assert r.status_code == 200 and "HX-Retarget" not in r.headers
    r = await client.delete(f"/cart/items/{b['_id']}", headers=await hx(client, app))
    assert r.headers["HX-Retarget"] == "#cart-root" and "Your Cart Is Empty" in r.text


async def test_selection_changes_totals(client, app):
    user = await login_as(client, app)
    a = await make_product(app.state.db, name="A", price=600)
    b = await make_product(app.state.db, name="B", price=600)
    await seed_cart(app, user, {"product": a["_id"], "quantity": 1, "selected": True},
                    {"product": b["_id"], "quantity": 1, "selected": True})
    assert "FREE delivery applied" in (await client.get("/cart")).text
    r = await client.put(f"/cart/items/{a['_id']}/selected", data={}, headers=await hx(client, app))
    assert "1 item(s) selected" in r.text and "Pay Separately" in r.text and "Add ₹499 more to get FREE delivery" in r.text
    r = await client.put("/cart/selection", data={"selected": "true"}, headers=await hx(client, app))
    assert "2 item(s) selected" in r.text


async def test_delivery_messages(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, price=1099)
    await seed_cart(app, user, {"product": product["_id"], "quantity": 1, "selected": True})
    text = (await client.get("/cart")).text
    assert "🎉 FREE delivery applied" in text and "Your order value is ₹1,099 or above." in text
    await app.state.db.products.update_one({"_id": product["_id"]}, {"$set": {"price": 1000}})
    text = (await client.get("/cart")).text
    assert "Delivery charges not included" in text and "*Grand Total does not include delivery charge." in text


async def test_add_out_of_stock_message(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=0)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "source": "shop"}, headers=await hx(client, app))
    assert toasts(r) == ["This product is out of stock."]
    assert await app.state.db.carts.count_documents({"items.0": {"$exists": True}}) == 0


async def test_add_updates_badge(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=9)
    r = await client.post("/cart/add", data={"product_id": str(product["_id"]), "quantity": "2", "source": "home"},
                          headers=await hx(client, app))
    assert re.search(r'<span id="cart-badge" hx-swap-oob="true"[^>]*>2</span>', r.text)
    assert "Product added to cart" in r.text  # card message on Home


async def test_cart_actions_require_login_and_csrf(client, app):
    r = await client.put(f"/cart/items/{ObjectId()}", data={"quantity": "1"}, headers=await hx(client, app, current_url="/cart"))
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login?redirect=%2Fcart"
    await login_as(client, app)
    r = await client.put(f"/cart/items/{ObjectId()}", data={"quantity": "1"}, headers={"HX-Request": "true"})
    assert r.status_code == 403

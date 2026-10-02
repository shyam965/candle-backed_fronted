"""`/api/cart/*` (FR-065–FR-080, D-28)."""

from __future__ import annotations

import asyncio

from bson import ObjectId

from app.core.documents import new_meta
from tests.helpers import API_ORIGIN, login_as, make_product


async def call(client, method, path, json=None):
    return await client.request(method, "/api/cart" + path, json=json, headers=API_ORIGIN)


async def test_requires_auth(client):
    for method, path in (("GET", ""), ("POST", "/add"), ("PUT", "/update"), ("DELETE", "/remove/x"),
                         ("PUT", "/toggle"), ("PUT", "/select-all"), ("DELETE", "/clear")):
        r = await call(client, method, path, {})
        assert r.status_code == 401 and r.json()["message"] == "Please login first", path


async def test_get_creates_empty_cart(client, app):
    user = await login_as(client, app)
    r = await call(client, "GET", "")
    body = r.json()
    assert r.status_code == 200 and body["success"] is True and body["cart"]["items"] == []
    assert body["cart"]["user"] == str(user["_id"]) and body["cart"]["__v"] == 0
    await call(client, "GET", "")
    assert await app.state.db.carts.count_documents({}) == 1


async def test_add_missing_product_id(client, app):
    await login_as(client, app)
    r = await call(client, "POST", "/add", {})
    assert r.status_code == 400 and r.json() == {"success": False, "message": "Product ID is required"}


async def test_add_unknown_product(client, app):
    await login_as(client, app)
    r = await call(client, "POST", "/add", {"productId": str(ObjectId())})
    assert r.status_code == 404 and r.json()["message"] == "Product not found"


async def test_add_invalid_id_400(client, app):
    await login_as(client, app)
    assert (await call(client, "POST", "/add", {"productId": "abc"})).status_code == 400


async def test_add_default_quantity(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=5)
    body = (await call(client, "POST", "/add", {"productId": str(product["_id"])})).json()
    assert body["message"] == "Product added to cart"
    line = body["cart"]["items"][0]
    assert line["quantity"] == 1 and line["selected"] is True and line["product"]["_id"] == str(product["_id"])
    assert line["product"]["name"] == product["name"]


async def test_add_quantity_rules(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=5)
    for qty in (0, -1, "0"):
        r = await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": qty})
        assert r.status_code == 400 and r.json()["message"] == "Quantity must be at least 1"
    for qty in ("abc", 1.5):
        assert (await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": qty})).status_code == 400


async def test_add_exceeds_stock(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=5)
    r = await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": 6})
    assert r.status_code == 400 and r.json()["message"] == "Only 5 items available"


async def test_add_existing_line_increments_and_selects(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=5)
    await app.state.db.carts.insert_one({"user": user["_id"], "items": [
        {"product": product["_id"], "quantity": 2, "selected": False}], **new_meta()})
    body = (await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": "3"})).json()
    assert body["cart"]["items"][0]["quantity"] == 5 and body["cart"]["items"][0]["selected"] is True
    assert body["cart"]["__v"] == 1
    r = await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": 1})
    assert r.status_code == 400 and r.json()["message"] == "Only 5 items available"


async def test_version_increments(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=9)
    await call(client, "POST", "/add", {"productId": str(product["_id"])})
    body = (await call(client, "POST", "/add", {"productId": str(product["_id"])})).json()
    assert body["cart"]["__v"] == 2 and body["cart"]["updatedAt"] >= body["cart"]["createdAt"]


async def test_update_invalid_data(client, app):
    await login_as(client, app)
    for body in ({"quantity": 2}, {"productId": "x", "quantity": 0}, {"productId": "x"}, {"productId": "x", "quantity": "abc"}):
        r = await call(client, "PUT", "/update", body)
        assert r.status_code == 400 and r.json()["message"] == "Invalid cart data", body


async def test_update_line_not_found(client, app):
    await login_as(client, app)
    r = await call(client, "PUT", "/update", {"productId": str(ObjectId()), "quantity": 1})
    assert r.status_code == 404 and r.json()["message"] == "Product not found in cart"


async def test_update_sets_quantity(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=4)
    await call(client, "POST", "/add", {"productId": str(product["_id"]), "quantity": 2})
    body = (await call(client, "PUT", "/update", {"productId": str(product["_id"]), "quantity": 3})).json()
    assert body["message"] == "Cart updated" and body["cart"]["items"][0]["quantity"] == 3
    r = await call(client, "PUT", "/update", {"productId": str(product["_id"]), "quantity": 5})
    assert r.status_code == 400 and r.json()["message"] == "Only 4 items available"


async def test_remove_line(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db)
    await call(client, "POST", "/add", {"productId": str(product["_id"])})
    body = (await call(client, "DELETE", f"/remove/{product['_id']}")).json()
    assert body["message"] == "Product removed" and body["cart"]["items"] == []


async def test_remove_absent_line_ok(client, app):
    await login_as(client, app)
    r = await call(client, "DELETE", f"/remove/{ObjectId()}")
    assert r.status_code == 200 and r.json()["cart"]["items"] == []
    assert (await call(client, "DELETE", "/remove/not-an-id")).status_code == 200


async def test_toggle(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db)
    pid = str(product["_id"])
    await call(client, "POST", "/add", {"productId": pid})
    for value, expected in ((False, False), (None, True), ("false", False), ("true", True)):
        payload = {"productId": pid} if value is None else {"productId": pid, "selected": value}
        body = (await call(client, "PUT", "/toggle", payload)).json()
        assert body["message"] == "Selection updated" and body["cart"]["items"][0]["selected"] is expected, value


async def test_toggle_missing_line_404(client, app):
    await login_as(client, app)
    r = await call(client, "PUT", "/toggle", {"productId": str(ObjectId()), "selected": False})
    assert r.status_code == 404 and r.json()["message"] == "Product not found in cart"


async def test_select_all(client, app):
    await login_as(client, app)
    for name in ("A", "B"):
        product = await make_product(app.state.db, name=name)
        await call(client, "POST", "/add", {"productId": str(product["_id"])})
    body = (await call(client, "PUT", "/select-all", {"selected": False})).json()
    assert [i["selected"] for i in body["cart"]["items"]] == [False, False]


async def test_clear(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db)
    await call(client, "POST", "/add", {"productId": str(product["_id"])})
    body = (await call(client, "DELETE", "/clear")).json()
    assert body["message"] == "Cart cleared" and body["cart"]["items"] == []


async def test_populated_and_missing_product(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db)
    await app.state.db.carts.insert_one({"user": user["_id"], "items": [
        {"product": product["_id"], "quantity": 1, "selected": True},
        {"product": ObjectId(), "quantity": 1, "selected": True}], **new_meta()})
    items = (await call(client, "GET", "")).json()["cart"]["items"]
    assert items[0]["product"]["price"] == product["price"] and items[1]["product"] is None


async def test_concurrent_get_single_cart(client, app):
    await login_as(client, app)
    responses = await asyncio.gather(*[call(client, "GET", "") for _ in range(8)])
    assert all(r.status_code == 200 for r in responses)
    assert await app.state.db.carts.count_documents({}) == 1


async def test_other_users_cart_untouched(client, app):
    other = await login_as(client, app)
    product = await make_product(app.state.db)
    await call(client, "POST", "/add", {"productId": str(product["_id"])})
    client.cookies.clear()
    await login_as(client, app)
    assert (await call(client, "GET", "")).json()["cart"]["items"] == []
    assert (await app.state.db.carts.find_one({"user": other["_id"]}))["items"]

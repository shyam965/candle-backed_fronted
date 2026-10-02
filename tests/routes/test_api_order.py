"""`/api/order/*` (FR-081–FR-103, D-29, D-30)."""

from __future__ import annotations

from bson import ObjectId

from app.core.documents import new_meta
from tests.helpers import API_ORIGIN, login_as, make_order, make_product, make_user

CUSTOMER = {"name": " Asha Verma ", "mobile": "9876543210", "address": "12 MG Road", "city": "Jaipur",
            "pincode": "302001", "message": " Please gift wrap "}


async def create(client, body):
    return await client.post("/api/order/create", json=body, headers=API_ORIGIN)


def payload(product, **kw):
    body = {"customer": CUSTOMER, "items": [{"productId": str(product["_id"]), "name": "Anything", "price": 1, "quantity": 2,
                                             "total": 2}], "itemsTotal": 2, "shipping": 0, "shippingStatus": "FREE",
            "grandTotal": 2, "paymentMethod": "Cash"}
    body.update(kw)
    return body


async def test_create_requires_auth(client):
    assert (await create(client, {})).status_code == 401


async def test_create_incomplete_customer(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db)
    for customer in (None, {**CUSTOMER, "city": ""}, {**CUSTOMER, "mobile": 9876543210}):
        r = await create(client, payload(product, customer=customer))
        assert r.status_code == 400 and r.json()["message"] == "Please provide complete customer details", customer
    r = await create(client, payload(product, customer={**CUSTOMER, "pincode": "12"}))
    assert r.status_code == 400 and r.json()["message"] == "Please enter a valid 6 digit pincode."


async def test_create_no_items(client, app):
    await login_as(client, app)
    for items in (None, [], "x"):
        r = await create(client, {"customer": CUSTOMER, "items": items})
        assert r.status_code == 400 and r.json()["message"] == "At least one product is required"


async def test_create_invalid_item(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db)
    for item in ({"name": "x", "quantity": 1}, {"productId": str(product["_id"]), "quantity": 1},
                 {"productId": str(product["_id"]), "name": "x", "quantity": 0},
                 {"productId": str(product["_id"]), "name": "x", "quantity": "abc"}):
        r = await create(client, {"customer": CUSTOMER, "items": [item]})
        assert r.status_code == 400 and r.json()["message"] == "Invalid order product data", item


async def test_create_unknown_product(client, app):
    await login_as(client, app)
    r = await create(client, {"customer": CUSTOMER, "items": [{"productId": str(ObjectId()), "name": "x", "quantity": 1}]})
    assert r.status_code == 400 and "no longer available" in r.json()["message"]


async def test_create_accepts_product_or_product_id(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, stock=10)
    r = await create(client, {"customer": CUSTOMER, "items": [{"product": str(product["_id"]), "name": "x", "quantity": 1}]})
    assert r.status_code == 201


async def test_client_totals_ignored(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, name="Rose Jar", price=499, stock=10)
    order = (await create(client, payload(product))).json()["order"]
    assert order["items"][0]["price"] == 499 and order["items"][0]["total"] == 998 and order["items"][0]["name"] == "Rose Jar"
    assert order["itemsTotal"] == 998 and order["grandTotal"] == 998 and order["shipping"] == 0
    assert order["paymentMethod"] == "WhatsApp Order"


async def test_client_shipping_status_ignored(client, app):
    await login_as(client, app)
    product = await make_product(app.state.db, price=100, stock=10)
    order = (await create(client, payload(product, shippingStatus="BOGUS"))).json()["order"]
    assert order["shippingStatus"] == "PAYABLE_SEPARATELY"


async def test_create_response_populated(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=10)
    r = await create(client, payload(product))
    body = r.json()
    assert r.status_code == 201 and body["message"] == "Order created successfully"
    order = body["order"]
    assert order["user"]["_id"] == str(user["_id"]) and "password" not in order["user"]
    assert order["items"][0]["product"]["_id"] == str(product["_id"])
    assert order["customer"]["name"] == "Asha Verma" and order["customer"]["message"] == "Please gift wrap"
    assert order["orderId"].startswith("AKRF-") and order["status"] == "Pending"


async def test_create_removes_ordered_lines(client, app):
    user = await login_as(client, app)
    product = await make_product(app.state.db, stock=10)
    await app.state.db.carts.insert_one({"user": user["_id"], "items": [
        {"product": product["_id"], "quantity": 3, "selected": False}], **new_meta()})
    await create(client, payload(product))
    cart = await app.state.db.carts.find_one({"user": user["_id"]})
    assert cart["items"][0]["quantity"] == 1


async def test_populated_user_has_no_password(client, app):
    await login_as(client, app, role="admin")
    await make_order(app.state.db, await make_user(app.state.db))
    assert "password" not in (await client.get("/api/order/all")).text


async def test_my_orders_own_newest_first(client, app):
    user = await login_as(client, app)
    old = await make_order(app.state.db, user, created_offset_minutes=10)
    new = await make_order(app.state.db, user)
    await make_order(app.state.db, await make_user(app.state.db))
    body = (await client.get("/api/order/my-orders")).json()
    assert body["success"] is True and [o["_id"] for o in body["orders"]] == [str(new["_id"]), str(old["_id"])]
    assert body["orders"][0]["user"] == str(user["_id"])


async def test_detail_owner_only(client, app):
    user = await login_as(client, app)
    mine = await make_order(app.state.db, user)
    theirs = await make_order(app.state.db, await make_user(app.state.db))
    assert (await client.get(f"/api/order/my-orders/{mine['_id']}")).json()["order"]["orderId"] == mine["orderId"]
    r = await client.get(f"/api/order/my-orders/{theirs['_id']}")
    assert r.status_code == 404 and r.json() == {"success": False, "message": "Order not found"}


async def test_detail_invalid_id_404(client, app):
    await login_as(client, app)
    assert (await client.get("/api/order/my-orders/abc")).status_code == 404


async def test_all_admin_only(client, app):
    assert (await client.get("/api/order/all")).status_code == 401
    await login_as(client, app)
    r = await client.get("/api/order/all")
    assert r.status_code == 403 and r.json()["message"] == "Admin access required"
    client.cookies.clear()
    await login_as(client, app, role="admin")
    await make_order(app.state.db, await make_user(app.state.db, name="Ravi"))
    orders = (await client.get("/api/order/all")).json()["orders"]
    assert orders[0]["user"]["name"] == "Ravi"


async def test_status_requires_admin(client, app):
    order = await make_order(app.state.db, await make_user(app.state.db))
    await login_as(client, app)
    r = await client.put(f"/api/order/status/{order['_id']}", json={"status": "Confirmed"}, headers=API_ORIGIN)
    assert r.status_code == 403


async def test_status_invalid_value(client, app):
    await login_as(client, app, role="admin")
    order = await make_order(app.state.db, await make_user(app.state.db))
    for status in (None, "shipped", "Lost"):
        r = await client.put(f"/api/order/status/{order['_id']}", json={"status": status}, headers=API_ORIGIN)
        assert r.status_code == 400 and r.json()["message"] == "Invalid order status"


async def test_status_order_not_found(client, app):
    await login_as(client, app, role="admin")
    r = await client.put(f"/api/order/status/{ObjectId()}", json={"status": "Confirmed"}, headers=API_ORIGIN)
    assert r.status_code == 404 and r.json()["message"] == "Order not found"


async def test_status_invalid_id_400(client, app):
    await login_as(client, app, role="admin")
    r = await client.put("/api/order/status/abc", json={"status": "Confirmed"}, headers=API_ORIGIN)
    assert r.status_code == 400


async def test_status_response_shape(client, app):
    await login_as(client, app, role="admin")
    order = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.put(f"/api/order/status/{order['_id']}", json={"status": "Shipped"}, headers=API_ORIGIN)
    body = r.json()
    assert body["success"] is True and body["message"] == "Order status changed to Shipped"
    assert body["order"]["status"] == "Shipped" and body["order"]["statusDates"]["Shipped"]
    assert body["order"]["statusDates"]["Pending"] and body["order"]["statusDates"]["Confirmed"] is None
    assert isinstance(body["order"]["user"], dict)


async def test_status_invalid_transition_400(client, app):
    await login_as(client, app, role="admin")
    order = await make_order(app.state.db, await make_user(app.state.db), status="Delivered")
    r = await client.put(f"/api/order/status/{order['_id']}", json={"status": "Pending"}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Cannot change order status from Delivered to Pending"


async def test_cancel_via_api(client, app):
    await login_as(client, app, role="admin")
    order = await make_order(app.state.db, await make_user(app.state.db))
    body = (await client.put(f"/api/order/status/{order['_id']}", json={"status": "Cancelled"}, headers=API_ORIGIN)).json()
    assert body["order"]["expectedDelivery"] is None and body["order"]["statusDates"]["Cancelled"]

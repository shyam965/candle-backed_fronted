"""WhatsApp checkout flow (FR-UI-068–FR-UI-083, D-39)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from app.core.documents import new_meta
from app.security.sessions import hash_token
from tests.helpers import hx, login_as, make_product

DELIVERY = {"name": "Asha Verma", "mobile": "9876543210", "address": "12 MG Road", "city": "Jaipur", "pincode": "302001",
            "message": "Gift wrap"}


def trigger(r):
    return json.loads(r.headers.get("HX-Trigger", "{}"))


def toasts(r):
    return [t["message"] for t in trigger(r).get("toast", {}).get("items", [])]


async def setup_cart(client, app, *, price=499, qty=2, stock=10, selected=True, **user_kw):
    user = await login_as(client, app, **user_kw)
    product = await make_product(app.state.db, name="Rose Jar", price=price, stock=stock)
    await app.state.db.carts.insert_one({"user": user["_id"], "items": [
        {"product": product["_id"], "quantity": qty, "selected": selected}], **new_meta()})
    return user, product


async def session_doc(client, app):
    return await app.state.db.sessions.find_one({"_id": hash_token(client.cookies.get("akrf_session"))})


async def test_checkout_requires_login(client, app):
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app, current_url="/cart"))
    assert r.status_code == 401 and r.headers["HX-Redirect"] == "/login?redirect=%2Fcart"


async def test_delivery_form_prefilled_from_user(client, app):
    await setup_cart(client, app, name="Ravi", phone="9123456789", address="5 Park St", city="Delhi", pincode="110001")
    text = (await client.get("/cart")).text
    for value in ('value="Ravi"', 'value="9123456789"', ">5 Park St</textarea>", 'value="Delhi"', 'value="110001"'):
        assert value in text


async def test_inputs_restricted(client, app):
    await setup_cart(client, app)
    text = (await client.get("/cart")).text
    assert 'data-digits="10"' in text and 'data-digits="6"' in text and 'maxlength="10"' in text


async def test_delivery_validation_messages(client, app):
    await setup_cart(client, app)
    r = await client.post("/cart/checkout", data={"name": "", "mobile": "12345", "address": "", "city": "", "pincode": "1"},
                          headers=await hx(client, app))
    assert r.status_code == 422
    for message in ("Please enter your full name.", "Please enter a valid 10 digit mobile number.",
                    "Please enter your complete address.", "Please enter your city.", "Please enter a valid 6 digit pincode."):
        assert message in r.text
    assert 'aria-invalid="true"' in r.text and 'id="customer-details"' in r.text


async def test_no_selected_items(client, app):
    await setup_cart(client, app, selected=False)
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Please select at least one product."]


async def test_checkout_stores_pending_order_in_session(client, app):
    _, product = await setup_cart(client, app, price=499, qty=2)
    r = await client.post("/cart/checkout", data={**DELIVERY, "mobile": "98765 43210"}, headers=await hx(client, app))
    assert r.status_code == 422  # mobile must be 10 digits (client strips non-digits)
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    pending = (await session_doc(client, app))["pendingOrder"]
    assert pending["customer"]["name"] == "Asha Verma" and pending["itemsTotal"] == 998
    assert pending["shippingStatus"] == "PAYABLE_SEPARATELY" and pending["grandTotal"] == 998 and pending["shipping"] == 0
    assert pending["items"][0]["product"] == product["_id"] and pending["items"][0]["total"] == 998
    assert (await app.state.db.orders.count_documents({})) == 0  # nothing saved yet


async def test_checkout_redirects_to_confirm(client, app):
    await setup_cart(client, app)
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == "/whatsapp-confirm"


async def test_checkout_triggers_open_whatsapp(client, app):
    await setup_cart(client, app, price=1200, qty=1)
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    url = urlsplit(trigger(r)["openWhatsApp"]["url"])
    text = parse_qs(url.query)["text"][0]
    pending = (await session_doc(client, app))["pendingOrder"]
    assert url.netloc == "wa.me" and url.path == "/919288245292"
    assert f"Order ID: {pending['orderId']}" in text and "*FREE DELIVERY:*" in text and "Gift wrap" in text


async def test_checkout_stock_changed(client, app):
    await setup_cart(client, app, qty=5, stock=3)
    r = await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Only 3 items available for Rose Jar"]


async def test_cart_shows_pending_banner(client, app):
    await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    text = (await client.get("/cart")).text
    assert "You have a pending WhatsApp order" in text and 'href="/whatsapp-confirm"' in text
    assert "visibilitychange" not in text
    r = await client.delete("/cart/pending-order", headers=await hx(client, app))
    assert r.status_code == 200 and (await session_doc(client, app))["pendingOrder"] is None


async def test_confirm_anonymous_redirects(client):
    r = await client.get("/whatsapp-confirm")
    assert r.status_code == 303 and r.headers["location"] == "/login?redirect=%2Fwhatsapp-confirm"


async def test_confirm_without_pending_redirects_to_cart(client, app):
    await login_as(client, app)
    r = await client.get("/whatsapp-confirm")
    assert r.status_code == 303 and r.headers["location"] == "/cart"
    assert "No pending WhatsApp order found." in (await client.get("/cart")).text


async def test_confirm_invalid_pending_cleared(client, app):
    await login_as(client, app)
    await app.state.db.sessions.update_one({"_id": hash_token(client.cookies.get("akrf_session"))},
                                           {"$set": {"pendingOrder": {"items": []}}})
    r = await client.get("/whatsapp-confirm")
    assert r.headers["location"] == "/cart" and (await session_doc(client, app))["pendingOrder"] is None
    assert "Pending order data is invalid." in (await client.get("/cart")).text


async def test_confirm_page_shows_details(client, app):
    await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    text = (await client.get("/whatsapp-confirm")).text
    for part in ("WhatsApp Order", "Did you send the WhatsApp message?", "Asha Verma", "302001", "Rose Jar", "Qty: 2",
                 "₹998", "Pay Separately", "I Have Sent WhatsApp Order", "I Haven't Sent It",
                 "Your cart will be updated only after the order is successfully confirmed."):
        assert part in text, part


async def test_send_again_link_contains_order_id(client, app):
    await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    pending = (await session_doc(client, app))["pendingOrder"]
    text = (await client.get("/whatsapp-confirm")).text
    assert "https://api.whatsapp.com/send?phone=919288245292&amp;text=" in text and pending["orderId"] in text


async def test_confirm_buttons_busy_markup(client, app):
    await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    text = (await client.get("/whatsapp-confirm")).text
    assert "Placing Order..." in text and 'hx-disabled-elt="#confirm-actions button, #confirm-actions a"' in text


async def test_confirm_creates_order(client, app):
    user, product = await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    pending = (await session_doc(client, app))["pendingOrder"]
    r = await client.post("/whatsapp-confirm", headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == "/my-orders"
    order = await app.state.db.orders.find_one({"user": user["_id"]})
    assert order["orderId"] == pending["orderId"] and order["grandTotal"] == 998 and order["customer"]["message"] == "Gift wrap"
    assert order["items"][0]["product"] == product["_id"] and order["paymentMethod"] == "WhatsApp Order"


async def test_confirm_success_flow(client, app):
    user, _ = await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    await client.post("/whatsapp-confirm", headers=await hx(client, app))
    assert (await session_doc(client, app))["pendingOrder"] is None
    assert (await app.state.db.carts.find_one({"user": user["_id"]}))["items"] == []
    assert "Order placed successfully!" in (await client.get("/about")).text


async def test_confirm_clears_ordered_lines_only(client, app):
    user, product = await setup_cart(client, app)
    other = await make_product(app.state.db, name="Other")
    await app.state.db.carts.update_one({"user": user["_id"]}, {"$push": {"items": {"product": other["_id"], "quantity": 1,
                                                                                     "selected": False}}})
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    await client.post("/whatsapp-confirm", headers=await hx(client, app))
    cart = await app.state.db.carts.find_one({"user": user["_id"]})
    assert [i["product"] for i in cart["items"]] == [other["_id"]]


async def test_confirm_failure_keeps_pending(client, app):
    _, product = await setup_cart(client, app, qty=2, stock=5)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    await app.state.db.products.update_one({"_id": product["_id"]}, {"$set": {"stock": 1}})
    r = await client.post("/whatsapp-confirm", headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Only 1 items available for Rose Jar"]
    assert (await session_doc(client, app))["pendingOrder"] is not None
    assert await app.state.db.orders.count_documents({}) == 0


async def test_pending_order_cleared_on_logout(client, app):
    await setup_cart(client, app)
    await client.post("/cart/checkout", data=DELIVERY, headers=await hx(client, app))
    await client.post("/logout", headers=await hx(client, app))
    assert await app.state.db.sessions.count_documents({"pendingOrder": {"$ne": None}}) == 0

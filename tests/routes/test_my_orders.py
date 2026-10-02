"""My Orders and Order Details pages (FR-093/094, FR-UI-027, FR-UI-084–FR-UI-093)."""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId

from app.core.documents import utcnow
from tests.helpers import login_as, make_order, make_product, make_user

HX = {"HX-Request": "true"}


async def test_anonymous_redirects_to_login(client):
    r = await client.get("/my-orders")
    assert r.status_code == 303 and r.headers["location"] == "/login?redirect=%2Fmy-orders"


async def test_page_shell(client, app):
    await login_as(client, app, name="Ravi")
    text = (await client.get("/my-orders")).text
    assert "Welcome, Ravi" in text and "Loading orders..." in text and 'hx-get="/my-orders/_list"' in text


async def test_no_orders_state(client, app):
    await login_as(client, app)
    text = (await client.get("/my-orders/_list", headers=HX)).text
    assert "No Orders Yet" in text and "Your WhatsApp orders will appear here." in text and "Start Shopping" in text


async def test_error_state_with_retry(client, app, monkeypatch):
    from pymongo.errors import PyMongoError

    from app.services import order_service

    async def boom(db, user):
        raise PyMongoError("down")

    monkeypatch.setattr(order_service, "list_for_user", boom)
    await login_as(client, app)
    r = await client.get("/my-orders/_list", headers=HX)
    assert "Unable to load orders" in r.text and "Retry" in r.text and "No Orders Yet" not in r.text


async def test_lists_only_own_orders(client, app):
    user = await login_as(client, app)
    old = await make_order(app.state.db, user, created_offset_minutes=60)
    new = await make_order(app.state.db, user)
    other = await make_order(app.state.db, await make_user(app.state.db))
    text = (await client.get("/my-orders/_list", headers=HX)).text
    assert "2 Order(s)" in text and other["orderId"] not in text
    assert text.index(new["orderId"]) < text.index(old["orderId"])


async def test_order_card_contents(client, app):
    user = await login_as(client, app)
    products = [await make_product(app.state.db, name=f"Candle {i}", price=100) for i in range(4)]
    order = await make_order(app.state.db, user, products=products, status="Delivered")
    text = (await client.get("/my-orders/_list", headers=HX)).text
    for part in (order["orderId"], "Delivered", "Order Date", "Expected Delivery", "Delivered On", "Delivered on",
                 "Qty: 2 × ₹100", "+1 more product(s)", "Grand Total", "₹800"):
        assert part in text, part
    assert "Candle 3" not in text


async def test_cancelled_hides_expected_delivery(client, app):
    user = await login_as(client, app)
    await make_order(app.state.db, user, status="Cancelled")
    text = (await client.get("/my-orders/_list", headers=HX)).text
    assert "Expected Delivery" not in text and "Cancelled On" in text


async def test_order_card_links_to_detail(client, app):
    user = await login_as(client, app)
    order = await make_order(app.state.db, user)
    assert f'href="/my-orders/{order["_id"]}"' in (await client.get("/my-orders/_list", headers=HX)).text


async def test_detail_page(client, app):
    user = await login_as(client, app)
    order = await make_order(app.state.db, user, status="Shipped")
    text = (await client.get(f"/my-orders/{order['_id']}")).text
    for part in ("Order Details", order["orderId"], "Tracking", "Order Placed", "On the way", "Delivery Details",
                 "12 MG Road", "Jaipur, 302001", "Items Total", "PAYABLE SEPARATELY", "Back to My Orders"):
        assert part in text, part


async def test_detail_summary(client, app):
    user = await login_as(client, app)
    order = await make_order(app.state.db, user, products=[await make_product(app.state.db, price=600)])
    text = (await client.get(f"/my-orders/{order['_id']}")).text
    assert "FREE" in text and "₹1,200" in text


async def test_cancelled_notice(client, app):
    user = await login_as(client, app)
    order = await make_order(app.state.db, user, status="Cancelled")
    text = (await client.get(f"/my-orders/{order['_id']}")).text
    assert "Order Cancelled" in text and "Cancelled on" in text and "Expected Delivery" not in text


async def test_detail_other_user_redirects(client, app):
    await login_as(client, app)
    theirs = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.get(f"/my-orders/{theirs['_id']}")
    assert r.status_code == 303 and r.headers["location"] == "/my-orders"


async def test_detail_not_found_redirects_with_toast(client, app):
    await login_as(client, app)
    for oid in (str(ObjectId()), "abc"):
        r = await client.get(f"/my-orders/{oid}")
        assert r.status_code == 303 and r.headers["location"] == "/my-orders"
    assert "Order not found" in (await client.get("/my-orders")).text


async def test_detail_anonymous_redirects_to_login(client, app):
    order = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.get(f"/my-orders/{order['_id']}")
    assert r.status_code == 303 and r.headers["location"].startswith("/login?redirect=%2Fmy-orders%2F")


async def test_dates_rendered_in_ist(client, app):
    user = await login_as(client, app)
    order = await make_order(app.state.db, user)
    created = order["createdAt"] + timedelta(hours=5, minutes=30)
    text = (await client.get(f"/my-orders/{order['_id']}")).text
    assert f"{created.day:02d} " in text and utcnow()

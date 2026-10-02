"""Admin → Orders (FR-095–FR-103 via UI, FR-UI-120–FR-UI-125, D-16, D-30)."""

from __future__ import annotations

import json

from bson import ObjectId

from tests.helpers import hx, login_as, make_order, make_product, make_user

HX = {"HX-Request": "true"}


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def admin(client, app):
    return await login_as(client, app, role="admin")


async def test_list_admin_only(client, app):
    assert (await client.get("/admin/orders")).headers["location"] == "/login?redirect=%2Fadmin%2Forders"
    await login_as(client, app)
    assert (await client.get("/admin/orders")).headers["location"] == "/"
    assert (await client.get("/admin/orders/_table", headers=HX)).status_code == 403


async def test_page_shell(client, app):
    await admin(client, app)
    text = (await client.get("/admin/orders")).text
    assert "Manage customer WhatsApp orders" in text and "Loading orders..." in text and "All Status" in text
    assert 'placeholder="Search by order ID, name or mobile..."' in text


async def test_table_lists_orders_paginated(client, app):
    await admin(client, app)
    app.state.settings.admin_orders_page_size = 5
    user = await make_user(app.state.db)
    orders = [await make_order(app.state.db, user, created_offset_minutes=i) for i in range(7)]
    r = await client.get("/admin/orders/_table", headers=HX)
    assert r.text.count('id="order-row-') == 5 and "Page <span class=\"font-semibold text-royal-900\">1</span> of 2" in r.text
    assert orders[0]["orderId"] in r.text and orders[6]["orderId"] not in r.text
    r = await client.get("/admin/orders/_table?page=2", headers=HX)
    assert r.text.count('id="order-row-') == 2 and orders[6]["orderId"] in r.text


async def test_stats_over_all_orders(client, app):
    await admin(client, app)
    user = await make_user(app.state.db)
    for status in ("Pending", "Pending", "Processing", "Delivered", "Cancelled", "Shipped"):
        await make_order(app.state.db, user, status=status)
    r = await client.get("/admin/orders/_table?status=Delivered", headers=HX)
    stats = r.text[r.text.index('id="orders-stats"'):r.text.index("</div>\n</div>", r.text.index('id="orders-stats"'))]
    assert 'hx-swap-oob="true"' in r.text
    assert ">6</p>" in stats and ">2</p>" in stats


async def test_search_and_status_filter(client, app):
    await admin(client, app)
    user = await make_user(app.state.db)
    a = await make_order(app.state.db, user, status="Pending")
    await app.state.db.orders.update_one({"_id": a["_id"]}, {"$set": {"customer.name": "Meera Shah", "customer.mobile": "9000000001"}})
    b = await make_order(app.state.db, user, status="Shipped")
    for q in ("meera", "9000000001", a["orderId"][-4:]):
        text = (await client.get(f"/admin/orders/_table?q={q}", headers=HX)).text
        assert a["orderId"] in text and b["orderId"] not in text, q
    text = (await client.get("/admin/orders/_table?status=Shipped", headers=HX)).text
    assert b["orderId"] in text and a["orderId"] not in text
    text = (await client.get("/admin/orders/_table?q=zzz", headers=HX)).text
    assert "No orders found" in text and "Try changing your search or status filter." in text


async def test_row_contents_and_allowed_options(client, app):
    await admin(client, app)
    product = await make_product(app.state.db, name="Rose Jar")
    order = await make_order(app.state.db, await make_user(app.state.db), products=[product], status="Shipped")
    text = (await client.get("/admin/orders/_table", headers=HX)).text
    assert "WhatsApp Order" in text and "1 product(s)" in text and "Rose Jar" in text and "View" in text
    select = text[text.index("<select name=\"status\""):text.index("</select>", text.index("<select name=\"status\""))]
    assert '<option value="Shipped" selected>' in select and "Delivered" in select and "Cancelled" in select
    assert "Pending" not in select and "Confirmed" not in select and order


async def test_terminal_order_select_disabled(client, app):
    await admin(client, app)
    await make_order(app.state.db, await make_user(app.state.db), status="Delivered")
    text = (await client.get("/admin/orders/_table", headers=HX)).text
    assert "disabled title=\"This order is delivered and can no longer change\"" in text


async def test_status_change_row_and_toast(client, app):
    await admin(client, app)
    order = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.put(f"/admin/orders/{order['_id']}/status", data={"status": "Confirmed", "source": "row"},
                         headers=await hx(client, app))
    assert r.status_code == 200 and toasts(r) == ["Order status changed to Confirmed"]
    assert r.text.lstrip().startswith(f'<tr id="order-row-{order["_id"]}"') and 'id="orders-stats" class' in r.text
    stored = await app.state.db.orders.find_one({"_id": order["_id"]})
    assert stored["status"] == "Confirmed" and stored["statusDates"]["Confirmed"] is not None


async def test_invalid_transition_toast(client, app):
    await admin(client, app)
    order = await make_order(app.state.db, await make_user(app.state.db), status="Cancelled")
    r = await client.put(f"/admin/orders/{order['_id']}/status", data={"status": "Shipped"}, headers=await hx(client, app))
    assert r.status_code == 400 and toasts(r) == ["Cannot change order status from Cancelled to Shipped"]


async def test_status_non_admin_403(client, app):
    order = await make_order(app.state.db, await make_user(app.state.db))
    await login_as(client, app)
    r = await client.put(f"/admin/orders/{order['_id']}/status", data={"status": "Confirmed"}, headers=await hx(client, app))
    assert r.status_code == 403 and (await app.state.db.orders.find_one({"_id": order["_id"]}))["status"] == "Pending"


async def test_modal_contents(client, app):
    await admin(client, app)
    order = await make_order(app.state.db, await make_user(app.state.db), message="Gift wrap please", status="Confirmed")
    text = (await client.get(f"/admin/orders/{order['_id']}", headers=HX)).text
    for part in (order["orderId"], "Order Received", "Expected Delivery", "Customer Details", "Jaipur - 302001",
                 "Current Order Status", "Order Timeline", "Order Pending", "Order Confirmed", "Current",
                 "Not processing yet", "Not shipped yet", "Products", "Items Total", "Grand Total", "Customer Note",
                 "Gift wrap please", "Order Date:"):
        assert part in text, part


async def test_modal_updated_oob(client, app):
    await admin(client, app)
    order = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.put(f"/admin/orders/{order['_id']}/status", data={"status": "Processing", "source": "modal"},
                         headers=await hx(client, app))
    assert r.text.lstrip().startswith('<div id="modal-body"') and "Processing" in r.text
    assert f'<tr id="order-row-{order["_id"]}" hx-swap-oob="true">' in r.text


async def test_modal_unknown_order(client, app):
    await admin(client, app)
    r = await client.get(f"/admin/orders/{ObjectId()}", headers=HX)
    assert r.status_code == 404 and toasts(r) == ["Order not found"]


async def test_status_uses_first_value_when_duplicated(client, app):
    await admin(client, app)
    order = await make_order(app.state.db, await make_user(app.state.db))
    r = await client.put(f"/admin/orders/{order['_id']}/status", content="status=Confirmed&q=&status=&source=row",
                         headers={**(await hx(client, app)), "content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and toasts(r) == ["Order status changed to Confirmed"]


async def test_orders_panel_does_not_leak_filters(client, app):
    await admin(client, app)
    text = (await client.get("/admin/orders")).text
    assert 'hx-disinherit="hx-include"' in text

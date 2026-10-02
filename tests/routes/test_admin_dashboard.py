"""Admin dashboard (FR-UI-097–FR-UI-102)."""

from __future__ import annotations

from pymongo.errors import PyMongoError

from app.services import dashboard_service
from tests.helpers import login_as, make_category, make_order, make_product, make_user

HX = {"HX-Request": "true"}


async def test_sidebar_links(client, app):
    await login_as(client, app, role="admin")
    text = (await client.get("/admin")).text
    for href, label in (("/admin", "Dashboard"), ("/admin/categories", "Categories"), ("/admin/products", "Products"),
                        ("/admin/orders", "Orders"), ("/admin/banner", "Banners"), ("/admin/promo-card", "Promotional Cards"),
                        ("/", "Back to Website")):
        assert f'href="{href}"' in text and label in text
    assert "AK Royal Flames <span class=\"text-flame-300\">Admin</span>" in text
    assert "<footer" not in text and 'id="mobile-menu"' not in text


async def test_counts_and_delivered_revenue(client, app):
    db = app.state.db
    await login_as(client, app, role="admin")
    cat = await make_category(db)
    await make_product(db, cat)
    await make_product(db, cat, name="Two")
    user = await make_user(db)
    await make_order(db, user, status="Delivered", products=[await make_product(db, cat, name="Three", price=500)])
    await make_order(db, user, status="Pending")
    summary = await dashboard_service.summary(db)
    assert summary["products"] == 3 and summary["categories"] == 1 and summary["orders"] == 2 and summary["revenue"] == 1000
    text = (await client.get("/admin/_p/stats", headers=HX)).text
    assert "Delivered Revenue" in text and "₹1,000" in text and "Only delivered orders" in text


async def test_status_counts(client, app):
    db = app.state.db
    user = await make_user(db)
    for status in ("Pending", "Shipped", "Shipped"):
        await make_order(db, user, status=status)
    counts = await dashboard_service.status_counts(db)
    assert counts == {"Pending": 1, "Confirmed": 0, "Processing": 0, "Shipped": 2, "Delivered": 0, "Cancelled": 0}


async def test_recent_orders(client, app):
    db = app.state.db
    await login_as(client, app, role="admin")
    user = await make_user(db, name="Ravi", phone="9111111111")
    orders = [await make_order(db, user, created_offset_minutes=i) for i in range(7)]
    text = (await client.get("/admin/_p/recent-orders", headers=HX)).text
    assert "7 Total" in text and text.count("<tr>") == 6 and orders[0]["orderId"] in text and orders[6]["orderId"] not in text
    assert "2 Items" in text


async def test_recent_orders_empty(client, app):
    await login_as(client, app, role="admin")
    text = (await client.get("/admin/_p/recent-orders", headers=HX)).text
    assert "No orders yet" in text and "Customer orders will appear here." in text


async def test_section_error_isolated(client, app, monkeypatch):
    await login_as(client, app, role="admin")

    async def boom(db):
        raise PyMongoError("down")

    monkeypatch.setattr(dashboard_service, "summary", boom)
    r = await client.get("/admin/_p/stats", headers=HX)
    assert "Unable to load dashboard" in r.text and "Retry" in r.text and "₹0" not in r.text
    assert "Recent Orders" in (await client.get("/admin/_p/recent-orders", headers=HX)).text


async def test_refresh_markup(client, app):
    await login_as(client, app, role="admin")
    page = (await client.get("/admin")).text
    assert "Refreshing..." in page and 'hx-get="/admin/_p/dashboard"' in page and "Loading dashboard..." in page
    r = await client.get("/admin/_p/dashboard", headers=HX)
    assert 'id="dashboard-stats" hx-swap-oob="true"' in r.text and 'id="dashboard-recent" class="mt-8" hx-swap-oob="true"' in r.text

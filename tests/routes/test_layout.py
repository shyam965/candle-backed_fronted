"""Global layout: header, footer, nav, badge, toasts (FR-UI-001–FR-UI-009)."""

from __future__ import annotations

import json
import re

from app.core.documents import new_meta
from tests.helpers import hx, login_as, make_product


async def test_site_pages_have_header_footer(client):
    for path in ("/about", "/contact", "/login", "/register"):
        text = (await client.get(path)).text
        assert "<header" in text and "<footer" in text, path


async def test_navigation_is_full_page(client):
    text = (await client.get("/about")).text
    assert "hx-boost" not in text  # plain links: every navigation starts at the top of the page


async def test_toast_region_config(client):
    text = (await client.get("/about")).text
    assert 'id="toasts"' in text and 'data-duration="3000"' in text and "top-4" in text and "items-center" in text


async def test_htmx_toast_trigger_header(client, app):
    r = await client.post("/login", data={"email": "", "password": ""}, headers=await hx(client, app))
    event = json.loads(r.headers["HX-Trigger"])["toast"]["items"][0]
    assert event == {"type": "error", "message": "Please enter email and password"}


async def test_active_nav_link(client):
    text = (await client.get("/about")).text
    assert re.search(r'href="/about" class="nav-link" aria-current="page"', text)
    assert not re.search(r'href="/" class="nav-link" aria-current="page"', text)


async def test_header_guest_vs_user(client, app):
    guest = (await client.get("/about")).text
    assert 'href="/login"' in guest and 'href="/my-orders"' not in guest
    user = await login_as(client, app, name="Ravi Kumar")
    text = (await client.get("/about")).text
    assert 'href="/my-orders"' in text and "Ravi Kumar" in text and 'hx-post="/logout"' in text
    assert 'aria-label="Admin dashboard"' not in text and user


async def test_header_admin_links_only_for_admin(client, app):
    await login_as(client, app, role="admin")
    text = (await client.get("/about")).text
    assert 'aria-label="Admin dashboard"' in text and "Admin Dashboard" in text


async def test_mobile_menu_actions(client, app):
    guest = (await client.get("/about")).text
    menu = guest[guest.index('id="mobile-menu"'):]
    assert 'href="/shop"' in menu and 'href="/login"' in menu
    await login_as(client, app, name="Ravi Kumar")
    menu = (await client.get("/about")).text
    menu = menu[menu.index('id="mobile-menu"'):]
    assert "Welcome" in menu and "Ravi Kumar" in menu and "Logging out..." in menu and 'href="/my-orders"' in menu


async def test_cart_badge_hidden_zero_and_99_plus(client, app):
    db = app.state.db
    user = await login_as(client, app)
    badge = re.compile(r'<span id="cart-badge"[^>]*>([^<]*)</span>')
    text = (await client.get("/about")).text
    assert re.search(r'hidden\s+data-count="0"', text)
    product = await make_product(db, stock=500)
    await db.carts.insert_one({"user": user["_id"], "items": [{"product": product["_id"], "quantity": 3, "selected": False}], **new_meta()})
    assert badge.search((await client.get("/about")).text).group(1) == "3"
    await db.carts.update_one({"user": user["_id"]}, {"$set": {"items.0.quantity": 120}})
    assert badge.search((await client.get("/about")).text).group(1) == "99+"


async def test_header_search_form(client):
    text = (await client.get("/about")).text
    assert 'action="/shop"' in text and 'name="search"' in text and 'placeholder="Search candles..."' in text

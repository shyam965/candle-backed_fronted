"""Admin → Banners / Promotional Cards (FR-UI-114–FR-UI-119)."""

from __future__ import annotations

import json

from tests.helpers import hx, image_file, login_as


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def test_pages_require_admin(client, app):
    for path in ("/admin/banner", "/admin/promo-card"):
        assert (await client.get(path)).status_code == 303
    await login_as(client, app)
    assert (await client.get("/admin/banner")).headers["location"] == "/"


async def test_banner_validation_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/banner", data={"title": " ", "status": "true"}, files=image_file(), headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Please enter banner title"]
    r = await client.post("/admin/banner", data={"title": "Diwali", "status": "true"}, headers=await hx(client, app))
    assert toasts(r) == ["Please select banner image"] and 'value="Diwali"' in r.text


async def test_promo_validation_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/promo-card", data={"title": ""}, files=image_file(), headers=await hx(client, app))
    assert toasts(r) == ["Please enter title"]
    r = await client.post("/admin/promo-card", data={"title": "Gifts"}, headers=await hx(client, app))
    assert toasts(r) == ["Please select image"]


async def test_banner_defaults_and_reset(client, app):
    await login_as(client, app, role="admin")
    page = await client.get("/admin/banner")
    assert "Banner Management" in page.text and 'value="Shop Now"' in page.text and 'value="/shop"' in page.text
    assert 'name="order"' in page.text and 'value="0"' in page.text
    r = await client.post("/admin/banner", data={"title": "Diwali", "buttonText": "Buy", "buttonLink": "/shop?x=1",
                                                 "order": "1", "status": ["false", "true"]},
                          files=image_file(), headers=await hx(client, app))
    assert r.status_code == 200 and toasts(r) == ["Banner uploaded successfully"]
    assert 'value="Diwali"' not in r.text and 'value="Shop Now"' in r.text  # form reset
    assert 'id="merch-list" class="card" hx-swap-oob="true"' in r.text and "Diwali" in r.text
    doc = await app.state.db.banners.find_one({})
    assert doc["buttonText"] == "Buy" and doc["order"] == 1 and doc["status"] is True


async def test_promo_defaults_and_reset(client, app):
    await login_as(client, app, role="admin")
    page = await client.get("/admin/promo-card")
    assert "Promotional Card Management" in page.text and 'type="color" value="#08aaa6"' in page.text
    r = await client.post("/admin/promo-card", data={"title": "Gifts", "background": "#123abc", "status": "false"},
                          files=image_file(), headers=await hx(client, app))
    assert toasts(r) == ["Promotional card uploaded"]
    doc = await app.state.db.promocards.find_one({})
    assert doc["background"] == "#123abc" and doc["status"] is False


async def test_list_and_delete(client, app):
    await login_as(client, app, role="admin")
    await client.post("/admin/banner", data={"title": "Diwali", "status": "true"}, files=image_file(), headers=await hx(client, app))
    listing = await client.get("/admin/banner/_list", headers={"HX-Request": "true"})
    assert "All Banners" in listing.text and "Button: <span" in listing.text and "Order:" in listing.text and "Active" in listing.text
    assert 'hx-confirm="Are you sure you want to delete this banner?"' in listing.text
    doc = await app.state.db.banners.find_one({})
    r = await client.delete(f"/admin/banner/{doc['_id']}", headers=await hx(client, app))
    assert toasts(r) == ["Banner deleted successfully"] and "No banners found." in r.text


async def test_colour_picker_and_background(client, app):
    await login_as(client, app, role="admin")
    await client.post("/admin/promo-card", data={"title": "Gifts", "background": "#123abc", "status": "true"},
                      files=image_file(), headers=await hx(client, app))
    listing = await client.get("/admin/promo-card/_list", headers={"HX-Request": "true"})
    assert "background-color: #123abc" in listing.text and "All Promotional Cards" in listing.text
    doc = await app.state.db.promocards.find_one({})
    r = await client.delete(f"/admin/promo-card/{doc['_id']}", headers=await hx(client, app))
    assert toasts(r) == ["Promotional card deleted"] and "No promotional cards found." in r.text


async def test_success_toasts(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/banner", data={"title": "A"}, files=image_file(), headers=await hx(client, app))
    assert toasts(r) == ["Banner uploaded successfully"]
    r = await client.post("/admin/promo-card", data={"title": "B"}, files=image_file(), headers=await hx(client, app))
    assert toasts(r) == ["Promotional card uploaded"]

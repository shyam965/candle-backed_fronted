"""Admin → Categories pages and partials (FR-UI-103–FR-UI-108)."""

from __future__ import annotations

import json

from bson import ObjectId

from tests.helpers import FAKE_PNG, PNG, hx, image_file, login_as, make_category, make_product


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def test_page_requires_admin(client, app):
    r = await client.get("/admin/categories")
    assert r.status_code == 303 and r.headers["location"] == "/login?redirect=%2Fadmin%2Fcategories"
    await login_as(client, app)
    r = await client.get("/admin/categories")
    assert r.status_code == 303 and r.headers["location"] == "/"
    r = await client.get("/admin/categories/_table", headers={"HX-Request": "true"})
    assert r.status_code == 403


async def test_list_and_search(client, app):
    await login_as(client, app, role="admin")
    await make_category(app.state.db, "Jar Candles", description="glass jars")
    await make_category(app.state.db, "Pillars", description="")
    page = await client.get("/admin/categories")
    assert page.status_code == 200 and 'hx-get="/admin/categories/_table"' in page.text
    r = await client.get("/admin/categories/_table", headers={"HX-Request": "true"})
    assert "Categories (2)" in r.text and "Manage your categories" in r.text and "—" in r.text
    r = await client.get("/admin/categories/_table?q=GLASS", headers={"HX-Request": "true"})
    assert "Jar Candles" in r.text and "Pillars" not in r.text
    r = await client.get("/admin/categories/_table?q=zzz", headers={"HX-Request": "true"})
    assert "No categories found" in r.text


async def test_form_validation_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/categories", data={"name": " "}, headers=await hx(client, app))
    assert r.status_code == 422 and "Category name is required" in r.text
    r = await client.post("/admin/categories", data={"name": "Jars", "description": "d"}, headers=await hx(client, app))
    assert r.status_code == 422 and "Please upload a category image" in r.text and 'value="Jars"' in r.text


async def test_image_type_and_size_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/categories", data={"name": "Jars"}, files=image_file(FAKE_PNG), headers=await hx(client, app))
    assert r.status_code == 422 and "Only JPG, PNG and WebP images are allowed" in r.text
    r = await client.post("/admin/categories", data={"name": "Jars"}, files=image_file(PNG + b"\0" * (5 * 1024 * 1024)),
                          headers=await hx(client, app))
    assert "Image must be under 5 MB" in r.text


async def test_create(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/categories", data={"name": "Jars", "description": " Glass "}, files=image_file(),
                          headers=await hx(client, app))
    assert r.status_code == 200 and "Categories (1)" in r.text
    doc = await app.state.db.categories.find_one({"name": "Jars"})
    assert doc["description"] == "Glass" and doc["image"].startswith("/uploads/")


async def test_update_keeps_image_when_none(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars", image="/uploads/keep.png")
    form = await client.get(f"/admin/categories/{cat['_id']}/edit", headers={"HX-Request": "true"})
    assert "Edit Category" in form.text and "Leave the image unchanged to keep the current image." in form.text
    r = await client.put(f"/admin/categories/{cat['_id']}", data={"name": "Jar Candles", "description": ""},
                         headers=await hx(client, app))
    assert r.status_code == 200
    doc = await app.state.db.categories.find_one({"_id": cat["_id"]})
    assert doc["name"] == "Jar Candles" and doc["image"] == "/uploads/keep.png"


async def test_success_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/categories", data={"name": "Jars"}, files=image_file(), headers=await hx(client, app))
    assert toasts(r) == ["Category created successfully"] and "Category created successfully" in r.text
    cat = await app.state.db.categories.find_one({"name": "Jars"})
    r = await client.put(f"/admin/categories/{cat['_id']}", data={"name": "Jars 2"}, headers=await hx(client, app))
    assert toasts(r) == ["Category updated successfully"]


async def test_delete_flow(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    table = await client.get("/admin/categories/_table", headers={"HX-Request": "true"})
    assert 'hx-confirm=\'Are you sure you want to delete "Jars"?\'' in table.text
    r = await client.delete(f"/admin/categories/{cat['_id']}", headers=await hx(client, app))
    assert r.status_code == 200 and toasts(r) == ["Category deleted successfully"]
    assert await app.state.db.categories.count_documents({}) == 0


async def test_delete_with_products_message(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    await make_product(app.state.db, cat)
    r = await client.delete(f"/admin/categories/{cat['_id']}", headers=await hx(client, app))
    assert r.status_code == 409
    assert toasts(r) == ["This category contains products. Delete or reassign those products first."]


async def test_invalid_id_404(client, app):
    await login_as(client, app, role="admin")
    r = await client.get(f"/admin/categories/{ObjectId()}/edit", headers={"HX-Request": "true"})
    assert r.status_code == 404 and toasts(r) == ["Category not found"]
    r = await client.get("/admin/categories/nope/edit", headers={"HX-Request": "true"})
    assert r.status_code == 400 and toasts(r) == ["Invalid category ID"]


async def test_mutations_require_csrf(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    r = await client.delete(f"/admin/categories/{cat['_id']}", headers={"HX-Request": "true"})
    assert r.status_code == 403 and await app.state.db.categories.count_documents({}) == 1

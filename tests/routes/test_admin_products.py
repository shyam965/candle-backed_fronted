"""Admin → Products (FR-UI-109–FR-UI-113)."""

from __future__ import annotations

import json

from tests.helpers import hx, image_file, login_as, make_category, make_product


def toasts(r):
    return [t["message"] for t in json.loads(r.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def test_page_requires_admin(client, app):
    assert (await client.get("/admin/products")).headers["location"] == "/login?redirect=%2Fadmin%2Fproducts"
    await login_as(client, app)
    assert (await client.get("/admin/products")).headers["location"] == "/"


async def test_list_and_search(client, app):
    await login_as(client, app, role="admin")
    jars = await make_category(app.state.db, "Jars")
    pillars = await make_category(app.state.db, "Pillars")
    await make_product(app.state.db, jars, name="Rose", price=499, oldPrice=699, stock=0)
    await make_product(app.state.db, pillars, name="Vanilla", price=299, stock=5)
    r = await client.get("/admin/products/_table", headers={"HX-Request": "true"})
    assert "Products (2)" in r.text and "Out of stock" in r.text and "₹699" in r.text and "Jars" in r.text
    r = await client.get("/admin/products/_table?q=pillars", headers={"HX-Request": "true"})
    assert "Vanilla" in r.text and "Rose" not in r.text


async def test_old_price_hidden_when_unset(client, app):
    await login_as(client, app, role="admin")
    await make_product(app.state.db, name="Plain", price=299)
    r = await client.get("/admin/products/_table", headers={"HX-Request": "true"})
    assert "line-through" not in r.text


async def test_validation_order_and_messages(client, app):
    await login_as(client, app, role="admin")
    r = await client.post("/admin/products", data={"name": "", "category": "", "price": "", "stock": ""},
                          headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Product name is required"]
    for text in ("Please select a category", "Please upload a product image", "Please enter a valid price", "Please enter valid stock"):
        assert text in r.text


async def test_create(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    data = {"name": "Rose", "category": str(cat["_id"]), "price": "499", "oldPrice": "", "stock": "3", "description": ""}
    r = await client.post("/admin/products", data=data, files=image_file(), headers=await hx(client, app))
    assert r.status_code == 200 and toasts(r) == ["Product created successfully"] and "Products (1)" in r.text
    doc = await app.state.db.products.find_one({"name": "Rose"})
    assert "oldPrice" not in doc and doc["stock"] == 3


async def test_create_duplicate_shows_message(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    await make_product(app.state.db, cat, name="Rose")
    data = {"name": "rose", "category": str(cat["_id"]), "price": "499", "oldPrice": "", "stock": "3"}
    r = await client.post("/admin/products", data=data, files=image_file(), headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Product already exists"]


async def test_edit_form_prefilled(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    prod = await make_product(app.state.db, cat, name="Rose", price=499.0, oldPrice=699, stock=7)
    r = await client.get(f"/admin/products/{prod['_id']}/edit", headers={"HX-Request": "true"})
    assert 'value="Rose"' in r.text and 'value="499"' in r.text and 'value="699"' in r.text and 'value="7"' in r.text
    assert f'value="{cat["_id"]}" selected' in r.text and "Update Product" in r.text


async def test_update(client, app):
    await login_as(client, app, role="admin")
    cat = await make_category(app.state.db, "Jars")
    prod = await make_product(app.state.db, cat, name="Rose", oldPrice=699)
    data = {"name": "Rose 2", "category": str(cat["_id"]), "price": "450", "oldPrice": "", "stock": "9", "description": "x"}
    r = await client.put(f"/admin/products/{prod['_id']}", data=data, headers=await hx(client, app))
    assert toasts(r) == ["Product updated successfully"]
    doc = await app.state.db.products.find_one({"_id": prod["_id"]})
    assert doc["name"] == "Rose 2" and "oldPrice" not in doc and doc["image"] == prod["image"]


async def test_no_categories_hint(client, app):
    await login_as(client, app, role="admin")
    r = await client.get("/admin/products/new", headers={"HX-Request": "true"})
    assert "Please create a category first." in r.text and "Upload Product" in r.text


async def test_delete_flow(client, app):
    await login_as(client, app, role="admin")
    prod = await make_product(app.state.db, name="Rose")
    table = await client.get("/admin/products/_table", headers={"HX-Request": "true"})
    assert 'Are you sure you want to delete "Rose"?' in table.text
    r = await client.delete(f"/admin/products/{prod['_id']}", headers=await hx(client, app))
    assert toasts(r) == ["Product deleted successfully"] and await app.state.db.products.count_documents({}) == 0

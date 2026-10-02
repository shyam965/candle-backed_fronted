"""`/api/product/*` (FR-050–FR-064, D-24, D-25, D-35)."""

from __future__ import annotations

from bson import ObjectId

from app.core.documents import new_meta
from tests.helpers import API_ORIGIN, PNG, image_file, login_as, make_category, make_order, make_product, make_user


def files_in(app):
    return sorted(p.name for p in app.state.settings.upload_dir.iterdir())


async def setup(client, app):
    await login_as(client, app, role="admin")
    return await make_category(app.state.db, "Jars")


def body(cat, **kw):
    data = {"name": "Rose Jar", "category": str(cat["_id"]), "price": "499", "oldPrice": "699", "stock": "12", "description": " d "}
    data.update(kw)
    return data


async def create(client, data, files=None):
    return await client.post("/api/product/create-product", data=data, files=files if files is not None else image_file(),
                             headers=API_ORIGIN)


async def test_create(client, app):
    cat = await setup(client, app)
    r = await create(client, body(cat))
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["category"] == str(cat["_id"]) and data["price"] == 499 and data["oldPrice"] == 699
    assert data["stock"] == 12 and data["description"] == "d"
    stored = await app.state.db.products.find_one({"_id": ObjectId(data["_id"])})
    assert isinstance(stored["price"], int) and isinstance(stored["category"], ObjectId)


async def test_create_without_old_price_omits_field(client, app):
    cat = await setup(client, app)
    data = (await create(client, body(cat, oldPrice=""))).json()["data"]
    assert "oldPrice" not in data
    data = (await create(client, body(cat, name="Decimal", price="499.5"))).json()["data"]
    assert data["price"] == 499.5


async def test_create_response_shape(client, app):
    cat = await setup(client, app)
    r = (await create(client, body(cat))).json()
    assert r["message"] == "Product created successfully" and r["success"] is True and r["error"] is False
    assert r["data"]["image"].startswith("/uploads/")


async def test_create_requires_admin(client, app):
    cat = await make_category(app.state.db)
    assert (await create(client, body(cat))).status_code == 401
    await login_as(client, app)
    assert (await create(client, body(cat))).status_code == 403


async def test_create_missing_required(client, app):
    cat = await setup(client, app)
    for field in ("name", "category", "price", "stock"):
        r = await create(client, body(cat, **{field: ""}))
        assert r.status_code == 400
        assert r.json() == {"message": "Name, category, price and stock are required", "success": False, "error": True}
    assert files_in(app) == []


async def test_create_without_image(client, app):
    cat = await setup(client, app)
    r = await client.post("/api/product/create-product", data=body(cat), headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Please upload an image"


async def test_invalid_category_400(client, app):
    cat = await setup(client, app)
    r = await create(client, body(cat, category="abc"))
    assert r.status_code == 400 and r.json()["message"] == "Invalid category ID"


async def test_unknown_category_404(client, app):
    cat = await setup(client, app)
    r = await create(client, body(cat, category=str(ObjectId())))
    assert r.status_code == 404 and r.json()["message"] == "Category not found"


async def test_create_invalid_numbers(client, app):
    cat = await setup(client, app)
    for kw in ({"price": "0"}, {"price": "abc"}, {"stock": "-1"}, {"stock": "2.5"}, {"oldPrice": "0"}):
        r = await create(client, body(cat, **kw))
        assert r.status_code == 400 and r.json()["message"] == "Invalid price, old price or stock", kw
    assert files_in(app) == []


async def test_old_price_below_price_400(client, app):
    cat = await setup(client, app)
    r = await create(client, body(cat, price="500", oldPrice="400"))
    assert r.status_code == 400 and r.json()["message"] == "Old price cannot be less than price"
    prod = await make_product(app.state.db, cat, price=500)
    r = await client.put(f"/api/product/update-product/{prod['_id']}", json={"oldPrice": "400"}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Old price cannot be less than price"
    r = await client.put(f"/api/product/update-product/{prod['_id']}", json={"oldPrice": "500"}, headers=API_ORIGIN)
    assert r.status_code == 200  # equal is allowed


async def test_unrelated_update_not_blocked_by_legacy_prices(client, app):
    cat = await setup(client, app)
    legacy = await make_product(app.state.db, cat, price=500, oldPrice=300)
    r = await client.put(f"/api/product/update-product/{legacy['_id']}", json={"stock": "4"}, headers=API_ORIGIN)
    assert r.status_code == 200 and r.json()["data"]["stock"] == 4


async def test_duplicate_in_category_409(client, app):
    cat = await setup(client, app)
    await make_product(app.state.db, cat, name="Rose Jar")
    r = await create(client, body(cat, name=" rose jar "))
    assert r.status_code == 409 and r.json()["message"] == "Product already exists"
    other = await make_category(app.state.db, "Other")
    assert (await create(client, body(other, name="Rose Jar"))).status_code == 201


async def test_update_duplicate_409(client, app):
    cat = await setup(client, app)
    await make_product(app.state.db, cat, name="Taken")
    mine = await make_product(app.state.db, cat, name="Mine")
    r = await client.put(f"/api/product/update-product/{mine['_id']}", json={"name": "TAKEN"}, headers=API_ORIGIN)
    assert r.status_code == 409


async def test_list_public_shape(client, app):
    cat = await make_category(app.state.db)
    await make_product(app.state.db, cat)
    body_ = (await client.get("/api/product/get-product")).json()
    assert body_["message"] == "products fetched successfully" and body_["success"] is True
    assert body_["data"][0]["category"] == str(cat["_id"])


async def test_invalid_id_400(client, app):
    await setup(client, app)
    for method, path in (("put", "/api/product/update-product/abc"), ("delete", "/api/product/delete-product/abc")):
        r = await client.request(method.upper(), path, json={}, headers=API_ORIGIN)
        assert r.status_code == 400 and r.json()["message"] == "Invalid product ID"


async def test_not_found_404(client, app):
    await setup(client, app)
    r = await client.put(f"/api/product/update-product/{ObjectId()}", json={"stock": 1}, headers=API_ORIGIN)
    assert r.status_code == 404 and r.json()["message"] == "Product not found"
    r = await client.delete(f"/api/product/delete-product/{ObjectId()}", headers=API_ORIGIN)
    assert r.status_code == 404


async def test_update_field_messages(client, app):
    cat = await setup(client, app)
    prod = await make_product(app.state.db, cat)
    url = f"/api/product/update-product/{prod['_id']}"
    cases = [({"name": " "}, "Product name is required"), ({"category": "x"}, "Invalid category ID"),
             ({"price": "0"}, "Invalid price"), ({"oldPrice": "abc"}, "Invalid old price"), ({"stock": "1.2"}, "Invalid stock")]
    for data, message in cases:
        r = await client.put(url, json=data, headers=API_ORIGIN)
        assert r.status_code == 400 and r.json()["message"] == message, data
    r = await client.put(url, json={"category": str(ObjectId())}, headers=API_ORIGIN)
    assert r.status_code == 404 and r.json()["message"] == "Category not found"


async def test_update_empty_old_price_unsets(client, app):
    cat = await setup(client, app)
    prod = await make_product(app.state.db, cat, oldPrice=699)
    r = await client.put(f"/api/product/update-product/{prod['_id']}", data={"oldPrice": ""}, headers=API_ORIGIN)
    assert r.status_code == 200 and "oldPrice" not in r.json()["data"]
    assert "oldPrice" not in await app.state.db.products.find_one({"_id": prod["_id"]})


async def test_update_response_shape(client, app):
    cat = await setup(client, app)
    prod = await make_product(app.state.db, cat)
    r = (await client.put(f"/api/product/update-product/{prod['_id']}", json={"price": 549, "stock": 20}, headers=API_ORIGIN)).json()
    assert r["message"] == "Product updated successfully" and r["data"]["price"] == 549 and r["data"]["stock"] == 20


async def test_update_image_replaces_file(client, app):
    cat = await setup(client, app)
    created = (await create(client, body(cat))).json()["data"]
    r = await client.put(f"/api/product/update-product/{created['_id']}", files=image_file(PNG, "x.png"), headers=API_ORIGIN)
    new = r.json()["data"]["image"]
    assert new != created["image"] and files_in(app) == [new.rsplit("/", 1)[1]]


async def test_update_failure_removes_new_file(client, app):
    cat = await setup(client, app)
    prod = await make_product(app.state.db, cat)
    r = await client.put(f"/api/product/update-product/{prod['_id']}", data={"price": "0"}, files=image_file(),
                         headers=API_ORIGIN)
    assert r.status_code == 400 and files_in(app) == []


async def test_delete_cleans_carts_and_unreferenced_image(client, app):
    cat = await setup(client, app)
    created = (await create(client, body(cat))).json()["data"]
    pid = ObjectId(created["_id"])
    user = await make_user(app.state.db)
    other = await make_product(app.state.db, cat, name="Other")
    await app.state.db.carts.insert_one({"user": user["_id"], "items": [
        {"product": pid, "quantity": 1, "selected": True}, {"product": other["_id"], "quantity": 2, "selected": True}],
        **new_meta()})
    r = await client.delete(f"/api/product/delete-product/{created['_id']}", headers=API_ORIGIN)
    assert r.json() == {"message": "Product deleted successfully", "success": True, "error": False}
    cart = await app.state.db.carts.find_one({"user": user["_id"]})
    assert [i["product"] for i in cart["items"]] == [other["_id"]] and cart["__v"] == 1
    assert files_in(app) == []


async def test_delete_keeps_image_used_by_orders(client, app):
    cat = await setup(client, app)
    created = (await create(client, body(cat))).json()["data"]
    product = await app.state.db.products.find_one({"_id": ObjectId(created["_id"])})
    await make_order(app.state.db, await make_user(app.state.db), products=[product])
    await client.delete(f"/api/product/delete-product/{created['_id']}", headers=API_ORIGIN)
    assert files_in(app) == [created["image"].rsplit("/", 1)[1]]

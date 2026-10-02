"""`/api/category/*` (FR-037–FR-049, KI-01, D-12, D-24)."""

from __future__ import annotations

import re

from bson import ObjectId

from tests.helpers import API_ORIGIN, FAKE_PNG, PNG, image_file, login_as, make_category, make_product


async def admin(client, app):
    return await login_as(client, app, role="admin")


def files_in(app):
    return sorted(p.name for p in app.state.settings.upload_dir.iterdir())


async def create(client, data, files=None):
    return await client.post("/api/category/create-category", data=data, files=files or image_file(), headers=API_ORIGIN)


async def test_create(client, app):
    await admin(client, app)
    r = await create(client, {"name": "  Jar Candles ", "description": " Soy wax "})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["name"] == "Jar Candles" and data["description"] == "Soy wax"
    assert re.fullmatch(r"/uploads/\d{13}-\d+\.png", data["image"])
    assert data["__v"] == 0 and data["createdAt"].endswith("+05:30")
    assert files_in(app) == [data["image"].rsplit("/", 1)[1]]


async def test_create_response_shape(client, app):
    await admin(client, app)
    body = (await create(client, {"name": "Pillars"})).json()
    assert body["message"] == "Category created successfully" and body["success"] is True and body["error"] is False
    assert set(body["data"]) == {"_id", "name", "description", "image", "createdAt", "updatedAt", "__v"}


async def test_create_requires_admin(client, app):
    r = await create(client, {"name": "X"})
    assert r.status_code == 401
    await login_as(client, app, role="user")
    r = await create(client, {"name": "X"})
    assert r.status_code == 403 and r.json()["message"] == "Admin access required"
    assert files_in(app) == []


async def test_create_blank_name(client, app):
    await admin(client, app)
    r = await create(client, {"name": "   "})
    assert r.status_code == 400
    assert r.json() == {"message": "Category name is required", "success": False, "error": True}
    assert files_in(app) == []  # KI-08: nothing orphaned


async def test_create_without_image(client, app):
    await admin(client, app)
    r = await client.post("/api/category/create-category", data={"name": "X"}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Please upload an image"


async def test_create_rejects_spoofed_image(client, app):
    await admin(client, app)
    r = await create(client, {"name": "X"}, image_file(FAKE_PNG))
    assert r.status_code == 400 and r.json()["message"] == "Only JPG, PNG and WebP images are allowed"
    r = await create(client, {"name": "X"}, {"photo": ("a.png", PNG, "image/png")})
    assert r.status_code == 400
    assert files_in(app) == []


async def test_create_oversize_413(client, app):
    await admin(client, app)
    r = await create(client, {"name": "X"}, image_file(PNG + b"\0" * (5 * 1024 * 1024)))
    assert r.status_code == 413 and r.json()["message"] == "Image must be under 5 MB"


async def test_create_duplicate_case_insensitive(client, app):
    await admin(client, app)
    await make_category(app.state.db, "Jar Candles")
    r = await create(client, {"name": " jar candles "})
    assert r.status_code == 409 and r.json()["message"] == "Category already exists"
    assert files_in(app) == []


async def test_list_public_shape(client, app):
    await make_category(app.state.db, "A")
    await make_category(app.state.db, "B")
    r = await client.get("/api/category/get-category")
    body = r.json()
    assert r.status_code == 200 and body["message"] == "categories fetched successfully" and body["success"] is True
    assert [c["name"] for c in body["data"]] == ["A", "B"] and isinstance(body["data"][0]["_id"], str)


async def test_list_empty(client):
    assert (await client.get("/api/category/get-category")).json()["data"] == []


async def test_invalid_id_400(client, app):
    await admin(client, app)
    r = await client.put("/api/category/update-category/abc", data={"name": "x"}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Invalid category ID"
    r = await client.delete("/api/category/delete-category/abc", headers=API_ORIGIN)
    assert r.status_code == 400


async def test_not_found_404(client, app):
    await admin(client, app)
    r = await client.put(f"/api/category/update-category/{ObjectId()}", data={"name": "x"}, headers=API_ORIGIN)
    assert r.status_code == 404 and r.json()["message"] == "Category not found"
    r = await client.delete(f"/api/category/delete-category/{ObjectId()}", headers=API_ORIGIN)
    assert r.status_code == 404


async def test_update_partial(client, app):
    await admin(client, app)
    cat = await make_category(app.state.db, "Old", description="keep me")
    r = await client.put(f"/api/category/update-category/{cat['_id']}", json={"name": " New "}, headers=API_ORIGIN)
    body = r.json()
    assert r.status_code == 200 and body["message"] == "Category updated successfully"
    assert body["data"]["name"] == "New" and body["data"]["description"] == "keep me"
    assert body["data"]["image"] == cat["image"] and body["data"]["updatedAt"] >= body["data"]["createdAt"]


async def test_update_blank_name(client, app):
    await admin(client, app)
    cat = await make_category(app.state.db)
    r = await client.put(f"/api/category/update-category/{cat['_id']}", json={"name": "  "}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == "Category name is required"


async def test_rename_duplicate(client, app):
    await admin(client, app)
    await make_category(app.state.db, "Taken")
    cat = await make_category(app.state.db, "Mine")
    r = await client.put(f"/api/category/update-category/{cat['_id']}", json={"name": "TAKEN"}, headers=API_ORIGIN)
    assert r.status_code == 409
    r = await client.put(f"/api/category/update-category/{cat['_id']}", json={"name": "mine"}, headers=API_ORIGIN)
    assert r.status_code == 200  # renaming itself (case change) is allowed


async def test_update_image_deletes_old_file(client, app):
    await admin(client, app)
    created = (await create(client, {"name": "Img"})).json()["data"]
    r = await client.put(f"/api/category/update-category/{created['_id']}", files=image_file(PNG, "n.png"), headers=API_ORIGIN)
    new_image = r.json()["data"]["image"]
    assert new_image != created["image"]
    assert files_in(app) == [new_image.rsplit("/", 1)[1]]


async def test_failed_update_leaves_no_file(client, app):
    await admin(client, app)
    await make_category(app.state.db, "Taken")
    cat = await make_category(app.state.db, "Mine")
    r = await client.put(f"/api/category/update-category/{cat['_id']}", data={"name": "Taken"}, files=image_file(),
                         headers=API_ORIGIN)
    assert r.status_code == 409 and files_in(app) == []


async def test_delete_with_products_409(client, app):
    await admin(client, app)
    cat = await make_category(app.state.db)
    await make_product(app.state.db, cat)
    r = await client.delete(f"/api/category/delete-category/{cat['_id']}", headers=API_ORIGIN)
    assert r.status_code == 409
    assert r.json()["message"] == "This category contains products. Delete or reassign those products first."


async def test_delete_removes_doc_and_file(client, app):
    await admin(client, app)
    created = (await create(client, {"name": "Gone"})).json()["data"]
    r = await client.delete(f"/api/category/delete-category/{created['_id']}", headers=API_ORIGIN)
    body = r.json()
    assert r.status_code == 200 and body["message"] == "Category deleted successfully" and body["data"]["name"] == "Gone"
    assert await app.state.db.categories.count_documents({}) == 0 and files_in(app) == []

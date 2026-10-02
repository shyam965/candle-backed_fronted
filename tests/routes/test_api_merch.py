"""`/api/banner/*` and `/api/promo-card/*` (FR-104–FR-117)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from bson import ObjectId

from app.core.documents import new_meta, now_ist
from tests.helpers import API_ORIGIN, image_file, login_as

KINDS = {
    "banner": {"collection": "banners", "base": "/api/banner", "create": "/create-banner", "public": "/get-banner",
               "all": "/get-all-banner", "delete": "/delete-banner", "title_msg": "Banner title is required",
               "image_msg": "Banner image is required", "created": "Banner created successfully",
               "deleted": "Banner deleted successfully", "missing": "Banner not found"},
    "promo": {"collection": "promocards", "base": "/api/promo-card", "create": "/create-promo-card",
              "public": "/get-promo-card", "all": "/get-all-promo-card", "delete": "/delete-promo-card",
              "title_msg": "Promo card title is required", "image_msg": "Promo card image is required",
              "created": "Promotional card created successfully", "deleted": "Promotional card deleted successfully",
              "missing": "Promo card not found"},
}


@pytest.fixture(params=list(KINDS))
def k(request):
    return KINDS[request.param] | {"name": request.param}


async def create(client, k, data, files=None):
    return await client.post(k["base"] + k["create"], data=data, files=files if files is not None else image_file(),
                             headers=API_ORIGIN)


async def seed(db, k, title, order, status=True, minutes=0):
    doc = {"title": title, "subtitle": "", "image": f"/uploads/{title}.png", "buttonText": "Shop Now", "buttonLink": "/shop",
           "order": order, "status": status, **new_meta(now_ist() - timedelta(minutes=minutes))}
    if k["name"] == "promo":
        doc["background"] = "#08aaa6"
    await db[k["collection"]].insert_one(doc)


async def test_create(client, app, k):
    await login_as(client, app, role="admin")
    r = await create(client, k, {"title": " Festive ", "subtitle": " Up to 30% ", "order": "2"})
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True and body["message"] == k["created"]
    data = body["data"]
    assert data["title"] == "Festive" and data["subtitle"] == "Up to 30%" and data["order"] == 2
    assert data["buttonText"] == "Shop Now" and data["buttonLink"] == "/shop" and data["status"] is True
    if k["name"] == "promo":
        assert data["background"] == "#08aaa6"


async def test_create_response_shape(client, app, k):
    await login_as(client, app, role="admin")
    data = (await create(client, k, {"title": "T", "order": "abc", "status": "false"})).json()["data"]
    assert data["order"] == 0 and data["status"] is False and data["__v"] == 0


async def test_create_missing_title(client, app, k):
    await login_as(client, app, role="admin")
    for title in ("", "   "):
        r = await create(client, k, {"title": title})
        assert r.status_code == 400 and r.json() == {"success": False, "message": k["title_msg"]}


async def test_create_missing_image(client, app, k):
    await login_as(client, app, role="admin")
    r = await client.post(k["base"] + k["create"], data={"title": "T"}, headers=API_ORIGIN)
    assert r.status_code == 400 and r.json()["message"] == k["image_msg"]


async def test_create_rejects_dangerous_link(client, app, k):
    await login_as(client, app, role="admin")
    r = await create(client, k, {"title": "T", "buttonLink": "javascript:alert(1)"})
    assert r.status_code == 400 and r.json()["message"] == "Button link must start with / or http(s)://"
    assert (await create(client, k, {"title": "T", "buttonLink": "https://example.com/sale"})).status_code == 201


async def test_promo_rejects_bad_background(client, app):
    await login_as(client, app, role="admin")
    r = await create(client, KINDS["promo"], {"title": "T", "background": "red;}"})
    assert r.status_code == 400


async def test_create_requires_admin(client, app, k):
    assert (await create(client, k, {"title": "T"})).status_code == 401
    await login_as(client, app)
    assert (await create(client, k, {"title": "T"})).status_code == 403


async def test_public_list_active_sorted(client, app, k):
    db = app.state.db
    await seed(db, k, "b-order1", 1)
    await seed(db, k, "a-order0-old", 0, minutes=10)
    await seed(db, k, "c-order0-new", 0)
    await seed(db, k, "hidden", 0, status=False)
    r = await client.get(k["base"] + k["public"])
    assert [d["title"] for d in r.json()["data"]] == ["c-order0-new", "a-order0-old", "b-order1"]
    assert r.json()["success"] is True


async def test_all_admin_only_sorted(client, app, k):
    db = app.state.db
    await seed(db, k, "on", 1)
    await seed(db, k, "off", 0, status=False)
    assert (await client.get(k["base"] + k["all"])).status_code == 401
    await login_as(client, app, role="admin")
    assert [d["title"] for d in (await client.get(k["base"] + k["all"])).json()["data"]] == ["off", "on"]


async def test_delete(client, app, k):
    await login_as(client, app, role="admin")
    data = (await create(client, k, {"title": "T"})).json()["data"]
    r = await client.delete(f"{k['base']}{k['delete']}/{data['_id']}", headers=API_ORIGIN)
    assert r.json() == {"success": True, "message": k["deleted"]}
    assert list(app.state.settings.upload_dir.iterdir()) == []
    assert await app.state.db[k["collection"]].count_documents({}) == 0


async def test_delete_not_found_404(client, app, k):
    await login_as(client, app, role="admin")
    r = await client.delete(f"{k['base']}{k['delete']}/{ObjectId()}", headers=API_ORIGIN)
    assert r.status_code == 404 and r.json()["message"] == k["missing"]


async def test_delete_invalid_id_400(client, app, k):
    await login_as(client, app, role="admin")
    r = await client.delete(f"{k['base']}{k['delete']}/abc", headers=API_ORIGIN)
    assert r.status_code == 400 and "Cast to ObjectId" not in r.text

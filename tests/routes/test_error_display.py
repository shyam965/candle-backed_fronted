"""Cross-cutting error display (FR-UI-126, FR-UI-127, D-20)."""

from __future__ import annotations

import json

from app.services import category_service
from tests.helpers import hx, login_as


async def test_service_error_message_in_toast(client, app):
    await login_as(client, app, role="admin")
    r = await client.delete("/admin/categories/abc", headers=await hx(client, app))
    assert json.loads(r.headers["HX-Trigger"])["toast"]["items"] == [{"type": "error", "message": "Invalid category ID"}]


async def test_htmx_error_status_codes(client, app, monkeypatch):
    await login_as(client, app, role="admin")

    async def boom(*args, **kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(category_service, "delete", boom)
    from bson import ObjectId

    r = await client.delete(f"/admin/categories/{ObjectId()}", headers=await hx(client, app))
    assert r.status_code == 500 and "secret internals" not in r.text + r.headers["HX-Trigger"]
    assert "Something went wrong" in r.headers["HX-Trigger"]


async def test_unexpected_page_error_shows_branded_500(client, app, monkeypatch):
    from app.web import pages

    async def boom(*args, **kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(pages, "render", boom)
    r = await client.get("/about")
    assert r.status_code == 500 and "Something went wrong" in r.text and "secret internals" not in r.text


async def test_api_unexpected_error_generic(client, app, monkeypatch):
    await login_as(client, app)
    from app.services import cart_service

    async def boom(*args, **kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(cart_service, "load", boom)
    r = await client.get("/api/cart")
    assert r.status_code == 500 and r.json() == {"success": False, "message": "Something went wrong. Please try again."}

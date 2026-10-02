"""Platform behaviour: health, CORS, limits, 404s, routing, indexes, startup, headers, uploads serving."""

from __future__ import annotations

import logging

import pytest
from asgi_lifespan import LifespanManager

from app.db import DatabaseUnavailable
from app.main import create_app
from tests.helpers import PNG


async def test_healthz(client):
    for path in ("/healthz", "/api"):
        r = await client.get(path)
        assert r.status_code == 200 and r.json() == {"msg": "api is working"}


async def test_cors_allowed_origin(client):
    r = await client.get("/api", headers={"Origin": "https://spa.example"})
    assert r.headers["access-control-allow-origin"] == "https://spa.example"
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in r.headers["vary"]


async def test_cors_unknown_origin_no_headers(client):
    r = await client.get("/api", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    r = await client.get("/healthz", headers={"Origin": "https://spa.example"})
    assert "access-control-allow-origin" not in r.headers  # CORS only on /api


async def test_cors_preflight_204(client):
    r = await client.options("/api/cart/add", headers={
        "Origin": "https://spa.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 204
    assert r.headers["access-control-allow-methods"] == "GET,HEAD,PUT,PATCH,POST,DELETE"
    assert r.headers["access-control-allow-headers"] == "content-type"
    assert r.headers["access-control-allow-origin"] == "https://spa.example"


async def test_body_over_limit_413(client):
    big = b"{" + b" " * (10 * 1024 * 1024 + 10) + b"}"
    r = await client.post("/api/auth/login", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["success"] is False


async def test_unknown_page_404_html(client):
    r = await client.get("/definitely-not-here")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"]
    assert "This flame has gone out" in r.text and "<header" in r.text and "<footer" in r.text


async def test_unknown_api_404_json(client):
    r = await client.get("/api/unknown")
    assert r.status_code == 404 and r.json() == {"success": False, "message": "Not found"}


async def test_case_insensitive_and_trailing_slash(client):
    assert (await client.get("/HealthZ/")).status_code == 200
    assert (await client.get("/API/")).json() == {"msg": "api is working"}


async def test_indexes_created(db):
    async def keys(name):
        return {tuple(i["key"].items()): i for i in [x async for x in await db[name].list_indexes()]}

    assert keys and (await keys("users"))[(("email", 1),)]["unique"]
    assert (await keys("categories"))[(("name", 1),)]["unique"]
    assert (await keys("carts"))[(("user", 1),)]["unique"]
    orders = await keys("orders")
    assert orders[(("orderId", 1),)]["unique"] and (("user", 1),) in orders
    assert (await keys("sessions"))[(("expiresAt", 1),)]["expireAfterSeconds"] == 0
    assert (await keys("rate_limits"))[(("expiresAt", 1),)]["expireAfterSeconds"] == 0


async def test_startup_exits_when_db_unreachable(settings, caplog):
    bad = settings.model_copy(update={"mongo_uri": "mongodb://127.0.0.1:1", "mongo_timeout_ms": 300})
    app = create_app(bad)
    with caplog.at_level(logging.ERROR, logger="akrf.db"), pytest.raises(DatabaseUnavailable):
        async with LifespanManager(app):
            pass
    assert any(r.message.startswith("MongoDB connection failed:") for r in caplog.records)


async def test_security_headers(client):
    r = await client.get("/definitely-not-here")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]


async def test_csrf_cookie_issued_httponly(client):
    r = await client.get("/healthz")
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("akrf_csrf=") and "HttpOnly" in cookie and "Secure" in cookie


# ---------- /uploads (FR-006, D-13) ----------

async def test_serves_file(client, app):
    (app.state.settings.upload_dir / "1790670860904-253178900.png").write_bytes(PNG)
    r = await client.get("/uploads/1790670860904-253178900.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "public, max-age=0" and r.headers["etag"]


async def test_uploads_keep_filename_case(client, app):
    (app.state.settings.upload_dir / "1790-1.JPEG").write_bytes(b"\xff\xd8\xff")
    assert (await client.get("/uploads/1790-1.JPEG")).status_code == 200


async def test_missing_404(client):
    assert (await client.get("/uploads/nope.png")).status_code == 404


async def test_traversal_and_dotfiles_404(client, app):
    (app.state.settings.upload_dir / ".env").write_text("SECRET=1")
    for path in ("/uploads/.env", "/uploads/..%2f..%2fpyproject.toml", "/uploads/%2e%2e"):
        assert (await client.get(path)).status_code == 404

"""Authentication / authorisation guards and router-wide CSRF + role coverage (FR-028–FR-033, D-06, D-45, D-52)."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi.routing import APIRoute

from app.core.documents import now_ist
from app.security.csrf import api_origin_check, csrf_protect
from app.security.deps import require_admin
from app.security.sessions import hash_token
from tests.helpers import API_ORIGIN, hx, login_as, make_user

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def iter_routes(app):
    """(path, methods, dependant) for every endpoint, including those inside included routers."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            yield route.path, set(route.methods or ()), route.dependant
        elif hasattr(route, "effective_route_contexts"):
            for ctx in route.effective_route_contexts():
                yield ctx.path, set(ctx.methods or ()), ctx.dependant


def _deps(dependant) -> set:
    found, stack = set(), [dependant]
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            found.add(dep.call)
        stack.extend(dep.dependencies)
    return found


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "66fa1e119d3e4a0012ab3601", path)


async def test_all_unsafe_ui_routes_require_csrf(client, app):
    await login_as(client, app, role="admin")
    checked = 0
    for path, methods, dependant in iter_routes(app):
        if path.startswith("/api"):
            continue
        for method in methods & UNSAFE:
            assert csrf_protect in _deps(dependant), f"{method} {path} lacks CSRF"
            r = await client.request(method, _concrete(path), headers={"HX-Request": "true"})
            assert r.status_code == 403, f"{method} {path} accepted a request without a CSRF token"
            checked += 1
    assert checked >= 20


async def test_api_write_requires_allowed_origin(client, app):
    await login_as(client, app, role="admin")
    checked = 0
    for path, methods, dependant in iter_routes(app):
        if path.startswith("/api/"):
            assert api_origin_check in _deps(dependant), path
            for method in methods & UNSAFE:
                r = await client.request(method, _concrete(path), headers={"Origin": "https://evil.example"})
                assert r.status_code == 403, f"{method} {path}"
                checked += 1
    assert checked >= 20


async def test_all_admin_routes_require_admin(client, app):
    await login_as(client, app)  # ordinary customer
    admin_api = {"/api/category/create-category", "/api/category/update-category/{category_id}",
                 "/api/category/delete-category/{category_id}", "/api/product/create-product",
                 "/api/product/update-product/{product_id}", "/api/product/delete-product/{product_id}",
                 "/api/banner/create-banner", "/api/banner/get-all-banner", "/api/banner/delete-banner/{item_id}",
                 "/api/promo-card/create-promo-card", "/api/promo-card/get-all-promo-card",
                 "/api/promo-card/delete-promo-card/{item_id}", "/api/order/all", "/api/order/status/{order_id}"}
    seen = set()
    for path, methods, dependant in iter_routes(app):
        if path.startswith("/admin") or path in admin_api:
            assert require_admin in _deps(dependant), path
            seen.add(path)
            for method in methods:
                headers = {**(await hx(client, app)), **API_ORIGIN}
                r = await client.request(method, _concrete(path), headers=headers)
                assert r.status_code == 403, f"{method} {path} -> {r.status_code}"
    assert admin_api <= seen


async def test_authorization_header_ignored(client, app):
    user = await make_user(app.state.db)
    from app.security.sessions import create_session

    token = await create_session(app.state.db, user["_id"], app.state.settings)
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and r.json()["message"] == "Please login first"


async def test_api_no_cookie_401(client):
    assert (await client.get("/api/cart")).json() == {"success": False, "message": "Please login first"}


async def test_page_redirects_to_login(client):
    r = await client.get("/my-orders")
    assert r.status_code == 303 and r.headers["location"] == "/login?redirect=%2Fmy-orders"


async def test_invalid_session_401(client):
    client.cookies.set("akrf_session", "forged-token")
    assert (await client.get("/api/auth/me")).json()["message"] == "Invalid or expired session"


async def test_expired_session_401(client, app):
    await login_as(client, app)
    await app.state.db.sessions.update_many({}, {"$set": {"expiresAt": now_ist() - timedelta(seconds=1)}})
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["message"] == "Invalid or expired session"


async def test_deleted_user_401(client, app):
    user = await login_as(client, app)
    await app.state.db.users.delete_one({"_id": user["_id"]})
    assert (await client.get("/api/auth/me")).json()["message"] == "User not found"


async def test_role_change_takes_effect_immediately(client, app):
    user = await login_as(client, app)
    assert (await client.get("/api/order/all")).status_code == 403
    await app.state.db.users.update_one({"_id": user["_id"]}, {"$set": {"role": "admin"}})
    assert (await client.get("/api/order/all")).status_code == 200


async def test_user_resolved_per_request(client, app):
    await login_as(client, app, name="Before")
    assert "Before" in (await client.get("/about")).text
    await app.state.db.users.update_many({}, {"$set": {"name": "After"}})
    assert "After" in (await client.get("/about")).text


async def test_non_admin_api_403(client, app):
    await login_as(client, app)
    r = await client.get("/api/banner/get-all-banner")
    assert r.status_code == 403 and r.json() == {"success": False, "message": "Admin access required"}


async def test_non_admin_htmx_403(client, app):
    await login_as(client, app)
    r = await client.get("/admin/_p/stats", headers={"HX-Request": "true"})
    assert r.status_code == 403 and "Admin access required" in r.headers["HX-Trigger"]


async def test_admin_page_anonymous_redirects_login(client):
    r = await client.get("/admin")
    assert r.status_code == 303 and r.headers["location"] == "/login?redirect=%2Fadmin"


async def test_admin_page_non_admin_redirects_home(client, app):
    await login_as(client, app)
    r = await client.get("/admin/orders")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "Admin access required" in (await client.get("/about")).text


async def test_admin_guard_resolves_before_render(client, app):
    await login_as(client, app, role="admin")
    text = (await client.get("/admin")).text
    assert "Checking admin access" not in text and "Dashboard" in text


async def test_session_cookie_rotated_on_login(client, app):
    from tests.helpers import PASSWORD

    old = await login_as(client, app, email="asha@example.com")
    old_token = client.cookies.get("akrf_session")
    await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD}, headers=await hx(client, app))
    assert await app.state.db.sessions.find_one({"_id": hash_token(old_token)}) is None and old

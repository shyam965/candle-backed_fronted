"""Login / register / logout pages (FR-UI-012–FR-023, D-44)."""

from __future__ import annotations

import json

import pytest

from tests.helpers import PASSWORD, hx, login_as, make_user


def toasts(response):
    return [t["message"] for t in json.loads(response.headers.get("HX-Trigger", "{}")).get("toast", {}).get("items", [])]


async def test_login_page_renders(client):
    r = await client.get("/login?redirect=%2Fcart")
    assert r.status_code == 200
    assert 'name="redirect" value="/cart"' in r.text and 'hx-post="/login"' in r.text


async def test_login_empty_fields(client, app):
    r = await client.post("/login", data={"email": "  ", "password": ""}, headers=await hx(client, app))
    assert r.status_code == 422
    assert "Please enter email and password" in r.text and "Login Failed" in r.text
    assert toasts(r) == ["Please enter email and password"]


async def test_login_failure_alert_and_toast(client, app):
    await make_user(app.state.db, email="asha@example.com")
    r = await client.post("/login", data={"email": "asha@example.com", "password": "nope!!"}, headers=await hx(client, app))
    assert r.status_code == 422 and "Invalid email or password" in r.text
    assert 'value="asha@example.com"' in r.text  # entered value preserved
    assert toasts(r) == ["Invalid email or password"]


async def test_login_error_has_clear_on_input_hook(client, app):
    r = await client.post("/login", data={"email": "", "password": ""}, headers=await hx(client, app))
    assert 'data-clear-on-input="#login-error"' in r.text and 'id="login-error"' in r.text


async def test_login_success_trims_email(client, app):
    await make_user(app.state.db, email="asha@example.com")
    r = await client.post("/login", data={"email": " asha@example.com ", "password": PASSWORD}, headers=await hx(client, app))
    assert r.status_code == 200 and r.headers["HX-Redirect"] == "/"
    assert "akrf_session=" in r.headers.get("set-cookie", "")


@pytest.mark.parametrize("role,redirect_to,expected", [
    ("user", "", "/"),
    ("admin", "", "/admin"),
    ("user", "/cart", "/cart"),
    ("admin", "/admin/orders", "/admin/orders"),
    ("admin", "/my-orders", "/my-orders"),
    ("user", "/admin/orders", "/"),
])
async def test_login_redirect_rules(client, app, role, redirect_to, expected):
    await make_user(app.state.db, email="asha@example.com", role=role)
    r = await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD, "redirect": redirect_to},
                          headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == expected


@pytest.mark.parametrize("evil", ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
async def test_login_rejects_open_redirect(client, app, evil):
    await make_user(app.state.db, email="asha@example.com")
    r = await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD, "redirect": evil},
                          headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == "/"


async def test_login_sets_flash_toast_for_next_page(client, app):
    await make_user(app.state.db, email="asha@example.com")
    await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD}, headers=await hx(client, app))
    page = await client.get("/login")
    assert "Login successful!" in page.text


async def test_login_without_htmx_uses_form_field_csrf(client, app):
    await make_user(app.state.db, email="asha@example.com")
    from tests.helpers import csrf_token

    token = await csrf_token(client, app)
    r = await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD, "csrf_token": token})
    assert r.status_code == 303 and r.headers["location"] == "/"


async def test_login_requires_csrf(client, app):
    r = await client.post("/login", data={"email": "a@b.co", "password": "x"}, headers={"HX-Request": "true"})
    assert r.status_code == 403
    assert "Your session has expired" in toasts(r)[0]


async def test_register_missing_fields(client, app):
    r = await client.post("/register", data={"name": " ", "email": "a@b.co", "password": "secret1", "confirm_password": ""},
                          headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Please fill all required fields"]
    assert r.text.count("This field is required") == 2


async def test_register_mismatch_and_short_password(client, app):
    base = {"name": "Asha", "email": "a@b.co", "phone": ""}
    r = await client.post("/register", data={**base, "password": "123", "confirm_password": "123"}, headers=await hx(client, app))
    assert toasts(r) == ["Password must be at least 6 characters"]
    r = await client.post("/register", data={**base, "password": "secret1", "confirm_password": "secret2"},
                          headers=await hx(client, app))
    assert toasts(r) == ["Passwords do not match"] and 'value="Asha"' in r.text


async def test_register_live_validation_hooks(client):
    r = await client.get("/register")
    assert "data-live-register" in r.text and 'name="confirm_password"' in r.text


async def test_register_stores_trimmed_no_confirm(client, app):
    r = await client.post("/register", data={"name": " Asha ", "email": " A@B.co ", "phone": " 9876543210 ",
                                             "password": "secret1", "confirm_password": "secret1"},
                          headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == "/"
    stored = await app.state.db.users.find_one({"email": "a@b.co"})
    assert stored["name"] == "Asha" and stored["phone"] == "9876543210" and "confirm_password" not in stored


async def test_register_success_logs_in(client, app):
    await client.post("/register", data={"name": "Asha", "email": "a@b.co", "password": "secret1",
                                         "confirm_password": "secret1"}, headers=await hx(client, app))
    page = await client.get("/login")
    assert "Account created successfully!" in page.text and "My Orders" in page.text


async def test_register_duplicate_message(client, app):
    await make_user(app.state.db, email="a@b.co")
    r = await client.post("/register", data={"name": "Asha", "email": "a@b.co", "password": "secret1",
                                             "confirm_password": "secret1"}, headers=await hx(client, app))
    assert r.status_code == 422 and toasts(r) == ["Email already registered"]


async def test_logout_redirects_home_with_toast(client, app):
    await login_as(client, app)
    r = await client.post("/logout", headers=await hx(client, app))
    assert r.headers["HX-Redirect"] == "/"
    assert (await client.get("/api/auth/me")).status_code == 401
    assert "Logout successful" in (await client.get("/login")).text


async def test_submit_buttons_busy_labels(client, app):
    assert "Logging in..." in (await client.get("/login")).text
    assert "Creating account..." in (await client.get("/register")).text
    await login_as(client, app)
    assert "Logging out..." in (await client.get("/login")).text


async def test_login_rate_limit_message(client, app):
    await make_user(app.state.db, email="asha@example.com")
    for _ in range(5):
        await client.post("/login", data={"email": "asha@example.com", "password": "bad!!!"}, headers=await hx(client, app))
    r = await client.post("/login", data={"email": "asha@example.com", "password": PASSWORD}, headers=await hx(client, app))
    assert r.status_code == 422 and "Too many attempts" in r.text

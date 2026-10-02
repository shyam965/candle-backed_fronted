"""`/api/auth/*` (FR-013–FR-025, FR-034–FR-036, D-04, D-07)."""

from __future__ import annotations

import pytest

from app.services import auth_service
from tests.helpers import API_ORIGIN, PASSWORD, login_as, make_user

REG = {"name": "  Asha Verma ", "email": "  Asha@Example.COM ", "phone": " 9876543210 ", "password": "secret1"}


async def post(client, path, body):
    return await client.post(path, json=body, headers=API_ORIGIN)


@pytest.mark.parametrize("missing", ["name", "email", "password"])
async def test_register_missing_fields(client, missing):
    body = {**REG, missing: ""}
    r = await post(client, "/api/auth/register", body)
    assert r.status_code == 400
    assert r.json() == {"success": False, "message": "Name, email and password are required"}


async def test_register_whitespace_name_and_non_string_rejected(client):
    assert (await post(client, "/api/auth/register", {**REG, "name": "   "})).status_code == 400
    r = await post(client, "/api/auth/register", {**REG, "password": 1234567})
    assert r.status_code == 400 and r.json()["success"] is False


async def test_register_short_password(client):
    r = await post(client, "/api/auth/register", {**REG, "password": "12345"})
    assert r.status_code == 400 and r.json()["message"] == "Password must be at least 6 characters"


async def test_register_invalid_email_and_phone(client):
    assert (await post(client, "/api/auth/register", {**REG, "email": "nope"})).json()["message"] == \
        "Please enter a valid email address"
    assert (await post(client, "/api/auth/register", {**REG, "phone": "12345"})).json()["message"] == \
        "Please enter a valid 10 digit mobile number"


async def test_register_success_sets_session(client, db):
    r = await post(client, "/api/auth/register", REG)
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True and body["message"] == "Account created successfully"
    assert body["user"]["email"] == "asha@example.com" and body["user"]["role"] == "user"
    assert body["user"]["id"] == body["user"]["_id"]
    assert set(body["user"]) == {"id", "_id", "name", "email", "phone", "address", "city", "pincode", "role"}
    assert "akrf_session=" in r.headers["set-cookie"]
    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["user"]["name"] == "Asha Verma"


async def test_register_trims_fields(client, db):
    await post(client, "/api/auth/register", REG)
    stored = await db.users.find_one({"email": "asha@example.com"})
    assert stored["name"] == "Asha Verma" and stored["phone"] == "9876543210"
    assert stored["address"] == stored["city"] == stored["pincode"] == "" and stored["__v"] == 0
    assert stored["password"].startswith("$2a$10$")


async def test_register_ignores_role(client, db):
    await post(client, "/api/auth/register", {**REG, "role": "admin"})
    assert (await db.users.find_one({"email": "asha@example.com"}))["role"] == "user"


async def test_register_duplicate_409(client, db):
    await make_user(db, email="asha@example.com")
    r = await post(client, "/api/auth/register", REG)
    assert r.status_code == 409 and r.json()["message"] == "Email already registered"


async def test_register_unexpected_error_generic(client, monkeypatch):
    async def boom(db, data):
        raise RuntimeError("db exploded: secret detail")

    monkeypatch.setattr(auth_service, "register", boom)
    r = await post(client, "/api/auth/register", REG)
    assert r.status_code == 500 and r.json() == {"success": False, "message": "Registration failed"}


async def test_email_normalised(client, db):
    await make_user(db, email="asha@example.com")
    r = await post(client, "/api/auth/login", {"email": "  ASHA@example.com ", "password": PASSWORD})
    assert r.status_code == 200


@pytest.mark.parametrize("body", [{"email": "", "password": "x"}, {"email": "a@b.co"}, {}])
async def test_login_missing_fields(client, body):
    r = await post(client, "/api/auth/login", body)
    assert r.status_code == 400 and r.json()["message"] == "Email and password are required"


async def test_login_invalid_credentials(client, db):
    await make_user(db, email="asha@example.com")
    for body in ({"email": "asha@example.com", "password": "wrong!"}, {"email": "nobody@example.com", "password": "x"}):
        r = await post(client, "/api/auth/login", body)
        assert r.status_code == 401 and r.json() == {"success": False, "message": "Invalid email or password"}


async def test_login_success_profile_and_cookie(client, db):
    user = await make_user(db, email="asha@example.com", address="12 MG Road", city="Jaipur", pincode="302001")
    r = await post(client, "/api/auth/login", {"email": "asha@example.com", "password": PASSWORD})
    body = r.json()
    assert r.status_code == 200 and body["message"] == "Login successful"
    assert body["user"]["id"] == str(user["_id"]) and body["user"]["city"] == "Jaipur"
    cookie = r.headers["set-cookie"]
    assert "akrf_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "Max-Age=604800" in cookie


async def test_login_unexpected_error_generic(client, monkeypatch):
    async def boom(db, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_service, "authenticate", boom)
    r = await post(client, "/api/auth/login", {"email": "a@b.co", "password": "secret1"})
    assert r.status_code == 500 and r.json() == {"success": False, "message": "Login failed"}


async def test_me_returns_profile(client, app):
    user = await login_as(client, app, role="admin")
    r = await client.get("/api/auth/me")
    assert r.json() == {"success": True, "user": {
        "id": str(user["_id"]), "_id": str(user["_id"]), "name": user["name"], "email": user["email"],
        "phone": user["phone"], "address": "", "city": "", "pincode": "", "role": "admin"}}


async def test_me_anonymous_401(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json() == {"success": False, "message": "Please login first"}


async def test_logout_invalidates_session(client, app):
    await login_as(client, app)
    token = client.cookies.get("akrf_session")
    r = await client.post("/api/auth/logout", headers=API_ORIGIN)
    assert r.json() == {"success": True, "message": "Logout successful"}
    client.cookies.set("akrf_session", token)  # replaying the old token fails (KI-05)
    assert (await client.get("/api/auth/me")).json()["message"] == "Invalid or expired session"


async def test_logout_without_session(client):
    assert (await client.post("/api/auth/logout", headers=API_ORIGIN)).status_code == 200


async def test_password_never_returned(client, app):
    await login_as(client, app)
    assert "password" not in (await client.get("/api/auth/me")).text


async def test_api_write_requires_allowed_origin(client, db):
    r = await client.post("/api/auth/login", json={"email": "a@b.co", "password": "secret1"})
    assert r.status_code == 403 and r.json()["message"] == "Request origin not allowed"
    r = await client.post("/api/auth/login", json={"email": "a@b.co", "password": "secret1"},
                          headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = await client.post("/api/auth/login", json={"email": "a@b.co", "password": "secret1"},
                          headers={"Origin": "https://spa.example"})
    assert r.status_code == 401


async def test_invalid_json_body(client):
    r = await client.post("/api/auth/login", content=b"{bad", headers={**API_ORIGIN, "content-type": "application/json"})
    assert r.status_code == 400 and r.json()["message"] == "Invalid JSON body"


async def test_urlencoded_body_accepted(client, db):
    await make_user(db, email="asha@example.com")
    r = await client.post("/api/auth/login", data={"email": "asha@example.com", "password": PASSWORD}, headers=API_ORIGIN)
    assert r.status_code == 200


async def test_login_rate_limited(client, db):
    await make_user(db, email="asha@example.com")
    for _ in range(5):
        assert (await post(client, "/api/auth/login", {"email": "asha@example.com", "password": "bad!!!"})).status_code == 401
    r = await post(client, "/api/auth/login", {"email": "asha@example.com", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["message"].startswith("Too many attempts")


async def test_register_rate_limited(client):
    for i in range(10):
        await post(client, "/api/auth/register", {**REG, "email": f"u{i}@example.com"})
    r = await post(client, "/api/auth/register", {**REG, "email": "late@example.com"})
    assert r.status_code == 429

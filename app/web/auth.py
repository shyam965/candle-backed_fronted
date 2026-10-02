"""Login, registration and logout pages (FE §4.3–4.5, FR-UI-012–FR-023, D-44)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response

from app.api.common import client_ip
from app.core.errors import AppError
from app.core.links import safe_redirect
from app.core.templating import render
from app.security.deps import is_admin
from app.security.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
)
from app.services import auth_service
from app.web.common import form_data, redirect, respond_form, ui_router

router = ui_router()


def post_login_target(user: dict[str, Any], requested: str | None) -> str:
    target = safe_redirect(requested)
    if target and not target.startswith(("/login", "/register", "/logout")):
        if target.startswith("/admin") and not is_admin(user):
            return "/"
        return target
    return "/admin" if is_admin(user) else "/"


async def _start_session(request: Request, response: Response, user: dict[str, Any]) -> None:
    db, settings = request.app.state.db, request.app.state.settings
    await delete_session(db, request.cookies.get(SESSION_COOKIE))
    token = await create_session(db, user["_id"], settings)
    set_session_cookie(response, token, settings)


# ---------- login ----------

@router.get("/login")
async def login_page(request: Request) -> Response:
    redirect_to = safe_redirect(request.query_params.get("redirect")) or ""
    return await render(request, "pages/auth/login.html", {"values": {}, "redirect": redirect_to})


@router.post("/login")
async def login_submit(request: Request) -> Response:
    db, settings = request.app.state.db, request.app.state.settings
    data = await form_data(request)
    email, password = data.get("email", ""), data.get("password", "")
    redirect_to = safe_redirect(data.get("redirect")) or ""
    context: dict[str, Any] = {"values": {"email": email}, "redirect": redirect_to}

    async def failed(message: str) -> Response:
        return await respond_form(request, page="pages/auth/login.html", partial="partials/auth/login_form.html",
                                  context={**context, "error": message}, toast_message=message)

    if not email.strip() or not password:
        return await failed("Please enter email and password")
    ip = client_ip(request)
    try:
        await auth_service.guard_login(db, settings, ip, data)
        user = await auth_service.authenticate(db, {"email": email.strip(), "password": password})
    except AppError as exc:
        if exc.status_code == 401:
            await auth_service.record_login_failure(db, ip, data)
        return await failed(exc.message)
    response = redirect(request, post_login_target(user, redirect_to), "Login successful!")
    await _start_session(request, response, user)
    return response


# ---------- register ----------

@router.get("/register")
async def register_page(request: Request) -> Response:
    redirect_to = safe_redirect(request.query_params.get("redirect")) or ""
    return await render(request, "pages/auth/register.html", {"values": {}, "errors": {}, "redirect": redirect_to})


@router.post("/register")
async def register_submit(request: Request) -> Response:
    db, settings = request.app.state.db, request.app.state.settings
    data = await form_data(request)
    values = {k: data.get(k, "") for k in ("name", "email", "phone")}
    password, confirm = data.get("password", ""), data.get("confirm_password", "")
    redirect_to = safe_redirect(data.get("redirect")) or ""

    async def failed(message: str, errors: dict[str, str]) -> Response:
        return await respond_form(
            request, page="pages/auth/register.html", partial="partials/auth/register_form.html",
            context={"values": values, "errors": errors, "redirect": redirect_to}, toast_message=message,
        )

    required = {"name": values["name"].strip(), "email": values["email"].strip(), "password": password,
                "confirm_password": confirm}
    missing = {k: "This field is required" for k, v in required.items() if not v}
    if missing:
        return await failed("Please fill all required fields", missing)
    if len(password) < 6:
        return await failed("Password must be at least 6 characters",
                            {"password": "Password must be at least 6 characters"})
    if password != confirm:
        return await failed("Passwords do not match", {"confirm_password": "Passwords do not match"})
    try:
        await auth_service.guard_register(db, settings, client_ip(request))
        user = await auth_service.register(db, {"name": values["name"], "email": values["email"],
                                                "phone": values["phone"], "password": password})
    except AppError as exc:
        return await failed(exc.message, exc.errors)
    target = post_login_target(user, redirect_to) if redirect_to else "/"
    response = redirect(request, target, "Account created successfully!")
    await _start_session(request, response, user)
    return response


# ---------- logout ----------

@router.post("/logout")
async def logout(request: Request) -> Response:
    await delete_session(request.app.state.db, request.cookies.get(SESSION_COOKIE))
    response = redirect(request, "/", "Logout successful")
    clear_session_cookie(response, request.app.state.settings)
    return response

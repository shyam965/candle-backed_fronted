"""`/api/auth/*` — JSON compatibility endpoints (BE §6.2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import client_ip, ok, read_body
from app.core.errors import AppError
from app.core.handlers import api_error
from app.security.csrf import api_origin_check
from app.security.deps import require_user
from app.security.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
)
from app.services import auth_service

log = logging.getLogger("akrf.api.auth")
router = APIRouter(prefix="/api/auth", dependencies=[Depends(api_origin_check)])


async def _start_session(request: Request, response: JSONResponse, user: dict) -> None:
    db, settings = request.app.state.db, request.app.state.settings
    await delete_session(db, request.cookies.get(SESSION_COOKIE))
    token = await create_session(db, user["_id"], settings)
    set_session_cookie(response, token, settings)


@router.post("/register")
async def register(request: Request) -> JSONResponse:
    db, settings = request.app.state.db, request.app.state.settings
    data = await read_body(request)
    await auth_service.guard_register(db, settings, client_ip(request))
    try:
        user = await auth_service.register(db, data)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - FR-021 generic failure message
        log.error("Register Error: %s", type(exc).__name__)
        return api_error(request, 500, "Registration failed")
    response = ok({"success": True, "message": "Account created successfully",
                   "user": auth_service.public_profile(user)}, 201)
    await _start_session(request, response, user)
    return response


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    db, settings = request.app.state.db, request.app.state.settings
    data = await read_body(request)
    ip = client_ip(request)
    await auth_service.guard_login(db, settings, ip, data)
    try:
        user = await auth_service.authenticate(db, data)
    except AppError as exc:
        if exc.status_code == 401:
            await auth_service.record_login_failure(db, ip, data)
        raise
    except Exception as exc:  # noqa: BLE001 - FR-025 generic failure message
        log.error("Login Error: %s", type(exc).__name__)
        return api_error(request, 500, "Login failed")
    response = ok({"success": True, "message": "Login successful", "user": auth_service.public_profile(user)})
    await _start_session(request, response, user)
    return response


@router.get("/me")
async def me(user: dict = Depends(require_user)) -> JSONResponse:
    return ok({"success": True, "user": auth_service.public_profile(user)})


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    await delete_session(request.app.state.db, request.cookies.get(SESSION_COOKIE))
    response = ok({"success": True, "message": "Logout successful"})
    clear_session_cookie(response, request.app.state.settings)
    return response

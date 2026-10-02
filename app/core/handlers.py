"""Exception handlers: JSON for `/api`, toasts for HTMX, branded pages otherwise (D-20, D-45, D-52)."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AdminRequired, AppError, BodyTooLarge, CsrfFailed, LoginRequired
from app.core.flash import set_flash
from app.core.htmx import current_path, is_htmx, toast
from app.core.links import safe_redirect

log = logging.getLogger("akrf.errors")

GENERIC_500 = "Something went wrong. Please try again."
ERROR_TITLES = {400: "Bad request", 403: "Access denied", 404: "Page not found", 409: "Conflict",
                413: "Too large", 429: "Too many requests", 500: "Something went wrong"}


def is_api(request: Request) -> bool:
    return request.url.path == "/api" or request.url.path.startswith("/api/")


def api_error(request: Request, status_code: int, message: str) -> JSONResponse:
    """Error envelope: style A `{success,message}`; style B (category/product) adds `error: true`."""
    if getattr(request.state, "api_style", "A") == "B":
        body = {"message": message, "success": False, "error": True}
    else:
        body = {"success": False, "message": message}
    return JSONResponse(body, status_code=status_code)


def htmx_error(status_code: int, message: str) -> Response:
    response = Response(status_code=status_code)
    toast(response, message, "error")
    return response


async def error_page(request: Request, status_code: int, message: str | None = None) -> HTMLResponse:
    from app.core.templating import render

    template = {404: "errors/404.html", 403: "errors/403.html", 500: "errors/500.html"}.get(
        status_code, "errors/error.html"
    )
    context = {"status_code": status_code, "title": ERROR_TITLES.get(status_code, "Error"), "message": message}
    try:
        return await render(request, template, context, status_code=status_code)
    except Exception:  # noqa: BLE001 - never fail while rendering an error page
        log.exception("Error page rendering failed")
        return HTMLResponse(
            f"<!doctype html><title>{ERROR_TITLES.get(status_code, 'Error')}</title>"
            f"<h1>{ERROR_TITLES.get(status_code, 'Error')}</h1>",
            status_code=status_code,
        )


def login_url(request: Request) -> str:
    target = current_path(request) if is_htmx(request) else (
        request.url.path + (f"?{request.url.query}" if request.url.query else "")
    )
    target = safe_redirect(target)
    if not target or target.startswith("/login") or target == "/":
        return "/login"
    return f"/login?redirect={quote(target, safe='')}"


async def handle_app_error(request: Request, exc: AppError) -> Response:
    if is_api(request):
        return api_error(request, exc.status_code, exc.message)
    if is_htmx(request):
        return htmx_error(exc.status_code, exc.message)
    return await error_page(request, exc.status_code, exc.message)


async def handle_login_required(request: Request, exc: LoginRequired) -> Response:
    if is_api(request):
        return api_error(request, 401, exc.message)
    url = login_url(request)
    if is_htmx(request):
        response = Response(status_code=401)
        response.headers["HX-Redirect"] = url
        return response
    return RedirectResponse(url, status_code=303)


async def handle_admin_required(request: Request, exc: AdminRequired) -> Response:
    if is_api(request):
        return api_error(request, 403, exc.message)
    if is_htmx(request):
        return htmx_error(403, exc.message)
    if request.method in {"GET", "HEAD"}:
        response = RedirectResponse("/", status_code=303)
        set_flash(response, request, exc.message, "error")
        return response
    return await error_page(request, 403, exc.message)


async def handle_csrf(request: Request, exc: CsrfFailed) -> Response:
    if is_htmx(request):
        return htmx_error(403, exc.message)
    return await error_page(request, 403, exc.message)


async def handle_body_too_large(request: Request, exc: BodyTooLarge) -> Response:
    message = "Request body is too large"
    if is_api(request):
        return api_error(request, 413, message)
    if is_htmx(request):
        return htmx_error(413, "The file or form you sent is too large.")
    return await error_page(request, 413, "The file or form you sent is too large.")


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
    status = exc.status_code
    if is_api(request):
        message = {404: "Not found", 405: "Method not allowed"}.get(status, str(exc.detail))
        return api_error(request, status, message)
    if status in {404, 405}:
        if is_htmx(request):
            return htmx_error(404, "Not found")
        return await error_page(request, 404)
    if is_htmx(request):
        return htmx_error(status, str(exc.detail))
    return await error_page(request, status, str(exc.detail))


async def handle_validation(request: Request, exc: RequestValidationError) -> Response:
    if is_api(request):
        return api_error(request, 400, "Invalid request")
    if is_htmx(request):
        return htmx_error(400, "Invalid request")
    return await error_page(request, 404)


async def handle_unexpected(request: Request, exc: Exception) -> Response:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    if is_api(request):
        return api_error(request, 500, GENERIC_500)
    if is_htmx(request):
        return htmx_error(500, GENERIC_500)
    return await error_page(request, 500)


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(LoginRequired, handle_login_required)
    app.add_exception_handler(AdminRequired, handle_admin_required)
    app.add_exception_handler(CsrfFailed, handle_csrf)
    app.add_exception_handler(BodyTooLarge, handle_body_too_large)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation)
    app.add_exception_handler(Exception, handle_unexpected)

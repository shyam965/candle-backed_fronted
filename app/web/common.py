"""Helpers shared by the server-rendered routers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.core.flash import set_flash
from app.core.htmx import hx_redirect, is_htmx, toast
from app.core.templating import render
from app.security.csrf import csrf_protect


def ui_router(**kwargs: Any) -> APIRouter:
    """Every server-rendered router enforces CSRF on unsafe methods (D-06)."""
    dependencies = list(kwargs.pop("dependencies", []))
    return APIRouter(dependencies=[Depends(csrf_protect), *dependencies], **kwargs)


async def respond_form(
    request: Request,
    *,
    page: str,
    partial: str,
    context: dict[str, Any],
    status_code: int = 422,
    toast_message: str | None = None,
) -> Response:
    """Re-render a form with errors: the partial for HTMX (422 is swapped), the full page otherwise."""
    if is_htmx(request):
        response = await render(request, partial, context, status_code=status_code, full_page=False)
    else:
        response = await render(request, page, context, status_code=status_code)
    if toast_message:
        toast(response, toast_message, "error")
    return response


def redirect(request: Request, url: str, message: str | None = None, kind: str = "success") -> Response:
    response: Response = hx_redirect(url) if is_htmx(request) else RedirectResponse(url, status_code=303)
    if message:
        set_flash(response, request, message, kind)
    return response


async def form_data(request: Request) -> dict[str, str]:
    """Text fields of a submitted form (files are read separately)."""
    form = await request.form()
    return {k: v for k, v in form.multi_items() if isinstance(v, str)}

"""Admin → Categories (FE §5.11, FR-UI-103–FR-UI-108)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.htmx import toast
from app.core.templating import render
from app.services import category_service
from app.services.upload_service import extract_image
from app.web.admin import admin_router

log = logging.getLogger("akrf.admin.categories")
router = admin_router(prefix="/admin/categories")

PANEL = "admin/partials/categories_table.html"
FORM = "admin/partials/category_form.html"


async def _table(request: Request, *, q: str = "", message: str | None = None, status_code: int = 200) -> Response:
    context: dict[str, Any] = {"q": q, "message": message}
    try:
        categories = await category_service.list_all(request.app.state.db)
        context["categories"] = [c for c in categories if not q or category_service.matches(c, q)]
        context["total"] = len(categories)
    except PyMongoError:
        log.exception("Failed to fetch categories")
        context["load_error"] = "Failed to fetch categories"
    return await render(request, PANEL, context, status_code=status_code, full_page=False)


async def _form(request: Request, *, category: dict | None, values: dict, errors: dict | None = None,
                error: str | None = None, status_code: int = 200) -> Response:
    return await render(request, FORM, {"category": category, "values": values, "errors": errors or {}, "error": error},
                        status_code=status_code, full_page=False)


@router.get("")
async def page(request: Request) -> Response:
    return await render(request, "admin/categories.html")


@router.get("/_table")
async def table(request: Request, q: str = "") -> Response:
    return await _table(request, q=q.strip()[:100])


@router.get("/new")
async def new_form(request: Request) -> Response:
    return await _form(request, category=None, values={})


@router.get("/{category_id}/edit")
async def edit_form(category_id: str, request: Request) -> Response:
    category = await category_service.get(request.app.state.db, category_id)
    return await _form(request, category=category, values=category)


async def _save(request: Request, category_id: str | None) -> Response:
    db, store, settings = request.app.state.db, request.app.state.uploads, request.app.state.settings
    category = await category_service.get(db, category_id) if category_id else None
    form = await request.form()
    values = {"name": form.get("name") or "", "description": form.get("description") or ""}
    try:
        image = await extract_image(form, settings.max_upload_bytes)
        data = {"name": values["name"], "description": values["description"]}
        if category is None:
            await category_service.create(db, store, data, image, image_message="Please upload a category image")
        else:
            await category_service.update(db, store, category_id, data, image)
    except AppError as exc:
        if exc.status_code == 404:
            raise
        response = await _form(request, category=category, values=values, errors=exc.errors,
                               error=None if exc.errors else exc.message, status_code=422)
        return toast(response, exc.message, "error")
    message = "Category created successfully" if category is None else "Category updated successfully"
    return toast(await _table(request, message=message), message)


@router.post("")
async def create(request: Request) -> Response:
    return await _save(request, None)


@router.put("/{category_id}")
async def update(category_id: str, request: Request) -> Response:
    return await _save(request, category_id)


@router.delete("/{category_id}")
async def delete(category_id: str, request: Request) -> Response:
    await category_service.delete(request.app.state.db, request.app.state.uploads, category_id)
    message = "Category deleted successfully"
    return toast(await _table(request, message=message), message)

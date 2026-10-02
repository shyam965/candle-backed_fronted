"""Admin → Products (FE §5.12, FR-UI-109–FR-UI-113)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.formatting import to_number
from app.core.htmx import toast
from app.core.templating import render
from app.core.validators import Invalid
from app.services import category_service, product_service
from app.services.upload_service import ImageUpload, extract_image
from app.web.admin import admin_router

log = logging.getLogger("akrf.admin.products")
router = admin_router(prefix="/admin/products")

PANEL = "admin/partials/products_table.html"
FORM = "admin/partials/product_form.html"
FIELDS = ("name", "category", "price", "oldPrice", "stock", "description")


def _plain(value: Any) -> str:
    """Show stored numbers without a trailing `.0` in form inputs."""
    number = to_number(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else str(number)


def validate_form(values: dict[str, str], image: ImageUpload | None, creating: bool) -> dict[str, str]:
    """Client-equivalent validation in the documented order (FR-UI-110)."""
    errors: dict[str, str] = {}
    if not values["name"].strip():
        errors["name"] = "Product name is required"
    if not values["category"]:
        errors["category"] = "Please select a category"
    if creating and image is None:
        errors["image"] = "Please upload a product image"
    price = None
    try:
        price = product_service.parse_price(values["price"])
    except Invalid:
        errors["price"] = "Please enter a valid price"
    try:
        product_service.parse_stock(values["stock"])
    except Invalid:
        errors["stock"] = "Please enter valid stock"
    if values["oldPrice"].strip():
        try:
            old_price = product_service.parse_old_price(values["oldPrice"])
            if price is not None and old_price is not None and old_price < price:
                raise Invalid("below price")
        except Invalid:
            errors["oldPrice"] = "Old price must be greater than or equal to selling price"
    return errors


async def _categories(request: Request) -> list[dict[str, Any]]:
    return await category_service.list_all(request.app.state.db)


async def _table(request: Request, *, q: str = "", message: str | None = None) -> Response:
    context: dict[str, Any] = {"q": q, "message": message}
    try:
        categories = await _categories(request)
        names = {c["_id"]: c["name"] for c in categories}
        products = await product_service.list_all(request.app.state.db)
        context["products"] = [
            {**p, "category_name": product_service.category_name(p, names, "—")}
            for p in products if not q or product_service.matches(p, q, names)
        ]
    except PyMongoError:
        log.exception("Failed to fetch products")
        context["load_error"] = "Failed to fetch products"
    return await render(request, PANEL, context, full_page=False)


async def _form(request: Request, *, product: dict | None, values: dict, errors: dict | None = None,
                error: str | None = None, status_code: int = 200) -> Response:
    options = [(str(c["_id"]), c["name"]) for c in await _categories(request)]
    context = {"product": product, "values": values, "errors": errors or {}, "error": error,
               "category_options": options}
    return await render(request, FORM, context, status_code=status_code, full_page=False)


@router.get("")
async def page(request: Request) -> Response:
    return await render(request, "admin/products.html")


@router.get("/_table")
async def table(request: Request, q: str = "") -> Response:
    return await _table(request, q=q.strip()[:100])


@router.get("/new")
async def new_form(request: Request) -> Response:
    return await _form(request, product=None, values={})


@router.get("/{product_id}/edit")
async def edit_form(product_id: str, request: Request) -> Response:
    product = await product_service.get(request.app.state.db, product_id)
    category = product.get("category")
    values = {
        "name": product.get("name", ""),
        "category": str(category.get("_id") if isinstance(category, dict) else category or ""),
        "price": _plain(product.get("price")),
        "oldPrice": _plain(product.get("oldPrice")),
        "stock": _plain(product.get("stock")),
        "description": product.get("description", ""),
    }
    return await _form(request, product=product, values=values)


async def _save(request: Request, product_id: str | None) -> Response:
    db, store, settings = request.app.state.db, request.app.state.uploads, request.app.state.settings
    product = await product_service.get(db, product_id) if product_id else None
    form = await request.form()
    values = {k: (form.get(k) if isinstance(form.get(k), str) else "") for k in FIELDS}

    async def failed(message: str, errors: dict[str, str]) -> Response:
        response = await _form(request, product=product, values=values, errors=errors,
                               error=None if errors else message, status_code=422)
        return toast(response, message, "error")

    try:
        image = await extract_image(form, settings.max_upload_bytes)
    except AppError as exc:
        return await failed(exc.message, exc.errors)
    errors = validate_form(values, image, creating=product is None)
    if errors:
        return await failed(next(iter(errors.values())), errors)
    try:
        if product is None:
            await product_service.create(db, store, values, image)
        else:
            await product_service.update(db, store, product_id, values, image)
    except AppError as exc:
        if exc.status_code == 404 and "category" not in exc.errors:
            raise
        return await failed(exc.message, exc.errors)
    message = "Product created successfully" if product is None else "Product updated successfully"
    return toast(await _table(request, message=message), message)


@router.post("")
async def create(request: Request) -> Response:
    return await _save(request, None)


@router.put("/{product_id}")
async def update(product_id: str, request: Request) -> Response:
    return await _save(request, product_id)


@router.delete("/{product_id}")
async def delete(product_id: str, request: Request) -> Response:
    await product_service.delete(request.app.state.db, request.app.state.uploads, product_id)
    message = "Product deleted successfully"
    return toast(await _table(request, message=message), message)

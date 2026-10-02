"""Admin → Banners and Promotional Cards (FE §5.13–5.14, FR-UI-114–FR-UI-119)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.htmx import toast
from app.core.templating import render
from app.services import merch_service
from app.services.merch_service import BANNER, PROMO, MerchKind
from app.services.upload_service import extract_image
from app.web.admin import admin_router

log = logging.getLogger("akrf.admin.merch")


@dataclass(frozen=True)
class MerchPage:
    kind: MerchKind
    base: str
    page_title: str
    form_title: str
    list_title: str
    title_placeholder: str
    subtitle_placeholder: str
    title_message: str
    image_message: str
    submit_label: str
    uploaded_message: str
    deleted_message: str
    confirm: str
    loading: str
    empty: str
    load_error: str
    item_label: str


BANNER_PAGE = MerchPage(
    kind=BANNER, base="/admin/banner", page_title="Banner Management", form_title="Add New Banner",
    list_title="All Banners", title_placeholder="Luxury Scented Candles", subtitle_placeholder="Beautiful handmade candles",
    title_message="Please enter banner title", image_message="Please select banner image", submit_label="Upload Banner",
    uploaded_message="Banner uploaded successfully", deleted_message="Banner deleted successfully",
    confirm="Are you sure you want to delete this banner?", loading="Loading banners...", empty="No banners found.",
    load_error="Failed to load banners", item_label="banner",
)
PROMO_PAGE = MerchPage(
    kind=PROMO, base="/admin/promo-card", page_title="Promotional Card Management", form_title="Add Promotional Card",
    list_title="All Promotional Cards", title_placeholder="Luxury Scented Candles",
    subtitle_placeholder="Bring fragrance into your home", title_message="Please enter title",
    image_message="Please select image", submit_label="Upload Promotional Card",
    uploaded_message="Promotional card uploaded", deleted_message="Promotional card deleted",
    confirm="Are you sure you want to delete this card?", loading="Loading...", empty="No promotional cards found.",
    load_error="Failed to load promo cards", item_label="promotional card",
)

DEFAULTS = {"title": "", "subtitle": "", "buttonText": "Shop Now", "buttonLink": "/shop", "order": "0",
            "background": "#08aaa6", "status": "true"}


def build_router(cfg: MerchPage) -> APIRouter:
    router = admin_router(prefix=cfg.base)

    async def list_context(request: Request) -> dict[str, Any]:
        context: dict[str, Any] = {"cfg": cfg}
        try:
            context["items"] = await merch_service.list_all(request.app.state.db, cfg.kind)
        except PyMongoError:
            log.exception("Failed to load %s", cfg.kind.collection)
            context["load_error"] = cfg.load_error
        return context

    async def list_partial(request: Request) -> Response:
        return await render(request, "admin/partials/merch_list.html", await list_context(request), full_page=False)

    @router.get("")
    async def page(request: Request) -> Response:
        return await render(request, "admin/merch.html", {"cfg": cfg, "values": DEFAULTS, "errors": {}})

    @router.get("/_list")
    async def items(request: Request) -> Response:
        return await list_partial(request)

    @router.post("")
    async def create(request: Request) -> Response:
        db, store, settings = request.app.state.db, request.app.state.uploads, request.app.state.settings
        form = await request.form()
        statuses = [v for v in form.getlist("status") if isinstance(v, str)]
        values = {k: (form.get(k) if isinstance(form.get(k), str) else "") for k in DEFAULTS if k != "status"}
        values["status"] = statuses[-1] if statuses else "false"

        async def failed(message: str, errors: dict[str, str]) -> Response:
            response = await render(request, "admin/partials/merch_form.html",
                                    {"cfg": cfg, "values": values, "errors": errors}, status_code=422, full_page=False)
            return toast(response, message, "error")

        try:
            image = await extract_image(form, settings.max_upload_bytes)
        except AppError as exc:
            return await failed(exc.message, exc.errors)
        if not values["title"].strip():
            return await failed(cfg.title_message, {"title": cfg.title_message})
        if image is None:
            return await failed(cfg.image_message, {"image": cfg.image_message})
        try:
            await merch_service.create(db, store, cfg.kind, values, image)
        except AppError as exc:
            return await failed(exc.message, exc.errors)
        context = {**await list_context(request), "values": DEFAULTS, "errors": {}, "oob": True}
        response = await render(request, "admin/partials/merch_created.html", context, full_page=False)
        return toast(response, cfg.uploaded_message)

    @router.delete("/{item_id}")
    async def delete(item_id: str, request: Request) -> Response:
        await merch_service.delete(request.app.state.db, request.app.state.uploads, cfg.kind, item_id)
        return toast(await list_partial(request), cfg.deleted_message)

    return router


banner_router = build_router(BANNER_PAGE)
promo_router = build_router(PROMO_PAGE)

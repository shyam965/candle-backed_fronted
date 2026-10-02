"""`/api/banner/*` and `/api/promo-card/*` (BE §6.7–6.8) — style-A envelope, admin-only writes (KI-01)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import ok, read_body
from app.security.csrf import api_origin_check
from app.security.deps import require_admin
from app.services import merch_service
from app.services.merch_service import BANNER, PROMO, MerchKind
from app.services.upload_service import extract_image

ADMIN = [Depends(require_admin)]


def build_router(prefix: str, kind: MerchKind, create_path: str, public_path: str, all_path: str,
                 delete_path: str) -> APIRouter:
    router = APIRouter(prefix=prefix, dependencies=[Depends(api_origin_check)])

    @router.post(create_path, dependencies=ADMIN)
    async def create(request: Request) -> JSONResponse:
        image = None
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            image = await extract_image(await request.form(), request.app.state.settings.max_upload_bytes)
        doc = await merch_service.create(request.app.state.db, request.app.state.uploads, kind,
                                         await read_body(request), image)
        return ok({"success": True, "message": kind.created, "data": doc}, 201)

    @router.get(public_path)
    async def list_public(request: Request) -> JSONResponse:
        return ok({"success": True, "data": await merch_service.list_active(request.app.state.db, kind)})

    @router.get(all_path, dependencies=ADMIN)
    async def list_everything(request: Request) -> JSONResponse:
        return ok({"success": True, "data": await merch_service.list_all(request.app.state.db, kind)})

    @router.delete(delete_path + "/{item_id}", dependencies=ADMIN)
    async def delete(item_id: str, request: Request) -> JSONResponse:
        await merch_service.delete(request.app.state.db, request.app.state.uploads, kind, item_id)
        return ok({"success": True, "message": kind.deleted})

    return router


banner_router = build_router("/api/banner", BANNER, "/create-banner", "/get-banner", "/get-all-banner", "/delete-banner")
promo_router = build_router("/api/promo-card", PROMO, "/create-promo-card", "/get-promo-card", "/get-all-promo-card",
                            "/delete-promo-card")

"""`/api/category/*` (BE §6.3) — style-B envelope, admin-only writes (KI-01)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import ok, read_body, style_b
from app.security.csrf import api_origin_check
from app.security.deps import require_admin
from app.services import category_service
from app.services.upload_service import extract_image

router = APIRouter(prefix="/api/category", dependencies=[Depends(api_origin_check)])
ADMIN = [Depends(require_admin), Depends(style_b)]


async def _image(request: Request):
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        return await extract_image(await request.form(), request.app.state.settings.max_upload_bytes)
    return None


@router.post("/create-category", dependencies=ADMIN)
async def create_category(request: Request) -> JSONResponse:
    image = await _image(request)
    doc = await category_service.create(request.app.state.db, request.app.state.uploads, await read_body(request), image)
    return ok({"message": "Category created successfully", "success": True, "error": False, "data": doc}, 201)


@router.get("/get-category", dependencies=[Depends(style_b)])
async def get_categories(request: Request) -> JSONResponse:
    data = await category_service.list_all(request.app.state.db)
    return ok({"message": "categories fetched successfully", "success": True, "data": data})


@router.put("/update-category/{category_id}", dependencies=ADMIN)
async def update_category(category_id: str, request: Request) -> JSONResponse:
    await category_service.get(request.app.state.db, category_id)
    image = await _image(request)
    doc = await category_service.update(request.app.state.db, request.app.state.uploads, category_id,
                                        await read_body(request), image)
    return ok({"message": "Category updated successfully", "success": True, "error": False, "data": doc})


@router.delete("/delete-category/{category_id}", dependencies=ADMIN)
async def delete_category(category_id: str, request: Request) -> JSONResponse:
    doc = await category_service.delete(request.app.state.db, request.app.state.uploads, category_id)
    return ok({"message": "Category deleted successfully", "success": True, "error": False, "data": doc})

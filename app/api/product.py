"""`/api/product/*` (BE §6.4) — style-B envelope, admin-only writes (KI-01)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.common import ok, read_body, style_b
from app.security.csrf import api_origin_check
from app.security.deps import require_admin
from app.services import product_service
from app.services.upload_service import extract_image

router = APIRouter(prefix="/api/product", dependencies=[Depends(api_origin_check)])
ADMIN = [Depends(require_admin), Depends(style_b)]


async def _image(request: Request):
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        return await extract_image(await request.form(), request.app.state.settings.max_upload_bytes)
    return None


@router.post("/create-product", dependencies=ADMIN)
async def create_product(request: Request) -> JSONResponse:
    image = await _image(request)
    doc = await product_service.create(request.app.state.db, request.app.state.uploads, await read_body(request), image)
    return ok({"message": "Product created successfully", "success": True, "error": False, "data": doc}, 201)


@router.get("/get-product", dependencies=[Depends(style_b)])
async def get_products(request: Request) -> JSONResponse:
    data = await product_service.list_all(request.app.state.db)
    return ok({"message": "products fetched successfully", "success": True, "data": data})


@router.put("/update-product/{product_id}", dependencies=ADMIN)
async def update_product(product_id: str, request: Request) -> JSONResponse:
    await product_service.get(request.app.state.db, product_id)
    image = await _image(request)
    doc = await product_service.update(request.app.state.db, request.app.state.uploads, product_id,
                                       await read_body(request), image)
    return ok({"message": "Product updated successfully", "success": True, "error": False, "data": doc})


@router.delete("/delete-product/{product_id}", dependencies=ADMIN)
async def delete_product(product_id: str, request: Request) -> JSONResponse:
    await product_service.delete(request.app.state.db, request.app.state.uploads, product_id)
    return ok({"message": "Product deleted successfully", "success": True, "error": False})

"""Health check (FR-002, D-02) and uploaded-file serving (FR-006, D-13)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException

router = APIRouter()

UPLOAD_CSP = "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox"


@router.get("/healthz", include_in_schema=False)
@router.get("/api", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"msg": "api is working"})


@router.get("/uploads/{filename}", include_in_schema=False)
async def uploaded_file(filename: str, request: Request) -> FileResponse:
    path = request.app.state.uploads.path_for(filename)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        headers={
            "Cache-Control": "public, max-age=0",
            "Content-Security-Policy": UPLOAD_CSP,
            "X-Content-Type-Options": "nosniff",
        },
    )

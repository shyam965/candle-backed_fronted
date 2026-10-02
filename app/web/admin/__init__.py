"""Admin routers: every route requires CSRF (unsafe methods) and the admin role (D-52)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.security.deps import require_admin
from app.web.common import ui_router


def admin_router(**kwargs: Any) -> APIRouter:
    return ui_router(dependencies=[Depends(require_admin)], **kwargs)

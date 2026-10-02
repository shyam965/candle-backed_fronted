"""Application factory: lifespan (DB + indexes), middleware stack, routers, error handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, get_settings
from app.core.handlers import handle_unexpected, register_handlers
from app.core.middleware import (
    ApiCorsMiddleware,
    BodyLimitMiddleware,
    PathNormalizeMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.templating import STATIC_DIR, create_templates
from app.db import connect, ensure_indexes
from app.logging_config import configure_logging
from app.security.csrf import CsrfCookieMiddleware
from app.services.upload_service import UploadStore

log = logging.getLogger("akrf")


class CatchAllMiddleware:
    """Innermost safety net so unexpected errors still get request-id logging and branded output."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started:
                raise
            response = await handle_unexpected(Request(scope, receive), exc)
            await response(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client, db = await connect(settings)
        try:
            await ensure_indexes(db)
            app.state.mongo_client = client
            app.state.db = db
            app.state.uploads.ensure_dir()
            log.info("server started on port %s", settings.port)
            yield
        finally:
            await client.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.templates = create_templates(settings)
    app.state.uploads = UploadStore(settings.upload_dir)

    register_handlers(app)

    # Added innermost-first; execution order is the reverse of this list.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(CsrfCookieMiddleware, secure=settings.cookie_secure)
    app.add_middleware(BodyLimitMiddleware, settings=settings)
    app.add_middleware(ApiCorsMiddleware, settings=settings)
    app.add_middleware(PathNormalizeMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    from app.routes import include_routers

    include_routers(app)
    return app

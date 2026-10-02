"""`python -m app` — run with Uvicorn on PORT (default 9000). Exits with code 1 if startup fails (FR-008)."""

from __future__ import annotations

import os
import sys

import uvicorn

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    config = uvicorn.Config(
        "app.main:create_app",
        factory=True,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        log_level=settings.log_level.lower(),
        server_header=False,
    )
    server = uvicorn.Server(config)
    server.run()
    return 0 if server.started else 1


if __name__ == "__main__":
    sys.exit(main())

"""Plain, single-line log format with the request id (D-22). Never log secrets or payloads."""

from __future__ import annotations

import contextvars
import logging
from datetime import datetime

from app.core.documents import IST

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_akrf", False) for h in root.handlers):
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler._akrf = True  # type: ignore[attr-defined]
    handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    formatter.converter = lambda ts: datetime.fromtimestamp(ts, IST).timetuple()  # log times in IST
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("pymongo").setLevel(logging.WARNING)


logger = logging.getLogger("akrf")

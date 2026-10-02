"""Link safety: post-login redirects (D-44) and banner / promo CTA links (FR-UI-034, D-27)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

DEFAULT_CTA = "/shop"


def _is_internal_path(value: str) -> bool:
    return (
        value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and not any(ord(ch) < 32 for ch in value)
    )


def safe_redirect(value: Any) -> str | None:
    """Return `value` only if it is an in-site path such as `/cart`; otherwise None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or not _is_internal_path(value):
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return None
    return value


def is_valid_button_link(value: str) -> bool:
    if _is_internal_path(value):
        return True
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.netloc) and " " not in value


def cta_href(link: Any) -> str:
    """In-site paths and http(s) URLs pass through; empty or unsafe values fall back to /shop."""
    if isinstance(link, str):
        link = link.strip()
        if link and is_valid_button_link(link):
            return link
    return DEFAULT_CTA


def is_external(link: str) -> bool:
    return not _is_internal_path(link)

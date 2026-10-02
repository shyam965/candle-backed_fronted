"""Input validators shared by UI forms and the JSON API (D-26, D-27)."""

from __future__ import annotations

import math
import re
from typing import Any

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
PINCODE_RE = re.compile(r"^\d{6}$")
COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

DEFAULT_PROMO_BACKGROUND = "#08aaa6"


class Invalid(ValueError):
    """Raised by parsers when a value cannot be interpreted."""


def is_email(value: str) -> bool:
    return len(value) <= 254 and bool(EMAIL_RE.match(value))


def is_mobile(value: str) -> bool:
    return bool(MOBILE_RE.match(value))


def is_pincode(value: str) -> bool:
    return bool(PINCODE_RE.match(value))


def is_color(value: str) -> bool:
    return bool(COLOR_RE.match(value))


def safe_color(value: Any) -> str:
    return value if isinstance(value, str) and is_color(value) else DEFAULT_PROMO_BACKGROUND


def digits_only(value: Any, max_len: int) -> str:
    """Strip non-digit characters and cap the length (FR-UI-069)."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\D", "", value)[:max_len]


def text(value: Any) -> str | None:
    """Return a trimmed string, None when absent; raise Invalid for non-string values (KI-13)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise Invalid("expected text")
    return value.strip()


def parse_number(value: Any) -> float:
    """Parse a finite number from a JSON number or numeric string. `""` and junk raise Invalid."""
    if isinstance(value, bool) or value is None:
        raise Invalid("not a number")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise Invalid("empty")
        try:
            number = float(stripped)
        except ValueError as exc:
            raise Invalid("not a number") from exc
    else:
        raise Invalid("not a number")
    if not math.isfinite(number):
        raise Invalid("not finite")
    return number


def parse_int(value: Any) -> int:
    number = parse_number(value)
    if not number.is_integer():
        raise Invalid("not an integer")
    return int(number)


TRUE_STRINGS = {"true", "on", "1", "yes"}
FALSE_STRINGS = {"false", "off", "0", "no"}


def parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_STRINGS:
            return True
        if lowered in FALSE_STRINGS:
            return False
    raise Invalid("not a boolean")

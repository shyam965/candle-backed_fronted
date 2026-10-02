"""Display formatting: ₹ en-IN money, en-IN dates, discounts and image URLs (FR-UI-041/042/093/128)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _group_indian(integer: str) -> str:
    if len(integer) <= 3:
        return integer
    head, tail = integer[:-3], integer[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_number_en_in(value: Any) -> str:
    number = to_number(value)
    if number is None:
        number = 0.0
    try:
        quantized = Decimal(str(number)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        quantized = Decimal("0.00")
    sign = "-" if quantized < 0 else ""
    integer, _, fraction = f"{abs(quantized):.2f}".partition(".")
    fraction = fraction.rstrip("0")
    text = _group_indian(integer)
    return f"{sign}{text}.{fraction}" if fraction else f"{sign}{text}"


def inr(value: Any) -> str:
    """`₹` followed by the en-IN formatted amount with at most 2 decimals (FR-UI-041)."""
    return "₹" + format_number_en_in(value)


def js_round(value: float) -> int:
    return math.floor(value + 0.5)


def discount_percent(price: Any, old_price: Any) -> int | None:
    """round((oldPrice − price) / oldPrice × 100) when oldPrice > price, else None (FR-UI-042)."""
    p, o = to_number(price), to_number(old_price)
    if p is None or o is None or o <= 0 or o <= p:
        return None
    return js_round((o - p) / o * 100)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def fmt_date(value: Any, tz: ZoneInfo) -> str:
    """en-IN `05 Oct 2026`; `-` for missing or invalid dates (FR-UI-093)."""
    dt = _as_datetime(value)
    if dt is None:
        return "-"
    local = dt.astimezone(tz)
    return f"{local.day:02d} {_MONTHS[local.month - 1]} {local.year}"


def fmt_datetime(value: Any, tz: ZoneInfo) -> str:
    """en-IN `05 Oct 2026, 09:15 am`; `-` for missing or invalid dates (FR-UI-093)."""
    dt = _as_datetime(value)
    if dt is None:
        return "-"
    local = dt.astimezone(tz)
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    return f"{fmt_date(dt, tz)}, {hour:02d}:{local.minute:02d} {suffix}"


def image_url(path: Any) -> str:
    """Absolute http(s) and data: URLs unchanged; root-relative paths served same-origin (FR-UI-128, K-29)."""
    if not isinstance(path, str) or not path:
        return ""
    if path.startswith(("http://", "https://", "data:image/")):
        return path
    if path.startswith("/") and not path.startswith("//"):
        return path
    return ""

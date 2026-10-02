"""Presentation rules for orders: status labels, tracking steps, shipping label (FR-UI-086–FR-UI-092, FR-UI-125)."""

from __future__ import annotations

from typing import Any

from app.core.formatting import inr, to_number
from app.services.order_service import FLOW, STATUSES, allowed_next

STATUS_STYLES = {
    "Pending": ("badge-warning", "clock"),
    "Confirmed": ("badge-info", "check"),
    "Processing": ("badge-royal", "package"),
    "Shipped": ("badge-info", "truck"),
    "Delivered": ("badge-success", "check-circle"),
    "Cancelled": ("badge-danger", "x-circle"),
}
STEP_LABELS = {"Pending": "Order Placed", "Confirmed": "Confirmed", "Processing": "Processing", "Shipped": "Shipped",
               "Delivered": "Delivered"}
CURRENT_TAGS = {"Processing": "Preparing", "Shipped": "On the way", "Delivered": "Delivered"}
ADMIN_LABELS = {"Pending": "Order Pending", "Confirmed": "Order Confirmed", "Processing": "Processing",
                "Shipped": "Shipped", "Delivered": "Delivered", "Cancelled": "Cancelled"}


def status_of(order: dict[str, Any]) -> str:
    status = order.get("status")
    return status if status in STATUSES else "Pending"


def status_style(status: str) -> tuple[str, str]:
    return STATUS_STYLES.get(status, STATUS_STYLES["Pending"])


def _date(order: dict[str, Any], key: str) -> Any:
    value = (order.get("statusDates") or {}).get(key)
    if key == "Pending" and not value:
        return order.get("createdAt")
    return value


def current_status(order: dict[str, Any]) -> tuple[str, Any]:
    """Label "Order Placed" for Pending, else "{status} On"; value = that status's date (FR-UI-087)."""
    status = status_of(order)
    label = "Order Placed" if status == "Pending" else f"{status} On"
    return label, _date(order, status)


def tracking_steps(order: dict[str, Any]) -> list[dict[str, Any]]:
    """5-step flow, or the 3-step cancelled variant (FR-UI-090, FR-UI-091)."""
    status = status_of(order)
    if status == "Cancelled":
        confirmed = _date(order, "Confirmed")
        return [
            {"key": "Pending", "label": "Order Placed", "date": _date(order, "Pending"), "state": "done", "tag": None},
            {"key": "Confirmed", "label": "Confirmed", "date": confirmed, "state": "done" if confirmed else "upcoming",
             "tag": None},
            {"key": "Cancelled", "label": "Cancelled", "date": _date(order, "Cancelled"), "state": "cancelled",
             "tag": None},
        ]
    index = FLOW.index(status)
    steps = []
    for position, key in enumerate(FLOW):
        state = "done" if position < index else "current" if position == index else "upcoming"
        steps.append({"key": key, "label": STEP_LABELS[key], "date": _date(order, key), "state": state,
                      "tag": CURRENT_TAGS.get(key) if state == "current" else None})
    return steps


def shipping_label(order: dict[str, Any]) -> str:
    status = order.get("shippingStatus")
    if status == "FREE":
        return "FREE"
    if status == "PAYABLE_SEPARATELY":
        return "PAYABLE SEPARATELY"
    shipping = to_number(order.get("shipping")) or 0
    return inr(shipping) if shipping > 0 else "PAYABLE SEPARATELY"


def admin_timeline(order: dict[str, Any]) -> list[dict[str, Any]]:
    """Six entries with dates or "Not available" / "Not {status} yet" (FR-UI-125)."""
    current = status_of(order)
    entries = []
    for key in STATUSES:
        date = (order.get("statusDates") or {}).get(key)
        missing = "Not available" if key == "Pending" else f"Not {key.lower()} yet"
        entries.append({"key": key, "label": ADMIN_LABELS[key], "date": date, "missing": missing,
                        "current": key == current})
    return entries


def item_count(order: dict[str, Any]) -> int:
    return sum(int(to_number(i.get("quantity")) or 0) for i in order.get("items", []))


TEMPLATE_GLOBALS = {
    "order_status": status_of,
    "status_style": status_style,
    "current_status": current_status,
    "tracking_steps": tracking_steps,
    "shipping_label": shipping_label,
    "admin_timeline": admin_timeline,
    "item_count": item_count,
    "allowed_statuses": allowed_next,
}

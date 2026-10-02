"""Order presentation rules (FR-UI-087, FR-UI-090–FR-UI-092, FR-UI-125)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import order_view as v

T0 = datetime(2026, 10, 2, tzinfo=UTC)
T1 = datetime(2026, 10, 3, tzinfo=UTC)


def order(status, **dates):
    base = {s: None for s in ("Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled")}
    base.update(dates)
    return {"status": status, "statusDates": base, "createdAt": T0}


def test_current_status_label():
    assert v.current_status(order("Pending")) == ("Order Placed", T0)  # falls back to createdAt
    assert v.current_status(order("Shipped", Shipped=T1)) == ("Shipped On", T1)
    assert v.current_status(order("Confirmed")) == ("Confirmed On", None)


def test_tracking_steps():
    steps = v.tracking_steps(order("Shipped", Pending=T0, Shipped=T1))
    assert [s["label"] for s in steps] == ["Order Placed", "Confirmed", "Processing", "Shipped", "Delivered"]
    assert [s["state"] for s in steps] == ["done", "done", "done", "current", "upcoming"]
    assert steps[3]["tag"] == "On the way" and steps[3]["date"] == T1 and steps[1]["date"] is None
    assert v.tracking_steps(order("Processing"))[2]["tag"] == "Preparing"
    assert v.tracking_steps(order("Delivered"))[4]["tag"] == "Delivered"
    assert v.tracking_steps({"status": "Weird", "statusDates": {}, "createdAt": T0})[0]["state"] == "current"


def test_cancelled_tracking():
    steps = v.tracking_steps(order("Cancelled", Cancelled=T1))
    assert [s["label"] for s in steps] == ["Order Placed", "Confirmed", "Cancelled"]
    assert [s["state"] for s in steps] == ["done", "upcoming", "cancelled"]
    assert v.tracking_steps(order("Cancelled", Confirmed=T0))[1]["state"] == "done"


def test_shipping_label():
    assert v.shipping_label({"shippingStatus": "FREE"}) == "FREE"
    assert v.shipping_label({"shippingStatus": "PAYABLE_SEPARATELY"}) == "PAYABLE SEPARATELY"
    assert v.shipping_label({"shippingStatus": None, "shipping": 50}) == "₹50"
    assert v.shipping_label({"shippingStatus": None, "shipping": 0}) == "PAYABLE SEPARATELY"


def test_admin_timeline_labels():
    entries = v.admin_timeline(order("Confirmed", Pending=T0, Confirmed=T1))
    assert [e["label"] for e in entries] == ["Order Pending", "Order Confirmed", "Processing", "Shipped", "Delivered", "Cancelled"]
    assert entries[1]["current"] and entries[1]["date"] == T1
    assert entries[2]["missing"] == "Not processing yet" and entries[0]["missing"] == "Not available"

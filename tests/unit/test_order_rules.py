"""Order business rules (BR-19–BR-30, D-29–D-34)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ValidationFailed
from app.services import order_service as o
from tests.helpers import make_product, make_user

NOW = datetime(2026, 10, 2, 9, 15, 27, 481000, tzinfo=UTC)


def test_order_id_format():
    oid = o.generate_order_id(NOW)
    assert re.fullmatch(rf"AKRF-{int(NOW.timestamp() * 1000)}-\d{{4}}", oid)
    assert all(1000 <= int(o.generate_order_id(NOW)[-4:]) <= 9999 for _ in range(200))


def test_expected_delivery_72h():
    assert o.expected_delivery(NOW) - NOW == timedelta(hours=72)


@pytest.mark.parametrize("current,allowed", [
    ("Pending", ["Confirmed", "Processing", "Shipped", "Delivered", "Cancelled"]),
    ("Confirmed", ["Processing", "Shipped", "Delivered", "Cancelled"]),
    ("Processing", ["Shipped", "Delivered", "Cancelled"]),
    ("Shipped", ["Delivered", "Cancelled"]),
    ("Delivered", []),
    ("Cancelled", []),
])
def test_transition_matrix(current, allowed):
    assert o.allowed_next(current) == allowed
    for status in o.STATUSES:
        if status in allowed:
            o.check_transition(current, status)
        else:
            with pytest.raises(ValidationFailed):
                o.check_transition(current, status)


def test_transition_messages():
    with pytest.raises(ValidationFailed, match="Order is already Shipped"):
        o.check_transition("Shipped", "Shipped")
    with pytest.raises(ValidationFailed, match="Cannot change order status from Delivered to Pending"):
        o.check_transition("Delivered", "Pending")
    with pytest.raises(ValidationFailed, match="Invalid order status"):
        o.check_transition("Pending", "shipped")


def test_status_change_stamps_date_keeps_others():
    changes = o.apply_status({"expectedDelivery": NOW}, "Shipped", NOW)
    assert changes == {"status": "Shipped", "statusDates.Shipped": NOW}


def test_cancel_clears_expected_delivery():
    assert o.apply_status({"expectedDelivery": NOW}, "Cancelled", NOW)["expectedDelivery"] is None


def test_expected_delivery_restored_for_legacy_null():
    assert o.apply_status({"expectedDelivery": None}, "Confirmed", NOW)["expectedDelivery"] == NOW + timedelta(days=3)


def test_customer_validation_messages():
    values, errors = o.validate_customer({"name": " ", "mobile": "12345", "address": "", "city": "x", "pincode": "11"})
    assert errors == {"name": "Please enter your full name.", "address": "Please enter your complete address.",
                      "mobile": "Please enter a valid 10 digit mobile number.", "pincode": "Please enter a valid 6 digit pincode."}
    values, errors = o.validate_customer({"name": " Asha ", "mobile": "9876543210", "address": "12 MG Road",
                                          "city": "Jaipur", "pincode": "302001", "message": " gift "})
    assert errors == {} and values["name"] == "Asha" and values["message"] == "gift"
    _, errors = o.validate_customer({"name": "A", "mobile": 9876543210, "address": "x", "city": "y", "pincode": "302001"})
    assert "mobile" in errors


def test_totals_recomputed_shipping_status_threshold():
    items = [{"total": 998}, {"total": 101}]
    assert o.summarize(items, 1099) == {"itemsTotal": 1099, "shipping": 0, "shippingStatus": "FREE", "grandTotal": 1099}
    assert o.summarize([{"total": 998}], 1099)["shippingStatus"] == "PAYABLE_SEPARATELY"


async def test_lines_priced_from_db(app):
    db = app.state.db
    product = await make_product(db, price=499.5, stock=4, name="Rose")
    lines = await o.build_lines(db, [(product["_id"], 1), (product["_id"], 1)])
    assert lines == [{"product": product["_id"], "name": "Rose", "image": product["image"], "price": 499.5,
                      "quantity": 2, "total": 999}]
    with pytest.raises(ValidationFailed, match="Only 4 items available for Rose"):
        await o.build_lines(db, [(product["_id"], 5)])


async def test_cart_cleanup_quantities(app):
    db = app.state.db
    user = await make_user(db)
    a = await make_product(db, name="A")
    b = await make_product(db, name="B")
    c = await make_product(db, name="C")
    await db.carts.insert_one({"user": user["_id"], "__v": 0, "items": [
        {"product": a["_id"], "quantity": 3, "selected": True},
        {"product": b["_id"], "quantity": 1, "selected": False},
        {"product": c["_id"], "quantity": 2, "selected": True}]})
    await o.cleanup_cart(db, user["_id"], [{"product": a["_id"], "quantity": 1}, {"product": c["_id"], "quantity": 2}])
    cart = await db.carts.find_one({"user": user["_id"]})
    assert [(i["product"], i["quantity"]) for i in cart["items"]] == [(a["_id"], 2), (b["_id"], 1)] and cart["__v"] == 1


async def test_new_order_status_and_dates(app):
    db = app.state.db
    user = await make_user(db)
    product = await make_product(db, price=100)
    pending = o.pending_from_lines({"name": "A", "mobile": "9876543210", "address": "x", "city": "y", "pincode": "302001",
                                    "message": ""}, await o.build_lines(db, [(product["_id"], 2)]), 1099)
    order = await o.create_from_pending(db, user, pending, 1099)
    assert order["status"] == "Pending" and order["orderId"] == pending["orderId"]
    assert order["statusDates"]["Pending"] == order["createdAt"]
    assert all(order["statusDates"][s] is None for s in o.STATUSES[1:])
    assert order["expectedDelivery"] - order["createdAt"] == timedelta(days=3)
    assert order["paymentMethod"] == "WhatsApp Order" and order["__v"] == 0

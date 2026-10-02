"""Cart totals and selection rules (FR-UI-065–FR-UI-067, FR-UI-074, BR-17)."""

from __future__ import annotations

from app.core.validators import parse_bool
from app.services.cart_service import totals


def line(price, qty, selected=True, product=True):
    return {"product": {"price": price} if product else None, "quantity": qty, "selected": selected}


def test_items_total_selected_only():
    t = totals([line(499, 2), line(100, 1, selected=False), line(50, 3, product=False)], 1099)
    assert t.items_total == 998 and t.selected_quantity == 2 and t.all_quantity == 3


def test_free_delivery_threshold():
    assert totals([line(1099, 1)], 1099).free_shipping is True
    below = totals([line(1098.5, 1)], 1099)
    assert below.free_shipping is False and below.amount_for_free == 0.5


def test_grand_total_equals_items_total():
    t = totals([line(499.5, 2)], 1099)
    assert t.grand_total == t.items_total == 999


def test_shipping_status_threshold():
    assert totals([line(1200, 1)], 1099).shipping_status == "FREE"
    assert totals([line(10, 1)], 1099).shipping_status == "PAYABLE_SEPARATELY"


def test_missing_selected_flag_counts_as_selected():
    assert totals([{"product": {"price": 10}, "quantity": 1}], 1099).items_total == 10


def test_parse_selected():
    assert parse_bool(None, default=True) is True
    assert parse_bool(False, default=True) is False
    assert parse_bool("false", default=True) is False
    assert parse_bool("true", default=False) is True

"""Product numeric rules (BR-09–BR-11, D-25, D-26) and admin form validation order (FR-UI-110)."""

from __future__ import annotations

import pytest

from app.core.validators import Invalid
from app.services.product_service import parse_old_price, parse_price, parse_stock
from app.web.admin.products import validate_form


def test_price_stock_oldprice_rules():
    assert parse_price("499") == 499 and parse_price(1) == 1 and parse_price("1.5") == 1.5
    for bad in ("", "0", "0.99", "-5", "abc", None, True, "nan"):
        with pytest.raises(Invalid):
            parse_price(bad)
    assert parse_old_price("") is None and parse_old_price(None) is None and parse_old_price("699") == 699
    with pytest.raises(Invalid):
        parse_old_price("0")
    assert parse_stock("0") == 0 and parse_stock(12) == 12
    for bad in ("", "-1", "1.5", "x"):
        with pytest.raises(Invalid):
            parse_stock(bad)


def test_validation_order_and_messages():
    values = {"name": " ", "category": "", "price": "0", "oldPrice": "abc", "stock": "1.5", "description": ""}
    errors = validate_form(values, None, creating=True)
    assert list(errors) == ["name", "category", "image", "price", "stock", "oldPrice"]
    assert errors == {
        "name": "Product name is required",
        "category": "Please select a category",
        "image": "Please upload a product image",
        "price": "Please enter a valid price",
        "stock": "Please enter valid stock",
        "oldPrice": "Old price must be greater than or equal to selling price",
    }


def test_valid_form_and_equal_old_price():
    values = {"name": "Rose", "category": "x", "price": "499", "oldPrice": "499", "stock": "3", "description": ""}
    assert validate_form(values, None, creating=False) == {}

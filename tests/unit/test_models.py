"""Stored-document schemas (D-56) accept the spec's example documents and reject wrong types/enums."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.models import BannerDoc, CartDoc, CategoryDoc, OrderDoc, ProductDoc, PromoCardDoc, UserDoc, check

NOW = datetime(2026, 10, 2, tzinfo=UTC)
META = {"createdAt": NOW, "updatedAt": NOW, "__v": 0}
HASH = "$2a$10$" + "a" * 53


def order(**kw):
    doc = {"orderId": "AKRF-1790700056594-4821", "user": ObjectId(),
           "customer": {"name": "A", "mobile": "9876543210", "address": "x", "city": "y", "pincode": "302001", "message": ""},
           "items": [{"product": ObjectId(), "name": "Rose", "image": "", "price": 499, "quantity": 2, "total": 998}],
           "itemsTotal": 998, "shipping": 0, "shippingStatus": "FREE", "grandTotal": 998, "paymentMethod": "WhatsApp Order",
           "status": "Pending", "statusDates": {"Pending": NOW, "Confirmed": None, "Processing": None, "Shipped": None,
                                                "Delivered": None, "Cancelled": None}, "expectedDelivery": NOW, **META}
    doc.update(kw)
    return doc


def test_spec_examples_validate():
    check(UserDoc, {"name": "Asha", "email": "a@b.co", "phone": "", "password": HASH, "address": "", "city": "", "pincode": "",
                    "role": "user", **META})
    check(CategoryDoc, {"name": "Jar Candles", "description": "", "image": "/uploads/a.png", **META})
    check(ProductDoc, {"name": "Rose", "category": ObjectId(), "price": 499, "oldPrice": 699, "stock": 25, "description": "",
                       "image": "/uploads/b.png", **META})
    check(CartDoc, {"user": ObjectId(), "items": [{"product": ObjectId(), "quantity": 2, "selected": True}], **META})
    check(OrderDoc, order())
    check(BannerDoc, {"title": "T", "subtitle": "", "image": "/uploads/c.png", "buttonText": "Shop Now", "buttonLink": "/shop",
                      "order": 0, "status": True, **META})
    check(PromoCardDoc, {"title": "T", "subtitle": "", "image": "/uploads/c.png", "buttonText": "Shop Now", "buttonLink": "/shop",
                         "background": "#08aaa6", "order": 0, "status": True, **META})


@pytest.mark.parametrize("bad", [{"status": "Lost"}, {"shippingStatus": "PAID"}, {"items": []}, {"orderId": "X-1"},
                                 {"unknown": 1}, {"itemsTotal": float("nan")}])
def test_invalid_orders_rejected(bad):
    with pytest.raises(ValidationError):
        check(OrderDoc, order(**bad))


def test_invalid_user_role_and_hash_rejected():
    base = {"name": "A", "email": "a@b.co", "password": HASH, **META}
    with pytest.raises(ValidationError):
        check(UserDoc, {**base, "role": "superuser"})
    with pytest.raises(ValidationError):
        check(UserDoc, {**base, "password": "plain"})

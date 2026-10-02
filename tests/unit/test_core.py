"""Unit tests for config, documents, serialization, formatting, links and validators."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.config import Settings
from app.core import formatting as f
from app.core import links, validators as v
from app.core.documents import new_meta, num, touch
from app.core.serialization import to_json

IST = ZoneInfo("Asia/Kolkata")


def make_settings(**kw):
    base = {"mongo_uri": "mongodb://localhost:27017", "secret_key": "s" * 40}
    base.update(kw)
    return Settings(_env_file=None, **base)


# ---------- config (FR-001, D-04, D-08) ----------

def test_port_default_9000():
    assert make_settings().port == 9000


def test_secret_key_required():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mongo_uri="mongodb://localhost:27017")
    with pytest.raises(ValidationError):
        make_settings(secret_key="short")


def test_database_name_resolution():
    assert make_settings().database_name == "test"
    assert make_settings(mongo_uri="mongodb://localhost:27017/shop").database_name == "shop"
    assert make_settings(mongo_uri="mongodb://localhost:27017/shop", mongo_db_name="other").database_name == "other"


def test_cors_origins_split_and_allowed():
    s = make_settings(cors_origins="http://a.test, http://b.test/", app_base_url="https://shop.test/")
    assert s.cors_origins == ["http://a.test", "http://b.test"]
    assert s.allowed_origins == {"https://shop.test", "http://a.test", "http://b.test"}


def test_map_embed_url_validated():
    with pytest.raises(ValidationError):
        make_settings(map_embed_url="https://evil.example/embed")


# ---------- documents (FR-010, D-10) ----------

def test_new_doc_meta():
    meta = new_meta()
    assert meta["__v"] == 0 and meta["createdAt"] == meta["updatedAt"]
    assert meta["createdAt"].microsecond % 1000 == 0


def test_touch_updates_updated_at_and_version():
    update = touch({"$set": {"name": "x"}}, bump_version=True)
    assert "updatedAt" in update["$set"] and update["$inc"] == {"__v": 1}
    assert "$inc" not in touch({"$set": {"a": 1}})


def test_num_stores_integral_values_as_int():
    assert num(499.0) == 499 and isinstance(num(499.0), int)
    assert num(499.5) == 499.5
    with pytest.raises(TypeError):
        num(True)


# ---------- serialization (FR-011) ----------

def test_objectid_and_datetime():
    oid = ObjectId()
    dt = datetime(2026, 10, 2, 9, 15, 27, 481000, tzinfo=UTC)
    out = to_json({"_id": oid, "at": dt, "list": [{"d": dt}], "n": None})
    assert out == {"_id": str(oid), "at": "2026-10-02T09:15:27.481Z", "list": [{"d": "2026-10-02T09:15:27.481Z"}], "n": None}


# ---------- formatting (FR-UI-041/042/093/128) ----------

@pytest.mark.parametrize("value,expected", [
    (499, "₹499"), (1099, "₹1,099"), (123456.5, "₹1,23,456.5"), (1234567.891, "₹12,34,567.89"),
    (0, "₹0"), ("998", "₹998"), (None, "₹0"), (10.10, "₹10.1"),
])
def test_inr(value, expected):
    assert f.inr(value) == expected


def test_discount_percent():
    assert f.discount_percent(499, 699) == 29
    assert f.discount_percent(500, 500) is None
    assert f.discount_percent(600, 500) is None
    assert f.discount_percent(500, None) is None
    assert f.discount_percent(50, 100) == 50


def test_dates_en_in():
    dt = datetime(2026, 10, 5, 3, 45, tzinfo=UTC)  # 09:15 IST
    assert f.fmt_date(dt, IST) == "05 Oct 2026"
    assert f.fmt_datetime(dt, IST) == "05 Oct 2026, 09:15 am"
    assert f.fmt_datetime(datetime(2026, 10, 5, 10, 0, tzinfo=UTC), IST) == "05 Oct 2026, 03:30 pm"
    assert f.fmt_date("2026-10-05T03:45:00.000Z", IST) == "05 Oct 2026"
    assert f.fmt_date(None, IST) == "-"
    assert f.fmt_datetime("not a date", IST) == "-"


def test_image_url_resolution():
    assert f.image_url("/uploads/a.png") == "/uploads/a.png"
    assert f.image_url("https://cdn.example/a.png") == "https://cdn.example/a.png"
    assert f.image_url("data:image/png;base64,AAA") == "data:image/png;base64,AAA"
    assert f.image_url("") == ""
    assert f.image_url(None) == ""
    assert f.image_url("uploads/a.png") == ""
    assert f.image_url("//evil.example/a.png") == ""
    assert f.image_url("javascript:alert(1)") == ""


# ---------- links (FR-UI-034, D-44) ----------

def test_cta_href_resolution():
    assert links.cta_href("/shop?category=1") == "/shop?category=1"
    assert links.cta_href("https://example.com/sale") == "https://example.com/sale"
    assert links.cta_href("") == "/shop"
    assert links.cta_href(None) == "/shop"
    assert links.cta_href("javascript:alert(1)") == "/shop"
    assert links.cta_href("//evil.example") == "/shop"


@pytest.mark.parametrize("value,expected", [
    ("/cart", "/cart"), ("/my-orders?x=1", "/my-orders?x=1"), ("https://evil.example", None),
    ("//evil.example", None), ("/\\evil.example", None), ("", None), (None, None), ("cart", None),
])
def test_safe_redirect(value, expected):
    assert links.safe_redirect(value) == expected


# ---------- validators (FR-UI-069/071, D-26/27) ----------

def test_mobile_and_pincode_patterns():
    assert v.is_mobile("9876543210") and v.is_mobile("6000000000")
    assert not v.is_mobile("5876543210") and not v.is_mobile("987654321") and not v.is_mobile("98765432101")
    assert v.is_pincode("110001") and not v.is_pincode("11001") and not v.is_pincode("11000a")


def test_digits_normalisation():
    assert v.digits_only("+91 98765-43210", 10) == "9198765432"
    assert v.digits_only("11 00 01 9", 6) == "110001"
    assert v.digits_only(None, 6) == ""


def test_email_and_color():
    assert v.is_email("asha@example.com") and not v.is_email("asha@example") and not v.is_email("a b@c.d")
    assert v.is_color("#08aaa6") and v.is_color("#fff") and not v.is_color("red") and not v.is_color("#12345")
    assert v.safe_color("url(javascript:x)") == "#08aaa6"


def test_number_parsing():
    assert v.parse_number(" 499.5 ") == 499.5 and v.parse_number(3) == 3.0
    for bad in ("", "abc", None, True, float("nan"), "inf", [1]):
        with pytest.raises(v.Invalid):
            v.parse_number(bad)
    assert v.parse_int("12") == 12
    with pytest.raises(v.Invalid):
        v.parse_int("1.5")


def test_parse_bool():
    assert v.parse_bool(None, default=True) is True
    assert v.parse_bool("false", default=True) is False
    assert v.parse_bool("on", default=False) is True
    assert v.parse_bool(0, default=True) is False
    with pytest.raises(v.Invalid):
        v.parse_bool("maybe", default=True)

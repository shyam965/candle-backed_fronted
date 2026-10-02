"""Banner / promo defaults and parsing (FR-106, FR-113, BR-33, BR-34)."""

from __future__ import annotations

from app.services.merch_service import parse_order, parse_status


def test_defaults_and_status_parsing():
    assert parse_status(None) is True
    assert parse_status(True) is True and parse_status("true") is True
    for other in (False, "false", "on", "1", "TRUE", "", 1):
        assert parse_status(other) is False
    assert parse_order("3") == 3 and parse_order("abc") == 0 and parse_order(None) == 0 and parse_order("1.5") == 1.5

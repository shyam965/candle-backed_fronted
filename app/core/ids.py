"""ObjectId parsing. "Valid ObjectId" = 24 hexadecimal characters (BE §6.0)."""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId

_HEX24 = re.compile(r"^[0-9a-fA-F]{24}$")


def is_object_id(value: Any) -> bool:
    return isinstance(value, ObjectId) or (isinstance(value, str) and bool(_HEX24.match(value)))


def parse_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and _HEX24.match(value):
        return ObjectId(value)
    return None

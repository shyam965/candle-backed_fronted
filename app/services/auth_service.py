"""Registration, login and rate limiting (BE §6.2, BR-01–BR-05, D-05, D-07, D-27)."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.config import Settings
from app.core.documents import new_meta
from app.core.errors import Conflict, Unauthorized, ValidationFailed
from app.core.validators import is_email, is_mobile
from app.models import UserDoc, check
from app.security import rate_limit
from app.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, hash_password, verify_password

REQUIRED_REGISTER = "Name, email and password are required"
REQUIRED_LOGIN = "Email and password are required"
INVALID_LOGIN = "Invalid email or password"
SHORT_PASSWORD = "Password must be at least 6 characters"
LONG_PASSWORD = "Password must be at most 72 characters"

LOGIN_WINDOW = 15 * 60
REGISTER_WINDOW = 60 * 60


def normalize_email(email: str) -> str:
    return email.strip().lower()


def public_profile(user: dict[str, Any]) -> dict[str, Any]:
    """User summary returned by the auth endpoints; never includes the password (FR-036, M-15)."""
    return {
        "id": str(user["_id"]),
        "_id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "phone": user.get("phone", ""),
        "address": user.get("address", ""),
        "city": user.get("city", ""),
        "pincode": user.get("pincode", ""),
        "role": user.get("role", "user"),
    }


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


async def register(db: AsyncDatabase, data: dict[str, Any]) -> dict[str, Any]:
    raw_name, raw_email, password = (_str_or_none(data.get(k)) for k in ("name", "email", "password"))
    raw_phone = data.get("phone")
    name = (raw_name or "").strip()
    email = normalize_email(raw_email or "")
    if not name or not email or not password:
        errors = {k: "This field is required" for k, v in (("name", name), ("email", email), ("password", password)) if not v}
        raise ValidationFailed(REQUIRED_REGISTER, errors=errors)
    if raw_phone is not None and not isinstance(raw_phone, str):
        raise ValidationFailed("Please enter a valid 10 digit mobile number", field="phone")
    phone = (raw_phone or "").strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(SHORT_PASSWORD, field="password")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValidationFailed(LONG_PASSWORD, field="password")
    if len(name) > 120:
        raise ValidationFailed("Name must be at most 120 characters", field="name")
    if not is_email(email):
        raise ValidationFailed("Please enter a valid email address", field="email")
    if phone and not is_mobile(phone):
        raise ValidationFailed("Please enter a valid 10 digit mobile number", field="phone")
    if await db.users.find_one({"email": email}, {"_id": 1}):
        raise Conflict("Email already registered", field="email")
    user = {
        "_id": ObjectId(),
        "name": name,
        "email": email,
        "phone": phone,
        "password": await hash_password(password),
        "address": "",
        "city": "",
        "pincode": "",
        "role": "user",
        **new_meta(),
    }
    try:
        await db.users.insert_one(check(UserDoc, user))
    except DuplicateKeyError as exc:
        raise Conflict("Email already registered", field="email") from exc
    user.pop("password")
    return user


async def authenticate(db: AsyncDatabase, data: dict[str, Any]) -> dict[str, Any]:
    email, password = _str_or_none(data.get("email")), _str_or_none(data.get("password"))
    if not email or not email.strip() or not password:
        raise ValidationFailed(REQUIRED_LOGIN)
    user = await db.users.find_one({"email": normalize_email(email)})
    if user is None or not await verify_password(password, user.get("password", "")):
        raise Unauthorized(INVALID_LOGIN)
    user.pop("password", None)
    return user


# ---------- rate limiting (D-07) ----------

def _email_key(data: dict[str, Any]) -> str:
    email = data.get("email")
    return normalize_email(email) if isinstance(email, str) else ""


async def guard_login(db: AsyncDatabase, settings: Settings, ip: str, data: dict[str, Any]) -> None:
    await rate_limit.enforce(db, f"login-ip:{ip}", settings.rate_limit_login_ip_per_15m, LOGIN_WINDOW)
    await rate_limit.enforce(db, f"login-fail:{ip}:{_email_key(data)}", settings.rate_limit_login_per_15m,
                             LOGIN_WINDOW, count=False)


async def record_login_failure(db: AsyncDatabase, ip: str, data: dict[str, Any]) -> None:
    await rate_limit.hit(db, f"login-fail:{ip}:{_email_key(data)}", LOGIN_WINDOW)


async def guard_register(db: AsyncDatabase, settings: Settings, ip: str) -> None:
    await rate_limit.enforce(db, f"register-ip:{ip}", settings.rate_limit_register_per_hour, REGISTER_WINDOW)

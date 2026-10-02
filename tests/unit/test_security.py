"""Passwords (FR-017, D-05), sessions (FR-026/027, D-04) and uploads (FR-118–FR-122, D-12)."""

from __future__ import annotations

import re
from datetime import timedelta

import bcrypt
import pytest
from starlette.datastructures import FormData, Headers, UploadFile
from starlette.responses import Response

from app.core.documents import now_ist
from app.core.errors import PayloadTooLarge, ValidationFailed
from app.security.passwords import hash_password_sync, verify_password_sync
from app.security.sessions import create_session, get_session, hash_token, set_session_cookie
from app.services.upload_service import UploadStore, detect_image, extract_image
from tests.helpers import FAKE_PNG, JPEG, PNG, WEBP, make_user

# ---------- passwords ----------


def test_hash_is_2a_cost10():
    hashed = hash_password_sync("secret1")
    assert hashed.startswith("$2a$10$") and len(hashed) == 60
    assert verify_password_sync("secret1", hashed)
    assert not verify_password_sync("secret2", hashed)


def test_verifies_legacy_2a_hash():
    legacy = bcrypt.hashpw(b"secret1", bcrypt.gensalt(10, prefix=b"2a")).decode()
    assert verify_password_sync("secret1", legacy)


def test_verifies_2b_hash():
    assert verify_password_sync("secret1", bcrypt.hashpw(b"secret1", bcrypt.gensalt(4)).decode())


def test_long_password_truncated_like_bcryptjs():
    long_pw = "x" * 80
    hashed = bcrypt.hashpw(long_pw.encode()[:72], bcrypt.gensalt(4, prefix=b"2a")).decode()
    assert verify_password_sync(long_pw, hashed)


def test_invalid_hash_is_rejected():
    assert not verify_password_sync("secret1", "plain-text")
    assert not verify_password_sync("secret1", "$2a$10$broken")


# ---------- sessions ----------


async def test_token_stored_hashed_and_session_loaded(app):
    db = app.state.db
    user = await make_user(db)
    token = await create_session(db, user["_id"], app.state.settings)
    stored = await db.sessions.find_one({"user": user["_id"]})
    assert stored["_id"] == hash_token(token) and token not in str(stored)
    assert (await get_session(db, token))["user"] == user["_id"]


async def test_session_expires_after_7_days(app):
    db = app.state.db
    user = await make_user(db)
    token = await create_session(db, user["_id"], app.state.settings)
    stored = await db.sessions.find_one({"_id": hash_token(token)})
    assert stored["expiresAt"] - stored["createdAt"] == timedelta(days=7)
    await db.sessions.update_one({"_id": hash_token(token)}, {"$set": {"expiresAt": now_ist() - timedelta(seconds=1)}})
    assert await get_session(db, token) is None


def test_cookie_attributes(settings):
    response = Response()
    set_session_cookie(response, "tok", settings)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("akrf_session=tok;")
    for part in ("HttpOnly", "Max-Age=604800", "Path=/", "SameSite=lax", "Secure"):
        assert part in cookie
    assert "Domain" not in cookie


# ---------- uploads ----------


def _upload(data: bytes, filename: str = "a.png", content_type: str = "image/png") -> UploadFile:
    import io

    return UploadFile(io.BytesIO(data), size=len(data), filename=filename,
                      headers=Headers({"content-type": content_type}))


def test_type_detected_by_magic_bytes():
    assert detect_image(PNG) == (".png", "image/png")
    assert detect_image(JPEG) == (".jpg", "image/jpeg")
    assert detect_image(WEBP) == (".webp", "image/webp")
    assert detect_image(FAKE_PNG) is None
    assert detect_image(b"GIF89a....") is None


async def test_disallowed_type_rejected():
    with pytest.raises(ValidationFailed) as exc:
        await extract_image(FormData([("image", _upload(FAKE_PNG))]), 5 * 1024 * 1024)
    assert exc.value.message == "Only JPG, PNG and WebP images are allowed"


async def test_oversize_rejected_413():
    big = PNG + b"\x00" * (1024 * 1024)
    with pytest.raises(PayloadTooLarge) as exc:
        await extract_image(FormData([("image", _upload(big))]), 1024 * 1024)
    assert exc.value.status_code == 413 and exc.value.message == "Image must be under 1 MB"


async def test_wrong_field_or_multiple_files_rejected():
    with pytest.raises(ValidationFailed):
        await extract_image(FormData([("photo", _upload(PNG))]), 10**6)
    with pytest.raises(ValidationFailed) as exc:
        await extract_image(FormData([("image", _upload(PNG)), ("image", _upload(PNG))]), 10**6)
    assert exc.value.message == "Only one image file is allowed"


async def test_empty_file_part_means_no_file():
    assert await extract_image(FormData([("image", _upload(b"", filename=""))]), 10**6) is None
    assert await extract_image(FormData([("name", "x")]), 10**6) is None


async def test_stored_name_pattern_and_relative_path(tmp_path):
    store = UploadStore(tmp_path / "up")
    image = await extract_image(FormData([("image", _upload(JPEG, "Holiday PIC.JPEG"))]), 10**6)
    stored = await store.save(image)
    assert re.fullmatch(r"/uploads/\d{13}-\d{1,10}\.jpg", stored)
    name = stored.rsplit("/", 1)[1]
    assert (tmp_path / "up" / name).read_bytes() == JPEG
    await store.delete(stored)
    assert not (tmp_path / "up" / name).exists()
    await store.delete(stored)  # missing file is ignored
    await store.delete("/elsewhere/x.png")
    await store.delete("/uploads/../secret")

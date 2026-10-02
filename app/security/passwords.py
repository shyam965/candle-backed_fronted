"""bcrypt hashing compatible with the existing `$2a$10$` hashes (FR-017, D-05)."""

from __future__ import annotations

import bcrypt
from anyio import to_thread

BCRYPT_ROUNDS = 10
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 6


def hash_password_sync(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS, prefix=b"2a")
    return bcrypt.hashpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], salt).decode("ascii")


def verify_password_sync(password: str, hashed: str) -> bool:
    if not isinstance(hashed, str) or not hashed.startswith(("$2a$", "$2b$", "$2y$")):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], hashed.encode("ascii"))
    except ValueError:
        return False


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(hash_password_sync, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await to_thread.run_sync(verify_password_sync, password, hashed)

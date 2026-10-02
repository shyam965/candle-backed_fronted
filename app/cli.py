"""Operator commands (D-23). No web endpoint can create admins (BR-04).

Usage:
    python -m app.cli promote-admin <email>
    python -m app.cli demote-admin <email>
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import Settings, get_settings
from app.core.documents import utcnow
from app.db import connect
from app.services.auth_service import normalize_email


async def set_role(settings: Settings, email: str, role: str) -> bool:
    client, db = await connect(settings)
    try:
        result = await db.users.update_one({"email": normalize_email(email)},
                                           {"$set": {"role": role, "updatedAt": utcnow()}})
        return result.matched_count == 1
    finally:
        await client.close()


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AK Royal Flames admin tools")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("promote-admin", "demote-admin"):
        sub.add_parser(name).add_argument("email")
    args = parser.parse_args(argv)
    role = "admin" if args.command == "promote-admin" else "user"
    found = asyncio.run(set_role(settings or get_settings(), args.email, role))
    if not found:
        print(f"No user with email {args.email}", file=sys.stderr)
        return 1
    print(f"{args.email} is now '{role}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

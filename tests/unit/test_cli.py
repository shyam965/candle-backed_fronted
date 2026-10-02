"""Operator CLI (D-23)."""

from __future__ import annotations

import uuid

from pymongo import MongoClient

from app.cli import main
from app.config import Settings
from tests.conftest import TEST_MONGO_URI


def test_promote_and_demote(capsys):
    name = f"akrf_test_cli_{uuid.uuid4().hex[:8]}"
    settings = Settings(_env_file=None, mongo_uri=TEST_MONGO_URI, mongo_db_name=name, secret_key="c" * 40)
    sync = MongoClient(TEST_MONGO_URI)
    try:
        sync[name].users.insert_one({"email": "asha@example.com", "role": "user", "name": "Asha", "password": "x"})
        assert main(["promote-admin", "  ASHA@example.com "], settings) == 0
        assert sync[name].users.find_one()["role"] == "admin"
        assert main(["demote-admin", "asha@example.com"], settings) == 0
        assert sync[name].users.find_one()["role"] == "user"
        assert main(["promote-admin", "nobody@example.com"], settings) == 1
        assert "No user" in capsys.readouterr().err
    finally:
        sync.drop_database(name)
        sync.close()

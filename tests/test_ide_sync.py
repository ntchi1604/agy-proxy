"""
Unit tests for IDE sync (importing VS Code / Cloud Code accounts).
"""

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from agy_proxy.auth.pool import AccountPool
from agy_proxy.ide_sync import get_vscdb_path, sync_ide_accounts


class TestIDESync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.accounts_file = Path(self.temp_dir.name) / "accounts.json"
        self.pool = AccountPool(accounts_file=self.accounts_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_vscdb_path(self):
        # Simply ensure get_vscdb_path runs without error
        res = get_vscdb_path()
        self.assertTrue(res is None or isinstance(res, Path))

    def test_sync_ide_accounts_imports_tokens(self):
        db_path = Path(self.temp_dir.name) / "state.vscdb"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")

        payload = {
            "accounts": [
                {
                    "email": "ide_user@example.com",
                    "refresh_token": "rf_ide_test_12345",
                    "access_token": "acc_ide_test_12345",
                }
            ]
        }
        cursor.execute(
            "INSERT INTO ItemTable VALUES (?, ?)",
            ("cloudcode.accounts", json.dumps(payload)),
        )
        conn.commit()
        conn.close()

        with patch("agy_proxy.ide_sync.get_vscdb_path", return_value=db_path):
            count = sync_ide_accounts(self.pool)
            self.assertEqual(count, 1)

            # Account was added to pool
            matching = [a for a in self.pool.accounts.values() if a.email == "ide_user@example.com"]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].refresh_token, "rf_ide_test_12345")

            # Calling again does not duplicate
            count2 = sync_ide_accounts(self.pool)
            self.assertEqual(count2, 0)

    def test_sync_ide_accounts_no_vscdb(self):
        with patch("agy_proxy.ide_sync.get_vscdb_path", return_value=None):
            count = sync_ide_accounts(self.pool)
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()

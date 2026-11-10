import contextlib
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "supabase_live_check.py"
spec = importlib.util.spec_from_file_location("supabase_live_check_under_test", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeCursor:
    def __init__(self, missing=()):
        self.missing = set(missing)
        self.last = None
    def execute(self, sql, params=None):
        self.last = (sql, params)
    def fetchone(self):
        if self.last[0] == "SELECT 1":
            return (1,)
        names = self.last[1]
        return tuple(None if name.rsplit(".", 1)[-1] in self.missing else name for name in names)
    def __enter__(self): return self
    def __exit__(self, *args): return False


class FakeConnection:
    def __init__(self, missing=()): self.cursor_obj = FakeCursor(missing)
    def cursor(self): return self.cursor_obj
    def __enter__(self): return self
    def __exit__(self, *args): return False


class SupabaseLiveCheckTests(unittest.TestCase):
    def run_capture(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = mod.main()
        return code, json.loads(output.getvalue())

    def test_missing_dsn_does_not_attempt_connection(self):
        with patch.dict(os.environ, {}, clear=True):
            code, result = self.run_capture()
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "configuration")

    def test_all_expected_tables_pass(self):
        fake = types.ModuleType("psycopg")
        fake.connect = lambda *args, **kwargs: FakeConnection()
        with patch.dict(sys.modules, {"psycopg": fake}), patch.dict(os.environ, {"DATABASE_URL": "postgresql://safe-placeholder"}, clear=True):
            code, result = self.run_capture()
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_tables"], [])

    def test_missing_tables_fail_even_when_database_is_reachable(self):
        fake = types.ModuleType("psycopg")
        fake.connect = lambda *args, **kwargs: FakeConnection(missing={"chat_workspace_files"})
        with patch.dict(sys.modules, {"psycopg": fake}), patch.dict(os.environ, {"DATABASE_URL": "postgresql://safe-placeholder"}, clear=True):
            code, result = self.run_capture()
        self.assertEqual(code, 1)
        self.assertTrue(result["database_test"].startswith("SELECT 1"))
        self.assertIn("chat_workspace_files", result["missing_tables"])


if __name__ == "__main__":
    unittest.main()

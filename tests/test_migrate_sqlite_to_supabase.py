import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import migrate_sqlite_to_supabase as migration


class FakeCursor:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class FakeTarget:
    def __init__(self):
        self.statements = []
        self._next_user_id = 9001

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).lower().split())
        self.statements.append((normalized, params))
        if normalized.startswith("select count(*) from chat_messages"):
            return FakeCursor(one=(0,))
        if normalized.startswith("select id from users where lower(username)"):
            return FakeCursor(one=None)
        if normalized.startswith("insert into users") and "returning id" in normalized:
            self._next_user_id += 1
            return FakeCursor(one=(self._next_user_id,))
        if normalized.startswith("select api_key_enc, min(priority)"):
            return FakeCursor(many=[])
        return FakeCursor()


class FakePsycopg:
    def __init__(self, target):
        self.target = target

    def connect(self, *args, **kwargs):
        return self.target


def build_source(path, with_project_tables=True):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, api_key_enc TEXT, google_api_key_enc TEXT,
            xkiro_api_key_enc TEXT, created_at TEXT
        );
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, role TEXT NOT NULL,
            parts_json TEXT NOT NULL, display_text TEXT NOT NULL, created_at TEXT,
            conversation_id TEXT NOT NULL DEFAULT 'default'
        );
        INSERT INTO users VALUES (7,'tester','hash','user',NULL,NULL,NULL,'2026-01-01');
        INSERT INTO chat_messages VALUES (1,7,'user','[]','hello','2026-01-02','conversation-A');
    """)
    if with_project_tables:
        conn.executescript("""
            CREATE TABLE project_checkpoints (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, label TEXT NOT NULL,
                task_summary TEXT NOT NULL DEFAULT '', files_json TEXT NOT NULL,
                file_count INTEGER NOT NULL, total_bytes INTEGER NOT NULL,
                content_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
            );
            INSERT INTO project_checkpoints VALUES
              ('cp-1',7,'Checkpoint','repair login','[{"path":"app.py","content":"ok"}]',1,2,'sha256-demo','2026-01-03');
            CREATE TABLE alpha_project_memory (
                user_id INTEGER NOT NULL, project_key TEXT NOT NULL, project_name TEXT NOT NULL,
                memory_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id,project_key)
            );
            INSERT INTO alpha_project_memory VALUES
              (7,'alpha-project','Alpha Project','{"stack":"Flask"}','2026-01-04');
        """)
    conn.commit()
    conn.close()


class SupabaseMigrationTests(unittest.TestCase):
    def test_migrates_checkpoints_project_memory_and_conversation_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "app.db"
            build_source(source)
            target = FakeTarget()
            with patch.object(migration, "_load_psycopg", return_value=FakePsycopg(target)), \
                 patch.object(migration, "pg_dsn", return_value="postgresql://test"):
                counts = migration.migrate(source)

        self.assertEqual(counts["users"], 1)
        self.assertEqual(counts["messages"], 1)
        self.assertEqual(counts["project_checkpoints"], 1)
        self.assertEqual(counts["project_memories"], 1)
        self.assertTrue(any("alter table chat_messages add column if not exists conversation_id" in sql for sql, _ in target.statements))

        message = next(params for sql, params in target.statements if sql.startswith("insert into chat_messages"))
        self.assertEqual(message[0], 9002)
        self.assertEqual(message[5], "conversation-A")

        checkpoint = next((sql, params) for sql, params in target.statements if sql.startswith("insert into project_checkpoints"))
        self.assertEqual(checkpoint[1][0], "cp-1")
        self.assertEqual(checkpoint[1][1], 9002)
        self.assertIn("on conflict(id) do nothing", checkpoint[0])

        memory = next((sql, params) for sql, params in target.statements if sql.startswith("insert into alpha_project_memory"))
        self.assertEqual(memory[1][0], 9002)
        self.assertEqual(memory[1][1], "alpha-project")
        self.assertIn("on conflict(user_id,project_key) do update", memory[0])

    def test_legacy_database_without_project_tables_still_migrates(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "legacy.db"
            build_source(source, with_project_tables=False)
            target = FakeTarget()
            with patch.object(migration, "_load_psycopg", return_value=FakePsycopg(target)), \
                 patch.object(migration, "pg_dsn", return_value="postgresql://test"):
                counts = migration.migrate(source)
        self.assertEqual(counts["project_checkpoints"], 0)
        self.assertEqual(counts["project_memories"], 0)
        self.assertEqual(counts["messages"], 1)


if __name__ == "__main__":
    unittest.main()

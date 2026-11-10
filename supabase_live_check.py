#!/usr/bin/env python3
"""Read-only Supabase PostgreSQL connectivity and schema-presence check.

Reads DATABASE_URL/SUPABASE_DB_URL from the environment. Never prints the DSN,
username, password, host, or database contents. This script does not migrate data.
"""
from __future__ import annotations

import json
import os
import sys

EXPECTED_TABLES = (
    "users",
    "chat_messages",
    "chat_workspace_files",
    "project_checkpoints",
    "alpha_project_memory",
)


def main() -> int:
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        print(json.dumps({"ok": False, "stage": "configuration", "error": "DATABASE_URL is not set"}, ensure_ascii=False))
        return 2

    try:
        import psycopg
    except Exception:
        print(json.dumps({"ok": False, "stage": "dependency", "error": "psycopg is not installed; install requirements.txt"}, ensure_ascii=False))
        return 2

    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"

    try:
        with psycopg.connect(dsn, connect_timeout=10, prepare_threshold=None) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                one = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT " + ", ".join("to_regclass(%s)" for _ in EXPECTED_TABLES),
                    tuple("public." + name for name in EXPECTED_TABLES),
                )
                values = cursor.fetchone()
        tables = {name: value is not None for name, value in zip(EXPECTED_TABLES, values)}
        missing_tables = [name for name, found in tables.items() if not found]
        result = {
            "ok": one == 1 and not missing_tables,
            "stage": "connected",
            "database_test": "SELECT 1 passed",
            "schema_tables": tables,
            "missing_tables": missing_tables,
            "note": (
                "Read-only connectivity and schema check only. No data was changed or migrated."
                if not missing_tables else
                "Database is reachable, but one or more Alpha tables are missing. Deploy/restart the app to initialize schema, then rerun."
            ),
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0 if one == 1 and not missing_tables else 1
    except Exception as exc:
        # Deliberately omit str(exc): driver errors can embed connection details.
        print(json.dumps({
            "ok": False,
            "stage": "connection",
            "error_type": type(exc).__name__,
            "message": "Connection or read-only query failed. Check DATABASE_URL, Supabase pooler mode, SSL, and network access.",
        }, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

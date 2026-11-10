#!/usr/bin/env python3
"""One-time, transactional migration from Alpha AI's local SQLite DB to Supabase."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

def _load_psycopg():
    try:
        import psycopg
        return psycopg
    except ImportError as exc:  # pragma: no cover - exercised on user's machine
        raise SystemExit("Missing dependency. Run: python -m pip install 'psycopg[binary]'") from exc

ALPHA_MAX_MODEL = "qwen/qwen3.7-max:free"
ALPHA_MAX_FALLBACK_MODEL = "qwen/qwen3.6-max-preview:free"
LEGACY_ALPHA_MAX_MODEL = "deepseek-v4.1-flash:free"
XKIRO_BASE_URL = "https://api.xkiro.com/v1/chat/completions"
GLOBAL_PROMPT_KEY = "__global__"
GEMMA_MODEL = "gemma-4-26b-a4b-it"


def pg_dsn() -> str:
    dsn = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        raise SystemExit("Set DATABASE_URL to the Supabase PostgreSQL connection string first.")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return bool(found)


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def value(row: sqlite3.Row, available: set[str], name: str, default=None):
    return row[name] if name in available else default


def migrate(source_path: Path) -> dict[str, int]:
    if not source_path.is_file():
        raise SystemExit(f"SQLite database not found: {source_path}")

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA foreign_keys=ON")

    required = {"users", "chat_messages"}
    missing = {name for name in required if not table_exists(source, name)}
    if missing:
        raise SystemExit(f"Source database is missing required tables: {', '.join(sorted(missing))}")

    user_cols = columns(source, "users")
    message_cols = columns(source, "chat_messages")
    source_users = source.execute("SELECT * FROM users ORDER BY id").fetchall()
    source_messages = source.execute("SELECT * FROM chat_messages ORDER BY id").fetchall()
    workspace_cols = columns(source, "chat_workspace_files") if table_exists(source, "chat_workspace_files") else set()
    source_workspace_files = (
        source.execute("SELECT * FROM chat_workspace_files ORDER BY user_id,conversation_id,filename").fetchall()
        if workspace_cols else []
    )
    source_prompts = (
        source.execute("SELECT model_id,prompt,updated_at FROM model_prompts").fetchall()
        if table_exists(source, "model_prompts") else []
    )
    source_routes = (
        source.execute("SELECT * FROM model_api_routes ORDER BY user_id,model_id,priority,id").fetchall()
        if table_exists(source, "model_api_routes") else []
    )
    route_cols = columns(source, "model_api_routes") if table_exists(source, "model_api_routes") else set()
    checkpoint_cols = columns(source, "project_checkpoints") if table_exists(source, "project_checkpoints") else set()
    source_checkpoints = (
        source.execute("SELECT * FROM project_checkpoints ORDER BY user_id,created_at,id").fetchall()
        if checkpoint_cols else []
    )
    memory_cols = columns(source, "alpha_project_memory") if table_exists(source, "alpha_project_memory") else set()
    source_project_memory = (
        source.execute("SELECT * FROM alpha_project_memory ORDER BY user_id,project_key").fetchall()
        if memory_cols else []
    )

    counts = {
        "users": 0, "prompts": 0, "messages": 0, "api_routes": 0,
        "workspace_files": 0, "project_checkpoints": 0, "project_memories": 0,
    }
    psycopg = _load_psycopg()
    dsn = pg_dsn()

    try:
        # Do not duplicate chat histories accidentally. Users/admin may already exist
        # because the Render service creates its initial admin and schema on first boot.
        with psycopg.connect(dsn, connect_timeout=15, prepare_threshold=None) as target:
            target.execute(
                """CREATE TABLE IF NOT EXISTS chat_workspace_files (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    conversation_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
                    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
                    UNIQUE(user_id, conversation_id, filename)
                )"""
            )
            target.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_workspace_user_conversation "
                "ON chat_workspace_files(user_id, conversation_id, updated_at)"
            )
            target.execute(
                "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS conversation_id TEXT NOT NULL DEFAULT 'default'"
            )
            target.execute(
                """CREATE TABLE IF NOT EXISTS project_checkpoints (
                    id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    label TEXT NOT NULL,
                    task_summary TEXT NOT NULL DEFAULT '',
                    files_json TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    total_bytes BIGINT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
                )"""
            )
            target.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_checkpoints_user_created "
                "ON project_checkpoints(user_id, created_at)"
            )
            target.execute(
                """CREATE TABLE IF NOT EXISTS alpha_project_memory (
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_key TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    memory_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
                    PRIMARY KEY(user_id, project_key)
                )"""
            )
            target.execute(
                "CREATE INDEX IF NOT EXISTS idx_alpha_project_memory_user_updated "
                "ON alpha_project_memory(user_id, updated_at)"
            )
            existing_messages = target.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
            if existing_messages:
                raise SystemExit(
                    "Supabase already contains chat messages. Migration stopped to avoid duplicates; "
                    "use a fresh Supabase project/database or review it manually."
                )

            user_id_map: dict[int, int] = {}
            for old in source_users:
                old_id = old["id"]
                username = old["username"]
                existing = target.execute(
                    "SELECT id FROM users WHERE lower(username)=lower(%s)", (username,)
                ).fetchone()

                old_values = {
                    "password_hash": old["password_hash"],
                    "role": old["role"],
                    "api_key_enc": value(old, user_cols, "api_key_enc"),
                    "google_api_key_enc": value(old, user_cols, "google_api_key_enc"),
                    "xkiro_api_key_enc": value(old, user_cols, "xkiro_api_key_enc"),
                    "created_at": value(old, user_cols, "created_at"),
                }
                if existing:
                    new_id = existing[0]
                    target.execute(
                        """UPDATE users SET password_hash=%s, role=%s, api_key_enc=%s,
                           google_api_key_enc=%s, xkiro_api_key_enc=%s,
                           created_at=COALESCE(%s, created_at) WHERE id=%s""",
                        (
                            old_values["password_hash"], old_values["role"],
                            old_values["api_key_enc"], old_values["google_api_key_enc"],
                            old_values["xkiro_api_key_enc"], old_values["created_at"], new_id,
                        ),
                    )
                else:
                    new_id = target.execute(
                        """INSERT INTO users
                           (username,password_hash,role,api_key_enc,google_api_key_enc,xkiro_api_key_enc,created_at)
                           VALUES(%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text))
                           RETURNING id""",
                        (
                            username, old_values["password_hash"], old_values["role"],
                            old_values["api_key_enc"], old_values["google_api_key_enc"],
                            old_values["xkiro_api_key_enc"], old_values["created_at"],
                        ),
                    ).fetchone()[0]
                user_id_map[int(old_id)] = int(new_id)
                counts["users"] += 1

            source_prompt_map = {prompt["model_id"]: prompt for prompt in source_prompts}
            for prompt in source_prompts:
                target.execute(
                    """INSERT INTO model_prompts(model_id,prompt,updated_at)
                       VALUES(%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text))
                       ON CONFLICT(model_id) DO UPDATE SET
                       prompt=EXCLUDED.prompt, updated_at=EXCLUDED.updated_at""",
                    (prompt["model_id"], prompt["prompt"], prompt["updated_at"]),
                )
                counts["prompts"] += 1

            # The new application uses one shared administrator prompt. For an
            # older database, promote the former Alpha 3.1 Max prompt to global
            # unless a true global prompt already exists in the source database.
            if GLOBAL_PROMPT_KEY in source_prompt_map:
                global_prompt = source_prompt_map[GLOBAL_PROMPT_KEY]["prompt"]
            elif LEGACY_ALPHA_MAX_MODEL in source_prompt_map:
                global_prompt = source_prompt_map[LEGACY_ALPHA_MAX_MODEL]["prompt"]
            else:
                prompt_file = source_path.parent / "system_prompt.txt"
                global_prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else (
                    "You are an expert coding assistant. Preserve unrelated project functionality. "
                    "Never claim tests passed unless they were run. Always answer in Arabic."
                )
            target.execute(
                """INSERT INTO model_prompts(model_id,prompt,updated_at)
                   VALUES(%s,%s,CURRENT_TIMESTAMP::text)
                   ON CONFLICT(model_id) DO UPDATE SET
                   prompt=EXCLUDED.prompt, updated_at=CURRENT_TIMESTAMP::text""",
                (GLOBAL_PROMPT_KEY, global_prompt),
            )
            counts["prompts"] += 1
            # Make missing model prompt rows inherit the shared prompt; preserve
            # explicit per-model prompts copied from the source database.
            for model_id in (ALPHA_MAX_MODEL, GEMMA_MODEL):
                if model_id not in source_prompt_map:
                    target.execute(
                        """INSERT INTO model_prompts(model_id,prompt,updated_at)
                           VALUES(%s,%s,CURRENT_TIMESTAMP::text)
                           ON CONFLICT(model_id) DO UPDATE SET
                           prompt=EXCLUDED.prompt, updated_at=CURRENT_TIMESTAMP::text""",
                        (model_id, global_prompt),
                    )
                    counts["prompts"] += 1

            source_route_pairs: set[tuple[int, str]] = set()
            for route in source_routes:
                old_user_id = int(route["user_id"])
                if old_user_id not in user_id_map:
                    continue
                source_route_pairs.add((old_user_id, route["model_id"]))
                target.execute(
                    """INSERT INTO model_api_routes
                       (user_id,model_id,priority,provider,base_url,upstream_model,api_key_enc,created_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text))
                       ON CONFLICT(user_id,model_id,priority) DO NOTHING""",
                    (
                        user_id_map[old_user_id], route["model_id"], route["priority"],
                        route["provider"], value(route, route_cols, "base_url", ""),
                        route["upstream_model"], route["api_key_enc"],
                        value(route, route_cols, "created_at"),
                    ),
                )
                counts["api_routes"] += 1

            # Migrate legacy API-key columns and normalize the Alpha 3.1 Max
            # route pool to an ordered primary/fallback pair for every Xkiro key.
            for old in source_users:
                old_user_id = int(old["id"])
                mapped_user_id = user_id_map.get(old_user_id)
                if mapped_user_id is None:
                    continue

                # Preserve all configured Xkiro keys from new-format route rows.
                xkiro_rows = target.execute(
                    """SELECT api_key_enc, MIN(priority) AS first_priority
                       FROM model_api_routes
                       WHERE user_id=%s AND model_id=%s AND provider='xkiro'
                       GROUP BY api_key_enc ORDER BY first_priority""",
                    (mapped_user_id, ALPHA_MAX_MODEL),
                ).fetchall()
                encrypted_xkiro_keys = [row[0] for row in xkiro_rows]
                if not encrypted_xkiro_keys:
                    legacy_xkiro_key = value(old, user_cols, "xkiro_api_key_enc")
                    if legacy_xkiro_key:
                        encrypted_xkiro_keys = [legacy_xkiro_key]

                if encrypted_xkiro_keys:
                    target.execute(
                        "DELETE FROM model_api_routes WHERE user_id=%s AND model_id=%s AND provider='xkiro'",
                        (mapped_user_id, ALPHA_MAX_MODEL),
                    )
                    for key_index, encrypted_key in enumerate(encrypted_xkiro_keys):
                        for model_index, upstream_model in enumerate(
                            (ALPHA_MAX_MODEL, ALPHA_MAX_FALLBACK_MODEL)
                        ):
                            target.execute(
                                """INSERT INTO model_api_routes
                                   (user_id,model_id,priority,provider,base_url,upstream_model,api_key_enc)
                                   VALUES(%s,%s,%s,'xkiro',%s,%s,%s)
                                   ON CONFLICT(user_id,model_id,priority) DO NOTHING""",
                                (mapped_user_id, ALPHA_MAX_MODEL, key_index * 2 + model_index + 1,
                                 XKIRO_BASE_URL, upstream_model, encrypted_key),
                            )
                            counts["api_routes"] += 1

                    target.execute(
                        "UPDATE users SET xkiro_api_key_enc=%s WHERE id=%s",
                        (encrypted_xkiro_keys[0], mapped_user_id),
                    )

                # Google / Alpha 2.7 Flash remains on its original route.
                legacy_google_key = value(old, user_cols, "google_api_key_enc") or value(
                    old, user_cols, "api_key_enc"
                )
                if legacy_google_key and (old_user_id, GEMMA_MODEL) not in source_route_pairs:
                    target.execute(
                        """INSERT INTO model_api_routes
                           (user_id,model_id,priority,provider,base_url,upstream_model,api_key_enc)
                           VALUES(%s,%s,1,'google','',%s,%s)
                           ON CONFLICT(user_id,model_id,priority) DO NOTHING""",
                        (mapped_user_id, GEMMA_MODEL, GEMMA_MODEL, legacy_google_key),
                    )
                    counts["api_routes"] += 1

            for message in source_messages:
                old_user_id = int(message["user_id"])
                if old_user_id not in user_id_map:
                    continue
                target.execute(
                    """INSERT INTO chat_messages
                       (user_id,role,parts_json,display_text,created_at,conversation_id)
                       VALUES(%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text),%s)""",
                    (
                        user_id_map[old_user_id], message["role"], message["parts_json"],
                        message["display_text"], value(message, message_cols, "created_at"),
                        value(message, message_cols, "conversation_id", "default") or "default",
                    ),
                )
                counts["messages"] += 1

            # Preserve the new per-conversation Workspace files when a local
            # SQLite database is moved to Supabase. Older databases have no
            # such table and simply contribute zero rows.
            for workspace_file in source_workspace_files:
                old_user_id = int(workspace_file["user_id"])
                if old_user_id not in user_id_map:
                    continue
                target.execute(
                    """INSERT INTO chat_workspace_files
                       (id,user_id,conversation_id,filename,content,created_at,updated_at)
                       VALUES(%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text),
                              COALESCE(%s,CURRENT_TIMESTAMP::text))
                       ON CONFLICT DO NOTHING""",
                    (
                        value(workspace_file, workspace_cols, "id"),
                        user_id_map[old_user_id],
                        value(workspace_file, workspace_cols, "conversation_id", "default"),
                        value(workspace_file, workspace_cols, "filename"),
                        value(workspace_file, workspace_cols, "content", ""),
                        value(workspace_file, workspace_cols, "created_at"),
                        value(workspace_file, workspace_cols, "updated_at"),
                    ),
                )
                counts["workspace_files"] += 1

            # Keep project snapshots and long-lived Project Intelligence memory in
            # Supabase too. These tables are per-user, so always remap the SQLite
            # user ID before inserting. Existing snapshot IDs are never overwritten.
            for checkpoint in source_checkpoints:
                old_user_id = int(checkpoint["user_id"])
                if old_user_id not in user_id_map:
                    continue
                target.execute(
                    """INSERT INTO project_checkpoints
                       (id,user_id,label,task_summary,files_json,file_count,total_bytes,content_sha256,created_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text))
                       ON CONFLICT(id) DO NOTHING""",
                    (
                        checkpoint["id"], user_id_map[old_user_id], checkpoint["label"],
                        value(checkpoint, checkpoint_cols, "task_summary", ""),
                        checkpoint["files_json"], checkpoint["file_count"],
                        checkpoint["total_bytes"], checkpoint["content_sha256"],
                        value(checkpoint, checkpoint_cols, "created_at"),
                    ),
                )
                counts["project_checkpoints"] += 1

            for memory in source_project_memory:
                old_user_id = int(memory["user_id"])
                if old_user_id not in user_id_map:
                    continue
                target.execute(
                    """INSERT INTO alpha_project_memory
                       (user_id,project_key,project_name,memory_json,updated_at)
                       VALUES(%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP::text))
                       ON CONFLICT(user_id,project_key) DO UPDATE SET
                         project_name=EXCLUDED.project_name,
                         memory_json=EXCLUDED.memory_json,
                         updated_at=EXCLUDED.updated_at""",
                    (
                        user_id_map[old_user_id], memory["project_key"], memory["project_name"],
                        memory["memory_json"], value(memory, memory_cols, "updated_at"),
                    ),
                )
                counts["project_memories"] += 1

        # Supabase tables use BIGSERIAL for IDs; no manual sequence reset is needed
        # because this importer lets Postgres assign fresh IDs.
    finally:
        source.close()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Move Alpha AI data from SQLite to Supabase PostgreSQL.")
    parser.add_argument("--source", default="app.db", help="Path to the existing local SQLite database (default: app.db)")
    args = parser.parse_args()
    result = migrate(Path(args.source).expanduser().resolve())
    print("Migration completed successfully:")
    for key, count in result.items():
        print(f"  {key}: {count}")
    print("Keep the original app.db and .api_encryption.key as backups until you verify the deployed app.")


if __name__ == "__main__":
    main()

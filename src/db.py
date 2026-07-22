"""Database connection and migration runner.

schema/schema.sql is the canonical initial DDL and is applied as migration
version 1. Later changes go in schema/migrations/NNN_name.sql (forward-only,
applied in numeric order). Applied versions are tracked in schema_migrations.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = REPO_ROOT / "schema" / "schema.sql"
MIGRATIONS_DIR = REPO_ROOT / "schema" / "migrations"

_MIGRATION_NAME = re.compile(r"^(\d{3})_.+\.sql$")


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a connection with the pragmas every caller needs."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply schema.sql (version 1) and any pending numbered migrations.

    Returns the list of versions applied in this call. Idempotent.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  version INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  applied_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ")"
    )
    applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}

    pending: list[tuple[int, str, Path]] = []
    if 1 not in applied:
        pending.append((1, "initial (schema/schema.sql)", SCHEMA_SQL))
    if MIGRATIONS_DIR.is_dir():
        for path in sorted(MIGRATIONS_DIR.iterdir()):
            m = _MIGRATION_NAME.match(path.name)
            if not m:
                continue
            version = int(m.group(1))
            if version == 1:
                raise ValueError(
                    f"{path.name}: version 001 is reserved for schema/schema.sql"
                )
            if version not in applied:
                pending.append((version, path.name, path))

    pending.sort(key=lambda item: item[0])
    ran: list[int] = []
    for version, name, path in pending:
        conn.executescript(path.read_text(encoding="utf-8"))
        # executescript commits and resets pragmas set on the connection
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)", (version, name)
        )
        conn.commit()
        ran.append(version)
    return ran


def open_db(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Connect and bring the schema up to date."""
    conn = connect(db_path)
    migrate(conn)
    return conn

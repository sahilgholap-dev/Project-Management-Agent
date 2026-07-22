"""One-time bootstrap: seed the platform client row and the first
platform_admin, printing its credentials exactly once.

Run:  python -m api.bootstrap [db_path] [email]

The "__platform__" client row exists only because users.client_id is NOT
NULL and the first platform_admin must hang off something — a v1
simplification to revisit if multi-tenant is ever built (OQ-1, approved).
It is invisible to the admin endpoints (they filter it out).
"""

from __future__ import annotations

import sys
from pathlib import Path

from api import security
from api.deps import PLATFORM_CLIENT_NAME
from api.main import DEFAULT_DB_PATH
from src import db


def seed(db_path: str | Path = DEFAULT_DB_PATH,
         email: str = "platform-admin@nexus.local") -> dict:
    conn = db.open_db(db_path)
    try:
        if conn.execute(
            "SELECT 1 FROM users WHERE role = 'platform_admin'"
        ).fetchone():
            raise SystemExit("bootstrap refused: a platform_admin already exists")

        row = conn.execute(
            "SELECT client_id FROM clients WHERE name = ?", (PLATFORM_CLIENT_NAME,)
        ).fetchone()
        client_id = row["client_id"] if row else conn.execute(
            "INSERT INTO clients (name) VALUES (?)", (PLATFORM_CLIENT_NAME,)
        ).lastrowid

        password = security.generate_password()
        cur = conn.execute(
            "INSERT INTO users (client_id, email, display_name, role, invite_status)"
            " VALUES (?, ?, 'Platform Admin', 'platform_admin', 'invited')",
            (client_id, email),
        )
        conn.execute(
            "INSERT INTO auth_credentials (user_id, password_hash) VALUES (?, ?)",
            (cur.lastrowid, security.hash_password(password)),
        )
        conn.commit()
        return {"user_id": cur.lastrowid, "email": email, "password": password}
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    email = sys.argv[2] if len(sys.argv) > 2 else "platform-admin@nexus.local"
    creds = seed(db_path, email)
    print("platform_admin created — credentials shown ONCE, store them now:")
    print(f"  email:    {creds['email']}")
    print(f"  password: {creds['password']}")

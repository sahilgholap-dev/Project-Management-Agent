"""FastAPI dependencies: per-request DB connection and role-gated auth.

The API is the real permission boundary (the Next.js middleware is UX only):
every endpoint declares its allowed roles via require_role, backed by the
signed session cookie and users.role.
"""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from api import security
from src import db

SESSION_COOKIE = "nexus_session"

# The platform client row exists only so the first platform_admin satisfies
# users.client_id NOT NULL — a v1 simplification to revisit if multi-tenant
# is ever built (FRONTEND_IMPLEMENTATION_PLAN.md OQ-1).
PLATFORM_CLIENT_NAME = "__platform__"


def get_conn(request: Request):
    """One connection per request; schema is migrated once at app startup.
    check_same_thread=False because FastAPI may run the dependency and the
    endpoint body on different threadpool threads (sequential use only)."""
    conn = db.connect(request.app.state.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


def current_user(request: Request, conn: Conn) -> sqlite3.Row:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = security.parse_session(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = conn.execute(
        "SELECT user_id, client_id, email, display_name, role, invite_status"
        " FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if user is None or user["invite_status"] == "disabled":
        raise HTTPException(status_code=401, detail="account unavailable")
    return user


User = Annotated[sqlite3.Row, Depends(current_user)]


def require_role(*roles: str):
    def dependency(user: User) -> sqlite3.Row:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return Depends(dependency)

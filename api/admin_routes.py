"""Admin portal endpoints (platform_admin only) — PRD section 4 steps 1-2.

"Send invite" constraint (by design, not an oversight): this system has zero
outbound-send capability, enforced by the import allowlist. Creating a user
GENERATES credentials and returns them in the response EXACTLY ONCE for
on-screen display and manual handoff. No email, ever. The password hash is
all that is stored; the plaintext is never queryable again.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import security
from api.deps import PLATFORM_CLIENT_NAME, Conn, require_role

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[require_role("platform_admin")])


class ClientBody(BaseModel):
    name: str


class UserBody(BaseModel):
    email: str
    display_name: str
    role: str  # client_admin | member — platform_admins come only from bootstrap


@router.post("/clients", status_code=201)
def create_client(body: ClientBody, conn: Conn) -> dict:
    existing = conn.execute(
        "SELECT client_id FROM clients WHERE name != ?", (PLATFORM_CLIENT_NAME,)
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="a client already exists — v1 is single-client (PRD section 1)",
        )
    cur = conn.execute("INSERT INTO clients (name) VALUES (?)", (body.name,))
    conn.commit()
    return {"client_id": cur.lastrowid, "name": body.name}


@router.post("/users", status_code=201)
def create_user(body: UserBody, conn: Conn) -> dict:
    if body.role not in ("client_admin", "member"):
        raise HTTPException(status_code=422, detail="role must be client_admin or member")
    client = conn.execute(
        "SELECT client_id FROM clients WHERE name != ?", (PLATFORM_CLIENT_NAME,)
    ).fetchone()
    if client is None:
        raise HTTPException(status_code=409, detail="create the client company first")
    if conn.execute(
        "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?)", (body.email,)
    ).fetchone():
        raise HTTPException(status_code=409, detail="a user with this email exists")

    password = security.generate_password()
    cur = conn.execute(
        "INSERT INTO users (client_id, email, display_name, role, invite_status)"
        " VALUES (?, ?, ?, ?, 'invited')",
        (client["client_id"], body.email, body.display_name, body.role),
    )
    conn.execute(
        "INSERT INTO auth_credentials (user_id, password_hash) VALUES (?, ?)",
        (cur.lastrowid, security.hash_password(password)),
    )
    conn.commit()
    # shown once on screen for manual handoff — never stored, never sent
    return {
        "user_id": cur.lastrowid,
        "email": body.email,
        "role": body.role,
        "password": password,
        "handoff_note": "Displayed once. Relay these credentials manually —"
                        " this system sends nothing.",
    }

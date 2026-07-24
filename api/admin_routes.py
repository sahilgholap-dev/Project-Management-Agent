"""Admin portal endpoints (platform_admin only) — PRD section 4 steps 1-2.

"Send invite" constraint (by design, not an oversight): this system has zero
outbound-send capability, enforced by the import allowlist. Creating a user
GENERATES credentials and returns them in the response EXACTLY ONCE for
on-screen display and manual handoff. No email, ever. The password hash is
all that is stored; the plaintext is never queryable again. The same rule
applies to password resets.

Multi-company: the v1 single-client restriction is lifted — platform_admin
manages any number of client companies, and user creation names its company
explicitly via client_id. Deletes are safe-only: a company with users or
projects cannot be deleted (governance history is never cascaded away), and
users are disabled rather than deleted.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import security
from api.deps import PLATFORM_CLIENT_NAME, Conn, current_user, require_role
from api.errors import backend_errors
from src import config_loader
from src.lib import audit

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[require_role("platform_admin")])


class ClientBody(BaseModel):
    name: str


class UserBody(BaseModel):
    client_id: int
    email: str
    display_name: str
    role: str  # client_admin | member — platform_admins come only from bootstrap


class UserPatch(BaseModel):
    display_name: str | None = None
    role: str | None = None           # client_admin | member
    invite_status: str | None = None  # invited | active | disabled


def _get_client(conn: sqlite3.Connection, client_id: int) -> sqlite3.Row:
    """404 for unknown ids AND for the __platform__ row — the platform row is
    a bootstrap artifact, never a manageable company."""
    row = conn.execute(
        "SELECT client_id, name, created_at FROM clients"
        " WHERE client_id = ? AND name != ?",
        (client_id, PLATFORM_CLIENT_NAME),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such client company")
    return row


def _get_managed_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    """404 for unknown ids and for platform_admin accounts — bootstrap
    accounts are not manageable through the portal."""
    row = conn.execute(
        "SELECT user_id, client_id, email, display_name, role, invite_status"
        " FROM users WHERE user_id = ? AND role != 'platform_admin'",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such manageable user")
    return row


# --- companies -------------------------------------------------------------------

@router.get("/clients")
def list_clients(conn: Conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT c.client_id, c.name, c.created_at,"
        " (SELECT COUNT(*) FROM users u WHERE u.client_id = c.client_id) AS user_count,"
        " (SELECT COUNT(*) FROM projects p WHERE p.client_id = c.client_id) AS project_count"
        " FROM clients c WHERE c.name != ? ORDER BY c.client_id",
        (PLATFORM_CLIENT_NAME,),
    )]


@router.post("/clients", status_code=201)
def create_client(
    body: ClientBody, conn: Conn, admin=Depends(current_user)
) -> dict:
    name = body.name.strip()
    if not name or name == PLATFORM_CLIENT_NAME:
        raise HTTPException(status_code=422, detail="invalid company name")
    if conn.execute(
        "SELECT 1 FROM clients WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone():
        raise HTTPException(status_code=409, detail="a company with this name exists")
    cur = conn.execute("INSERT INTO clients (name) VALUES (?)", (name,))
    audit.log_action(
        conn, skill="admin_portal", action="create_client",
        input_summary={"name": name},
        output_summary={"client_id": cur.lastrowid},
        actor=str(admin["user_id"]),
    )
    conn.commit()
    return {"client_id": cur.lastrowid, "name": name}


@router.patch("/clients/{client_id}")
def rename_client(
    client_id: int, body: ClientBody, conn: Conn, admin=Depends(current_user)
) -> dict:
    existing = _get_client(conn, client_id)
    name = body.name.strip()
    if not name or name == PLATFORM_CLIENT_NAME:
        raise HTTPException(status_code=422, detail="invalid company name")
    if conn.execute(
        "SELECT 1 FROM clients WHERE LOWER(name) = LOWER(?) AND client_id != ?",
        (name, client_id),
    ).fetchone():
        raise HTTPException(status_code=409, detail="a company with this name exists")
    conn.execute("UPDATE clients SET name = ? WHERE client_id = ?", (name, client_id))
    audit.log_action(
        conn, skill="admin_portal", action="rename_client",
        input_summary={"client_id": client_id, "from": existing["name"], "to": name},
        output_summary={"client_id": client_id},
        actor=str(admin["user_id"]),
    )
    conn.commit()
    return {"client_id": client_id, "name": name}


@router.delete("/clients/{client_id}", status_code=204)
def delete_client(client_id: int, conn: Conn, admin=Depends(current_user)) -> None:
    """Safe delete only: a company that has accumulated users or projects is
    part of the governance record and cannot be removed."""
    existing = _get_client(conn, client_id)
    counts = conn.execute(
        "SELECT (SELECT COUNT(*) FROM users WHERE client_id = ?) AS users,"
        " (SELECT COUNT(*) FROM projects WHERE client_id = ?) AS projects",
        (client_id, client_id),
    ).fetchone()
    if counts["users"] or counts["projects"]:
        raise HTTPException(
            status_code=409,
            detail="company has users or projects — disable users instead;"
                   " history is never deleted",
        )
    conn.execute("DELETE FROM client_config WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM clients WHERE client_id = ?", (client_id,))
    audit.log_action(
        conn, skill="admin_portal", action="delete_client",
        input_summary={"client_id": client_id, "name": existing["name"]},
        output_summary={"deleted": True},
        actor=str(admin["user_id"]),
    )
    conn.commit()


# --- per-company config (platform_admin view of the client_admin /config) ---------

@router.get("/clients/{client_id}/config")
def get_client_config(client_id: int, conn: Conn) -> dict:
    _get_client(conn, client_id)
    try:
        return config_loader.load_client_config(conn, client_id)
    except config_loader.ConfigDefectError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.put("/clients/{client_id}/config")
def put_client_config(client_id: int, body: dict, conn: Conn) -> dict:
    _get_client(conn, client_id)
    with backend_errors():
        config_loader.save_client_config(conn, client_id, body)
    return config_loader.load_client_config(conn, client_id)


# --- users -----------------------------------------------------------------------

@router.get("/users")
def list_all_users(conn: Conn) -> list[dict]:
    """Every non-bootstrap user across all companies, with the company name
    joined in for the admin table. No credentials exposed."""
    return [dict(r) for r in conn.execute(
        "SELECT u.user_id, u.client_id, c.name AS client_name, u.email,"
        " u.display_name, u.role, u.invite_status, u.created_at"
        " FROM users u JOIN clients c ON c.client_id = u.client_id"
        " WHERE u.role != 'platform_admin' ORDER BY u.user_id",
    )]


@router.post("/users", status_code=201)
def create_user(body: UserBody, conn: Conn, admin=Depends(current_user)) -> dict:
    if body.role not in ("client_admin", "member"):
        raise HTTPException(status_code=422, detail="role must be client_admin or member")
    client = _get_client(conn, body.client_id)
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
    # audited WITHOUT the password: summaries must never carry the plaintext
    # (the full-dump test asserts it appears nowhere in the database)
    audit.log_action(
        conn, skill="admin_portal", action="create_user",
        input_summary={"email": body.email, "role": body.role,
                       "client_id": client["client_id"]},
        output_summary={"user_id": cur.lastrowid},
        actor=str(admin["user_id"]),
    )
    conn.commit()
    # shown once on screen for manual handoff — never stored, never sent
    return {
        "user_id": cur.lastrowid,
        "client_id": client["client_id"],
        "client_name": client["name"],
        "email": body.email,
        "role": body.role,
        "password": password,
        "handoff_note": "Displayed once. Relay these credentials manually —"
                        " this system sends nothing.",
    }


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, body: UserPatch, conn: Conn, admin=Depends(current_user)
) -> dict:
    user = _get_managed_user(conn, user_id)
    changes: dict = {}
    if body.display_name is not None and body.display_name.strip():
        changes["display_name"] = body.display_name.strip()
    if body.role is not None:
        if body.role not in ("client_admin", "member"):
            raise HTTPException(status_code=422,
                                detail="role must be client_admin or member")
        changes["role"] = body.role
    if body.invite_status is not None:
        if body.invite_status not in ("invited", "active", "disabled"):
            raise HTTPException(status_code=422, detail="invalid invite_status")
        changes["invite_status"] = body.invite_status
    if not changes:
        raise HTTPException(status_code=422, detail="nothing to update")

    assignments = ", ".join(f"{col} = ?" for col in changes)
    conn.execute(
        f"UPDATE users SET {assignments} WHERE user_id = ?",  # noqa: S608 — cols are a fixed allowlist
        (*changes.values(), user_id),
    )
    audit.log_action(
        conn, skill="admin_portal", action="update_user",
        input_summary={"user_id": user_id, "changes": changes},
        output_summary={"user_id": user_id},
        actor=str(admin["user_id"]),
    )
    conn.commit()
    updated = conn.execute(
        "SELECT user_id, client_id, email, display_name, role, invite_status"
        " FROM users WHERE user_id = ?", (user_id,),
    ).fetchone()
    return dict(updated)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, conn: Conn, admin=Depends(current_user)) -> dict:
    """Regenerates credentials and returns the plaintext EXACTLY ONCE — the
    same handoff rule as creation. Old password stops working immediately."""
    user = _get_managed_user(conn, user_id)
    password = security.generate_password()
    conn.execute(
        "INSERT INTO auth_credentials (user_id, password_hash) VALUES (?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET password_hash = excluded.password_hash",
        (user_id, security.hash_password(password)),
    )
    # audited WITHOUT the password, same rule as create_user
    audit.log_action(
        conn, skill="admin_portal", action="reset_password",
        input_summary={"user_id": user_id},
        output_summary={"user_id": user_id},
        actor=str(admin["user_id"]),
    )
    conn.commit()
    return {
        "user_id": user_id,
        "email": user["email"],
        "password": password,
        "handoff_note": "Displayed once. Relay these credentials manually —"
                        " this system sends nothing.",
    }

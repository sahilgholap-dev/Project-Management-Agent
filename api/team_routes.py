"""Team members + stakeholders — plain CRUD (no business logic exists for
these rows). allocated_hrs is read-only display (NEW-OQ 3: a cache, never a
decision input) and is not writable through the API."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import Conn, User, require_role

router = APIRouter(tags=["team"])

CLIENT_WRITE = require_role("client_admin")
CLIENT_READ = require_role("client_admin", "member")


class MemberBody(BaseModel):
    name: str
    role: str
    skill_tags: list[str] = []
    capacity_hrs: float = 40


class MemberPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    skill_tags: list[str] | None = None
    capacity_hrs: float | None = None
    is_active: bool | None = None


class StakeholderBody(BaseModel):
    name: str
    audience_type: str
    email: str | None = None
    project_id: int | None = None  # null = client-wide


def _member(row) -> dict:
    d = dict(row)
    d["skill_tags"] = json.loads(d["skill_tags"])
    return d


@router.get("/team-members", dependencies=[CLIENT_READ])
def list_members(conn: Conn, user: User) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM team_members WHERE client_id = ? ORDER BY member_id",
        (user["client_id"],),
    ).fetchall()
    return [_member(r) for r in rows]


@router.post("/team-members", status_code=201, dependencies=[CLIENT_WRITE])
def create_member(body: MemberBody, conn: Conn, user: User) -> dict:
    if body.capacity_hrs <= 0:
        raise HTTPException(status_code=422, detail="capacity_hrs must be positive")
    cur = conn.execute(
        "INSERT INTO team_members (client_id, name, role, skill_tags, capacity_hrs)"
        " VALUES (?, ?, ?, ?, ?)",
        (user["client_id"], body.name, body.role, json.dumps(body.skill_tags),
         body.capacity_hrs),
    )
    conn.commit()
    return _member(conn.execute(
        "SELECT * FROM team_members WHERE member_id = ?", (cur.lastrowid,)
    ).fetchone())


@router.patch("/team-members/{member_id}", dependencies=[CLIENT_WRITE])
def patch_member(member_id: int, body: MemberPatch, conn: Conn) -> dict:
    row = conn.execute(
        "SELECT * FROM team_members WHERE member_id = ?", (member_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such member")
    updates, values = [], []
    for field in ("name", "role", "capacity_hrs"):
        value = getattr(body, field)
        if value is not None:
            updates.append(f"{field} = ?")
            values.append(value)
    if body.skill_tags is not None:
        updates.append("skill_tags = ?")
        values.append(json.dumps(body.skill_tags))
    if body.is_active is not None:
        updates.append("is_active = ?")
        values.append(1 if body.is_active else 0)
    if updates:
        conn.execute(
            f"UPDATE team_members SET {', '.join(updates)} WHERE member_id = ?",
            (*values, member_id),
        )
        conn.commit()
    return _member(conn.execute(
        "SELECT * FROM team_members WHERE member_id = ?", (member_id,)
    ).fetchone())


@router.get("/stakeholders", dependencies=[CLIENT_READ])
def list_stakeholders(conn: Conn, user: User) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM stakeholders WHERE client_id = ? ORDER BY stakeholder_id",
        (user["client_id"],),
    )]


@router.post("/stakeholders", status_code=201, dependencies=[CLIENT_WRITE])
def create_stakeholder(body: StakeholderBody, conn: Conn, user: User) -> dict:
    if body.audience_type not in ("team", "exec", "client", "investor"):
        raise HTTPException(status_code=422, detail="invalid audience_type")
    cur = conn.execute(
        "INSERT INTO stakeholders (client_id, project_id, name, email, audience_type)"
        " VALUES (?, ?, ?, ?, ?)",
        (user["client_id"], body.project_id, body.name, body.email, body.audience_type),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM stakeholders WHERE stakeholder_id = ?", (cur.lastrowid,)
    ).fetchone())


@router.delete("/stakeholders/{stakeholder_id}", dependencies=[CLIENT_WRITE])
def delete_stakeholder(stakeholder_id: int, conn: Conn) -> dict:
    conn.execute("DELETE FROM stakeholders WHERE stakeholder_id = ?", (stakeholder_id,))
    conn.commit()
    return {"ok": True}

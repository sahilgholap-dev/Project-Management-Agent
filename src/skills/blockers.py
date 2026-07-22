"""Blocker management actions (approved OQ-6): assigning a resolution owner
and resolving. Both record a real human actor in audit_log. These are actions
taken while reviewing an existing Tier 1 item (e.g. the 'blocker has no clear
resolution owner' clarification) — NOT new tiered decisions, so no review
item is raised here."""

from __future__ import annotations

import sqlite3

from src.lib import audit


def assign_blocker(
    conn: sqlite3.Connection, blocker_id: int, assigned_to: int, by_user: int
) -> dict:
    blocker = conn.execute(
        "SELECT project_id, assigned_to FROM blockers WHERE blocker_id = ?",
        (blocker_id,),
    ).fetchone()
    if blocker is None:
        raise ValueError(f"blocker {blocker_id} does not exist")
    member = conn.execute(
        "SELECT is_active FROM team_members WHERE member_id = ?", (assigned_to,)
    ).fetchone()
    if member is None or not member["is_active"]:
        raise ValueError(f"member {assigned_to} does not exist or is inactive")

    conn.execute(
        "UPDATE blockers SET assigned_to = ? WHERE blocker_id = ?",
        (assigned_to, blocker_id),
    )
    audit.log_action(
        conn, skill="blockers", action="assign_blocker",
        input_summary={"blocker_id": blocker_id,
                       "from": blocker["assigned_to"], "to": assigned_to},
        actor=str(by_user),
        project_id=blocker["project_id"],
    )
    conn.commit()
    return {"blocker_id": blocker_id, "assigned_to": assigned_to}


def resolve_blocker(conn: sqlite3.Connection, blocker_id: int, by_user: int) -> dict:
    blocker = conn.execute(
        "SELECT project_id, status FROM blockers WHERE blocker_id = ?", (blocker_id,)
    ).fetchone()
    if blocker is None:
        raise ValueError(f"blocker {blocker_id} does not exist")
    if blocker["status"] == "resolved":
        raise ValueError(f"blocker {blocker_id} is already resolved")

    conn.execute(
        "UPDATE blockers SET status = 'resolved', resolved_at = datetime('now')"
        " WHERE blocker_id = ?",
        (blocker_id,),
    )
    audit.log_action(
        conn, skill="blockers", action="resolve_blocker",
        input_summary={"blocker_id": blocker_id},
        actor=str(by_user),
        project_id=blocker["project_id"],
    )
    conn.commit()
    return {"blocker_id": blocker_id, "status": "resolved"}

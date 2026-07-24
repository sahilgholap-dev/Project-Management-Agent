"""The member ("My Work") portal read model.

Members live entirely in /my (decision 2026-07-23): their API surface is
auth, GET /me/work, and POST /status-reports (self-only). Everything here is
scoped through the users -> team_members link (team_members.user_id): no
link, no data — the UI shows an ask-your-admin empty state instead of
guessing which roster row a login belongs to.

Task updates are NOT written here. The member portal's "mark done" goes
through POST /status-reports like every other status signal, so parsing,
ambiguity flagging, hours capture, and EVM integrity all still apply.
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from api.deps import Conn, User, require_role

router = APIRouter(tags=["me"])

ANY_CLIENT_USER = require_role("client_admin", "member")


@router.get("/me/work", dependencies=[ANY_CLIENT_USER])
def my_work(conn: Conn, user: User) -> dict:
    member = conn.execute(
        "SELECT * FROM team_members WHERE user_id = ? AND client_id = ?",
        (user["user_id"], user["client_id"]),
    ).fetchone()
    if member is None:
        return {"linked": False, "member": None, "projects": [],
                "blockers": [], "pending_task_ids": []}
    member_id = member["member_id"]

    projects = []
    for p in conn.execute(
        "SELECT DISTINCT p.project_id, p.name, p.status, p.timeline_start,"
        " p.timeline_end FROM projects p JOIN tasks t ON t.project_id = p.project_id"
        " WHERE t.owner_id = ? AND p.status != 'archived' ORDER BY p.project_id",
        (member_id,),
    ):
        phases = [dict(r) for r in conn.execute(
            "SELECT * FROM phases WHERE project_id = ? ORDER BY sequence_order",
            (p["project_id"],),
        )]
        tasks = []
        for t in conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND owner_id = ?"
            " ORDER BY planned_start IS NULL, planned_start, task_id",
            (p["project_id"], member_id),
        ):
            d = dict(t)
            d["skill_tags"] = json.loads(d["skill_tags"])
            d["owner_name"] = member["name"]  # all mine; matches the Task shape
            tasks.append(d)
        projects.append({**dict(p), "phases": phases, "tasks": tasks})

    blockers = [dict(r) for r in conn.execute(
        "SELECT b.*, p.name AS project_name FROM blockers b"
        " JOIN projects p ON p.project_id = b.project_id"
        " WHERE b.status = 'open' AND p.status != 'archived'"
        "   AND (b.assigned_to = ? OR b.blocked_member_id = ?)"
        " ORDER BY b.blocker_id",
        (member_id, member_id),
    )]

    # reports submitted but not yet parsed by a monitoring cycle — the UI
    # shows these tasks as "update pending processing"
    pending = [r["task_id"] for r in conn.execute(
        "SELECT DISTINCT task_id FROM status_reports"
        " WHERE member_id = ? AND processed_at IS NULL",
        (member_id,),
    )]

    member_out = dict(member)
    member_out["skill_tags"] = json.loads(member_out["skill_tags"])
    return {"linked": True, "member": member_out, "projects": projects,
            "blockers": blockers, "pending_task_ids": pending}

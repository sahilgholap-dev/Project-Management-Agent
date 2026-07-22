"""Status-report inbox, risk register, blockers, logs, artifacts — reads plus
the two approved OQ-6 actions (audited src/ functions, never raw updates)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import Conn, User, require_role
from api.errors import backend_errors
from src.skills import blockers as blockers_skill
from src.skills import risk_tracking

router = APIRouter(tags=["registers"])

CLIENT_WRITE = require_role("client_admin")
CLIENT_READ = require_role("client_admin", "member")
MEMBER_SUBMIT = require_role("client_admin", "member")


class StatusReportBody(BaseModel):
    task_id: int
    member_id: int
    raw_text: str


class ScoreBody(BaseModel):
    severity: int
    likelihood: int


class BlockerPatch(BaseModel):
    assigned_to: int | None = None
    resolve: bool = False


@router.post("/status-reports", status_code=201, dependencies=[MEMBER_SUBMIT])
def submit_status_report(body: StatusReportBody, conn: Conn) -> dict:
    """The confirmed-Q7 manual inbox: the row is parsed by Status Tracking on
    the next monitoring cycle, not here."""
    if conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (body.task_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="no such task")
    if conn.execute(
        "SELECT 1 FROM team_members WHERE member_id = ?", (body.member_id,)
    ).fetchone() is None:
        raise HTTPException(status_code=404, detail="no such member")
    cur = conn.execute(
        "INSERT INTO status_reports (task_id, member_id, raw_text) VALUES (?, ?, ?)",
        (body.task_id, body.member_id, body.raw_text),
    )
    conn.commit()
    return {"report_id": cur.lastrowid, "queued": True}


@router.get("/projects/{project_id}/status-reports", dependencies=[CLIENT_READ])
def list_status_reports(project_id: int, conn: Conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT r.*, t.title AS task_title FROM status_reports r"
        " JOIN tasks t ON t.task_id = r.task_id"
        " WHERE t.project_id = ? ORDER BY r.report_id DESC",
        (project_id,),
    )]


@router.get("/projects/{project_id}/risks", dependencies=[CLIENT_READ])
def list_risks(project_id: int, conn: Conn, status: str | None = None) -> list[dict]:
    where = "AND status = ?" if status else ""
    values = (project_id, status) if status else (project_id,)
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM risks_issues WHERE project_id = ? {where}"
        " ORDER BY score DESC, risk_id DESC",
        values,
    )]


@router.patch("/risks/{risk_id}/score", dependencies=[CLIENT_WRITE])
def adjust_risk_score(risk_id: int, body: ScoreBody, conn: Conn, user: User) -> dict:
    """Wraps risk_tracking.adjust_score (OQ-6: audited, human actor)."""
    with backend_errors():
        return risk_tracking.adjust_score(
            conn, risk_id, body.severity, body.likelihood, by_user=user["user_id"]
        )


@router.get("/projects/{project_id}/blockers", dependencies=[CLIENT_READ])
def list_blockers(project_id: int, conn: Conn) -> list[dict]:
    """Unowned blockers (assigned_to NULL) sort first — the UI surfaces them."""
    return [dict(r) for r in conn.execute(
        "SELECT b.*, raiser.name AS raised_by_name, assignee.name AS assigned_to_name,"
        "       blocked.name AS blocked_member_name"
        " FROM blockers b"
        " LEFT JOIN team_members raiser ON raiser.member_id = b.raised_by"
        " LEFT JOIN team_members assignee ON assignee.member_id = b.assigned_to"
        " LEFT JOIN team_members blocked ON blocked.member_id = b.blocked_member_id"
        " WHERE b.project_id = ?"
        " ORDER BY (b.assigned_to IS NOT NULL), b.status, b.blocker_id DESC",
        (project_id,),
    )]


@router.patch("/blockers/{blocker_id}", dependencies=[CLIENT_WRITE])
def patch_blocker(blocker_id: int, body: BlockerPatch, conn: Conn, user: User) -> dict:
    """Wraps blockers.assign_blocker / resolve_blocker (OQ-6: audited)."""
    result: dict = {}
    with backend_errors():
        if body.assigned_to is not None:
            result = blockers_skill.assign_blocker(
                conn, blocker_id, body.assigned_to, by_user=user["user_id"]
            )
        if body.resolve:
            result = blockers_skill.resolve_blocker(
                conn, blocker_id, by_user=user["user_id"]
            )
    if not result:
        raise HTTPException(status_code=422, detail="nothing to do")
    return result


@router.get("/projects/{project_id}/escalation-log", dependencies=[CLIENT_READ])
def escalation_log(project_id: int, conn: Conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT e.* FROM escalation_log e"
        " JOIN review_queue q ON q.item_id = e.item_id"
        " WHERE q.project_id = ? ORDER BY e.escalation_id DESC",
        (project_id,),
    )]


@router.get("/projects/{project_id}/audit-log", dependencies=[CLIENT_READ])
def audit_log(project_id: int, conn: Conn, limit: int = 200) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM audit_log WHERE project_id = ? ORDER BY audit_id DESC LIMIT ?",
        (project_id, min(limit, 1000)),
    )]


@router.get("/projects/{project_id}/artifacts", dependencies=[CLIENT_READ])
def artifacts(project_id: int, conn: Conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM artifact_versions WHERE project_id = ?"
        " ORDER BY version_id DESC",
        (project_id,),
    )]

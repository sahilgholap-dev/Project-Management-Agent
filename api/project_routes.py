"""Projects, the plan view, orchestrator triggers, meetings, and the Tier 3
forms — every verb names the src/ function it wraps (thin-wrapper rule)."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import Conn, User, require_role
from api.errors import backend_errors
from api.sonnet_dep import get_sonnet
from src import config_loader
from src.governance import escalation, forms
from src.orchestrator import graph, lifecycle
from src.skills import meeting_summary

router = APIRouter(tags=["projects"])

CLIENT_WRITE = require_role("client_admin")
CLIENT_READ = require_role("client_admin", "member")
MEMBER_SUBMIT = require_role("client_admin", "member")


class ProjectBody(BaseModel):
    name: str
    scope_document: str | None = None
    scope_summary: str | None = None
    budget_total: float | None = None
    timeline_start: str | None = None
    timeline_end: str | None = None
    config_overrides: dict | None = None


class CycleBody(BaseModel):
    as_of: date  # OQ-4 (approved): explicit simulation date
    draft_comms: bool | None = None  # None = cadence gate; True = ad hoc request


class CloseBody(BaseModel):
    as_of: date


class MeetingBody(BaseModel):
    raw_text: str
    meeting_date: str | None = None


class ChangeRequestBody(BaseModel):
    title: str
    description: str


class SignoffBody(BaseModel):
    title: str
    content: str


@router.get("/projects", dependencies=[CLIENT_READ])
def list_projects(conn: Conn, user: User) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT project_id, name, status, paused_reason, timeline_start,"
        " timeline_end, budget_total FROM projects WHERE client_id = ?"
        " ORDER BY project_id",
        (user["client_id"],),
    )]


@router.post("/projects", status_code=201, dependencies=[CLIENT_WRITE])
def create_project(body: ProjectBody, conn: Conn, user: User) -> dict:
    cur = conn.execute(
        "INSERT INTO projects (client_id, name, scope_document, scope_summary,"
        " budget_total, timeline_start, timeline_end)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user["client_id"], body.name, body.scope_document, body.scope_summary,
         body.budget_total, body.timeline_start, body.timeline_end),
    )
    project_id = cur.lastrowid
    conn.commit()
    if body.config_overrides:
        with backend_errors():
            config_loader.save_project_overrides(conn, project_id, body.config_overrides)
    return {"project_id": project_id}


@router.get("/projects/{project_id}", dependencies=[CLIENT_READ])
def project_detail(project_id: int, conn: Conn) -> dict:
    project = conn.execute(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    ).fetchone()
    if project is None:
        raise HTTPException(status_code=404, detail="no such project")
    phases = [dict(p) for p in conn.execute(
        "SELECT * FROM phases WHERE project_id = ? ORDER BY sequence_order",
        (project_id,),
    )]
    tasks = []
    for t in conn.execute(
        "SELECT t.*, m.name AS owner_name FROM tasks t"
        " LEFT JOIN team_members m ON m.member_id = t.owner_id"
        " WHERE t.project_id = ? ORDER BY t.planned_start IS NULL,"
        " t.planned_start, t.task_id",
        (project_id,),
    ):
        d = dict(t)
        d["skill_tags"] = json.loads(d["skill_tags"])
        tasks.append(d)
    dependencies = [dict(d) for d in conn.execute(
        "SELECT d.* FROM task_dependencies d"
        " JOIN tasks t ON t.task_id = d.predecessor_task_id WHERE t.project_id = ?",
        (project_id,),
    )]
    detail = dict(project)
    detail["config_overrides"] = json.loads(detail["config_overrides"] or "{}")
    detail.update(phases=phases, tasks=tasks, dependencies=dependencies)
    return detail


@router.post("/projects/{project_id}/onboard", dependencies=[CLIENT_WRITE])
def onboard(project_id: int, body: CloseBody, conn: Conn,
            sonnet=Depends(get_sonnet)) -> dict:
    """Wraps orchestrator.graph.onboard_project (breakdown -> schedule ->
    assign). A halted breakdown returns halted=true — surfaced, not hidden."""
    with backend_errors():
        state = graph.onboard_project(conn, project_id, body.as_of, sonnet)
    return {"halted": state.get("halted", False), "results": state.get("results", {})}


@router.post("/projects/{project_id}/cycle", dependencies=[CLIENT_WRITE])
def cycle(project_id: int, body: CycleBody, conn: Conn,
          sonnet=Depends(get_sonnet)) -> dict:
    """Wraps orchestrator.graph.run_monitoring_cycle."""
    with backend_errors():
        state = graph.run_monitoring_cycle(
            conn, project_id, body.as_of, draft_comms=body.draft_comms, sonnet=sonnet
        )
    return {"paused": state.get("paused", False), "results": state.get("results", {})}


@router.post("/projects/{project_id}/close", dependencies=[CLIENT_WRITE])
def close(project_id: int, body: CloseBody, conn: Conn,
          sonnet=Depends(get_sonnet)) -> dict:
    """Wraps lifecycle.generate_retrospective (Tier 2 review item)."""
    with backend_errors():
        item_id = lifecycle.generate_retrospective(conn, project_id, body.as_of, sonnet)
    return {"review_item_id": item_id}


@router.post("/projects/{project_id}/archive", dependencies=[CLIENT_WRITE])
def archive(project_id: int, conn: Conn) -> dict:
    """Wraps lifecycle.archive_project — refused (409) until the retrospective
    is explicitly approved; the UI surfaces the refusal, never works around it."""
    if not lifecycle.archive_project(conn, project_id):
        raise HTTPException(
            status_code=409,
            detail="archive refused: the retrospective has not been approved",
        )
    return {"status": "archived"}


@router.post("/projects/{project_id}/resume", dependencies=[CLIENT_WRITE])
def resume(project_id: int, conn: Conn, user: User) -> dict:
    """Wraps escalation.resume_project — refused while paused items remain."""
    if not escalation.resume_project(conn, project_id, by_user=user["user_id"]):
        raise HTTPException(
            status_code=409,
            detail="resume refused: unresolved paused review items remain",
        )
    return {"status": "active"}


@router.post("/projects/{project_id}/meetings", status_code=201,
             dependencies=[MEMBER_SUBMIT])
def upload_meeting(project_id: int, body: MeetingBody, conn: Conn, user: User,
                   sonnet=Depends(get_sonnet)) -> dict:
    """Wraps skills.meeting_summary.run (three-bucket extraction)."""
    with backend_errors():
        result = meeting_summary.run(
            conn, project_id, body.raw_text, uploaded_by=user["user_id"],
            meeting_date=body.meeting_date, sonnet=sonnet,
        )
    return result


@router.get("/projects/{project_id}/meetings", dependencies=[CLIENT_READ])
def list_meetings(project_id: int, conn: Conn) -> list[dict]:
    rows = conn.execute(
        "SELECT meeting_id, meeting_date, decisions, uploaded_by, created_at"
        " FROM meetings WHERE project_id = ? ORDER BY meeting_id DESC",
        (project_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["decisions"] = json.loads(d["decisions"])
        out.append(d)
    return out


@router.post("/projects/{project_id}/change-requests", status_code=201,
             dependencies=[CLIENT_WRITE])
def create_change_request(project_id: int, body: ChangeRequestBody, conn: Conn,
                          user: User) -> dict:
    """Wraps governance.forms.create_change_request (Tier 3 gate)."""
    with backend_errors():
        return forms.create_change_request(
            conn, project_id, body.title, body.description,
            requested_by=user["user_id"],
        )


@router.post("/projects/{project_id}/signoff-packets", status_code=201,
             dependencies=[CLIENT_WRITE])
def create_signoff_packet(project_id: int, body: SignoffBody, conn: Conn,
                          user: User) -> dict:
    """Wraps governance.forms.create_signoff_packet (Tier 3 gate)."""
    with backend_errors():
        return forms.create_signoff_packet(
            conn, project_id, body.title, body.content,
            requested_by=user["user_id"],
        )

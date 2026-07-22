"""Project close path (PRD section 11): when the project closes, a
retrospective is generated (Sonnet 5, Tier 2 reviewed — confirmed Q18) and
the project is archived only after that retrospective is explicitly approved.
Approval itself versions the final text in artifact_versions (resolve_item)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit, evm
from src.lib.calendar import WorkingCalendar
from src.llm.sonnet_client import SonnetClient

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"


def generate_retrospective(
    conn: sqlite3.Connection, project_id: int, today: date,
    sonnet: SonnetClient | None = None,
) -> int:
    """Draft the closing retrospective and queue it at Tier 2. Returns the
    review item id."""
    sonnet = sonnet or SonnetClient()
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))
    snap = evm.snapshot(conn, project_id, today, calendar)

    project = conn.execute(
        "SELECT name, timeline_start, timeline_end FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    phases = [
        dict(r) for r in conn.execute(
            "SELECT name, planned_start, planned_end, status FROM phases"
            " WHERE project_id = ? ORDER BY sequence_order",
            (project_id,),
        )
    ]
    task_stats = conn.execute(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done,"
        " SUM(CASE WHEN actual_end > planned_end THEN 1 ELSE 0 END) AS slipped"
        " FROM tasks WHERE project_id = ? AND status != 'cancelled'",
        (project_id,),
    ).fetchone()
    risks = [
        dict(r) for r in conn.execute(
            "SELECT title, kind, severity, likelihood, status, source"
            " FROM risks_issues WHERE project_id = ? ORDER BY score DESC",
            (project_id,),
        )
    ]
    data = {
        "project": dict(project),
        "as_of": today.isoformat(),
        "phases": phases,
        "tasks": dict(task_stats),
        "final_evm": {
            "planned_value_hours": snap.planned_value,
            "earned_value_hours": snap.earned_value,
            "actual_cost_hours": snap.actual_cost,
            "schedule_variance_hours": round(snap.schedule_variance, 2),
            "cost_variance_hours": round(snap.cost_variance, 2),
            "cost_data_complete": snap.cost_data_complete,
        },
        "risk_register": risks,
    }

    system = (_PROMPTS / "retrospective.md").read_text(encoding="utf-8")
    draft = sonnet.text(system, json.dumps(data, indent=2)).strip()
    item_id = raise_review_item(
        conn, project_id, "retrospective",
        {"draft": draft, "data_basis": data},
        created_by_skill="orchestrator",
    )
    conn.execute(
        "UPDATE projects SET status = 'closed' WHERE project_id = ? AND status = 'active'",
        (project_id,),
    )
    audit.log_action(
        conn, skill="orchestrator", action="generate_retrospective",
        input_summary={"as_of": today.isoformat()},
        output_summary={"item_id": item_id},
        project_id=project_id,
    )
    conn.commit()
    return item_id


def archive_project(conn: sqlite3.Connection, project_id: int) -> bool:
    """Archive only after the retrospective's Tier 2 item is explicitly
    approved (PRD section 11 / no-auto-approval). Returns False otherwise."""
    approved = conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue"
        " WHERE project_id = ? AND item_type = 'retrospective' AND status = 'approved'",
        (project_id,),
    ).fetchone()["n"]
    if not approved:
        return False
    conn.execute(
        "UPDATE projects SET status = 'archived' WHERE project_id = ?", (project_id,)
    )
    audit.log_action(
        conn, skill="orchestrator", action="archive_project", project_id=project_id,
    )
    conn.commit()
    return True

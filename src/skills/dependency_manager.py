"""Skill 8.6 — Dependency Manager. Deterministic graph re-walk, plain code.
NO LLM in the computation (the plain-language summary of the diff is a Phase 2
bolt-on; the dates are decided here, never by a model).

Trigger: a task's actual_end recorded later than its planned_end. Walks the
dependency graph forward, re-runs the Scheduler's passes restricted to the
affected tasks (with the slipped task's finish pinned to its actual_end),
diffs the dates, and raises a Tier 1 slip_impact item if a phase or project
end date moved by more than slip_threshold_days (PRD 8.6 step 6).
"""

from __future__ import annotations

import sqlite3
from datetime import date

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit
from src.lib.calendar import WorkingCalendar
from src.lib.task_graph import TaskGraph


class SlipError(Exception):
    pass


def handle_slip(conn: sqlite3.Connection, task_id: int) -> dict:
    """Process a detected slip on task_id. Returns a summary dict with the
    per-task date diffs and whether a threshold breach was raised."""
    # local import: scheduler and dependency manager share the CPM engine
    from src.skills import scheduler as sched

    task = conn.execute(
        "SELECT task_id, project_id, planned_end, actual_end, title FROM tasks"
        " WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if task is None:
        raise SlipError(f"task {task_id} does not exist")
    if not task["actual_end"] or not task["planned_end"]:
        raise SlipError(f"task {task_id} has no recorded actual_end/planned_end")

    planned_end = date.fromisoformat(task["planned_end"])
    actual_end = date.fromisoformat(task["actual_end"])
    calendar = WorkingCalendar(
        config_loader.resolve(conn, task["project_id"], "working_calendar")
    )
    slip_days = max(0, calendar.count_working_days(planned_end, actual_end) - 1)
    if slip_days == 0:
        return {"slip_days": 0, "affected": {}, "breach_raised": False}

    project_id = task["project_id"]
    graph = TaskGraph.for_project(conn, project_id)
    affected = graph.descendants(task_id)
    if not affected:
        audit.log_action(
            conn, skill="dependency_manager", action="handle_slip",
            input_summary={"task_id": task_id, "slip_days": slip_days},
            output_summary={"affected": 0}, project_id=project_id,
        )
        conn.commit()
        return {"slip_days": slip_days, "affected": {}, "breach_raised": False}

    old_dates = {
        r["task_id"]: (r["planned_start"], r["planned_end"])
        for r in conn.execute(
            f"SELECT task_id, planned_start, planned_end FROM tasks"
            f" WHERE task_id IN ({','.join('?' * len(affected))})",
            tuple(affected),
        )
    }
    old_project_finish = _project_finish(conn, project_id)
    old_phase_finishes = _phase_finishes(conn, project_id)

    # Re-run CPM restricted to the affected tasks, slipped finish pinned.
    new_dates = sched.schedule_project(
        conn,
        project_id,
        restrict_to=affected,
        fixed_ef_dates={task_id: actual_end},
    )

    diffs = {}
    for t in affected:
        old_end = old_dates.get(t, (None, None))[1]
        new_end = new_dates[t]["planned_end"].isoformat()
        if old_end != new_end:
            diffs[t] = {"old_end": old_end, "new_end": new_end}

    new_project_finish = _project_finish(conn, project_id)
    end_shift_days = 0
    if old_project_finish and new_project_finish > old_project_finish:
        end_shift_days = (
            calendar.count_working_days(old_project_finish, new_project_finish) - 1
        )

    # PRD 8.6 step 5: diff against PHASE end dates too, not just the project's
    # — a slip can blow a phase milestone even when later slack absorbs it at
    # project level.
    phase_end_shifts = {}
    for phase_id, new_finish in _phase_finishes(conn, project_id).items():
        old_finish = old_phase_finishes.get(phase_id)
        if old_finish and new_finish > old_finish:
            phase_end_shifts[phase_id] = (
                calendar.count_working_days(old_finish, new_finish) - 1
            )

    threshold = float(config_loader.resolve(conn, project_id, "slip_threshold_days"))
    breach = end_shift_days > threshold or any(
        shift > threshold for shift in phase_end_shifts.values()
    )
    if breach:
        raise_review_item(
            conn, project_id, "slip_impact",
            {
                "slipped_task_id": task_id,
                "slipped_task_title": task["title"],
                "slip_days": slip_days,
                "project_end_shift_days": end_shift_days,
                "phase_end_shift_days": phase_end_shifts,
                "threshold_days": threshold,
                "downstream_diffs": diffs,
            },
            created_by_skill="dependency_manager",
        )

    audit.log_action(
        conn, skill="dependency_manager", action="handle_slip",
        input_summary={"task_id": task_id, "slip_days": slip_days},
        output_summary={
            "affected": len(affected),
            "project_end_shift_days": end_shift_days,
            "breach_raised": breach,
        },
        project_id=project_id,
    )
    conn.commit()
    return {"slip_days": slip_days, "affected": diffs, "breach_raised": breach}


def detect_and_handle_slips(conn: sqlite3.Connection, project_id: int) -> list[dict]:
    """Trigger scan (PRD 8.6): every task whose actual_end is later than its
    planned_end."""
    slipped = conn.execute(
        "SELECT task_id FROM tasks WHERE project_id = ?"
        " AND actual_end IS NOT NULL AND planned_end IS NOT NULL"
        " AND actual_end > planned_end",
        (project_id,),
    ).fetchall()
    return [handle_slip(conn, r["task_id"]) for r in slipped]


def _phase_finishes(conn: sqlite3.Connection, project_id: int) -> dict[int, date]:
    """Latest planned task end per phase — the phase's effective milestone."""
    return {
        r["phase_id"]: date.fromisoformat(r["finish"])
        for r in conn.execute(
            "SELECT phase_id, MAX(planned_end) AS finish FROM tasks"
            " WHERE project_id = ? AND status != 'cancelled'"
            "   AND planned_end IS NOT NULL GROUP BY phase_id",
            (project_id,),
        )
    }


def _project_finish(conn: sqlite3.Connection, project_id: int) -> date | None:
    row = conn.execute(
        "SELECT MAX(planned_end) AS finish FROM tasks"
        " WHERE project_id = ? AND status != 'cancelled'",
        (project_id,),
    ).fetchone()
    return date.fromisoformat(row["finish"]) if row and row["finish"] else None

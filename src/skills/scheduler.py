"""Skill 8.2 — Scheduler. Deterministic Critical Path Method, plain code.

NO LLM: this module must never import from src/llm (enforced by
tests/test_import_guardrail.py). The same algorithm runs for every project —
only data changes (PRD section 3).

All arithmetic is in working-day indexes on an axis of the client's working
calendar. Durations: ceil(effort_hours / hours_per_day), minimum 1 day.
Planned dates written back are the early schedule (ES/EF). Slack is
latest_start - earliest_start in working days; zero (or negative) slack means
critical path. If the computed finish exceeds the project timeline, a Tier 1
infeasible_plan item is raised rather than silently accepting the plan
(PRD 8.2 step 9) — dates are still written so the reviewer sees the real plan.
"""

from __future__ import annotations

import math
import sqlite3
from bisect import bisect_right
from datetime import date, timedelta

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit
from src.lib.calendar import WorkingCalendar
from src.lib.task_graph import TaskGraph

# Horizon padding past the project timeline so late schedules still index.
_AXIS_PAD_DAYS = 400


class SchedulerError(Exception):
    pass


def _build_axis(calendar: WorkingCalendar, start: date, end: date) -> list[date]:
    return calendar.working_days_between(start, end + timedelta(days=_AXIS_PAD_DAYS))


def _idx_at_or_before(axis: list[date], day: date) -> int:
    """Index of the last working day <= day (for anchoring actual dates that
    may fall on non-working days)."""
    pos = bisect_right(axis, day) - 1
    if pos < 0:
        raise SchedulerError(f"date {day} precedes the scheduling axis")
    return pos


def _idx_at_or_after(axis: list[date], day: date) -> int:
    pos = bisect_right(axis, day - timedelta(days=1))
    if pos >= len(axis):
        raise SchedulerError(f"date {day} beyond the scheduling axis")
    return pos


def compute_cpm(
    durations: dict[int, int],
    graph: TaskGraph,
    es_floor: dict[int, int],
    lf_cap: dict[int, int],
    fixed_ef: dict[int, int] | None = None,
    restrict_to: set[int] | None = None,
) -> dict[int, dict]:
    """Pure CPM over working-day indexes.

    durations: task -> working days (>=1). es_floor/lf_cap: per-task index
    bounds (phase window intersected with project window). fixed_ef: tasks
    whose finish is pinned (completed tasks during a slip re-run) — they are
    not recomputed and act only as constraints. restrict_to: if given, only
    these tasks get results (a slip re-run restricted to affected tasks).
    """
    fixed_ef = fixed_ef or {}
    order = graph.topological_order()

    es: dict[int, int] = {}
    ef: dict[int, int] = {}
    for t in order:
        if t in fixed_ef:
            ef[t] = fixed_ef[t]
            es[t] = fixed_ef[t] - durations[t] + 1
            continue
        earliest = es_floor.get(t, 0)
        for pred in graph.predecessors[t]:
            earliest = max(earliest, ef[pred] + 1)
        es[t] = earliest
        ef[t] = earliest + durations[t] - 1

    ls: dict[int, int] = {}
    lf: dict[int, int] = {}
    for t in reversed(order):
        latest = lf_cap.get(t, max(ef.values()))
        for succ in graph.successors[t]:
            latest = min(latest, ls[succ] - 1)
        lf[t] = latest
        ls[t] = latest - durations[t] + 1

    results = {}
    scope = restrict_to if restrict_to is not None else set(order)
    for t in scope:
        if t in fixed_ef:
            continue
        slack = ls[t] - es[t]
        results[t] = {
            "es": es[t],
            "ef": ef[t],
            "slack_days": slack,
            "on_critical_path": slack <= 0,
        }
    return results


def _load_inputs(conn: sqlite3.Connection, project_id: int):
    project = conn.execute(
        "SELECT timeline_start, timeline_end FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if project is None:
        raise SchedulerError(f"project {project_id} does not exist")
    if not project["timeline_start"] or not project["timeline_end"]:
        raise SchedulerError(f"project {project_id} has no timeline to schedule against")
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))
    tasks = {
        r["task_id"]: r
        for r in conn.execute(
            "SELECT t.task_id, t.effort_hours, t.phase_id, t.status, t.actual_end,"
            "       p.planned_start AS phase_start, p.planned_end AS phase_end"
            " FROM tasks t JOIN phases p ON p.phase_id = t.phase_id"
            " WHERE t.project_id = ? AND t.status != 'cancelled'"
            "   AND t.effort_hours IS NOT NULL",
            (project_id,),
        )
    }
    return project, calendar, tasks


def _flag_unestimated_tasks(conn: sqlite3.Connection, project_id: int) -> int:
    """A NULL effort estimate gets the NEW-OQ 4 treatment: the task cannot
    enter CPM, so it is excluded, flagged, and raised as a Tier 1 item —
    never scheduled on a guessed number. Idempotent: only unflagged tasks
    raise a new item."""
    rows = conn.execute(
        "SELECT task_id, title FROM tasks"
        " WHERE project_id = ? AND status != 'cancelled'"
        "   AND effort_hours IS NULL AND needs_clarification IS NULL",
        (project_id,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE tasks SET needs_clarification ="
            " 'no effort estimate; excluded from scheduling until estimated'"
            " WHERE task_id = ?",
            (row["task_id"],),
        )
        raise_review_item(
            conn, project_id, "clarification",
            {"task_id": row["task_id"], "title": row["title"],
             "reason": "task has no effort estimate; excluded from CPM until"
                       " a reviewer supplies one"},
            created_by_skill="scheduler",
        )
    return len(rows)


def schedule_project(
    conn: sqlite3.Connection,
    project_id: int,
    restrict_to: set[int] | None = None,
    fixed_ef_dates: dict[int, date] | None = None,
) -> dict[int, dict]:
    """Run CPM for a project and write planned_start/planned_end, slack_days,
    on_critical_path. Returns {task_id: {planned_start, planned_end, slack_days,
    on_critical_path}} for the scheduled scope."""
    project, calendar, tasks = _load_inputs(conn, project_id)
    _flag_unestimated_tasks(conn, project_id)
    if not tasks:
        conn.commit()
        return {}

    start = date.fromisoformat(project["timeline_start"])
    end = date.fromisoformat(project["timeline_end"])
    axis = _build_axis(calendar, start, end)
    project_end_idx = _idx_at_or_before(axis, end)

    graph = TaskGraph.for_project(conn, project_id)
    durations, es_floor, lf_cap = {}, {}, {}
    for t, row in tasks.items():
        durations[t] = max(1, math.ceil(row["effort_hours"] / calendar.hours_per_day))
        phase_start = date.fromisoformat(row["phase_start"])
        phase_end = date.fromisoformat(row["phase_end"])
        es_floor[t] = max(0, _idx_at_or_after(axis, max(phase_start, start)))
        lf_cap[t] = min(project_end_idx, _idx_at_or_before(axis, phase_end))

    fixed_ef = {
        t: _idx_at_or_before(axis, d) for t, d in (fixed_ef_dates or {}).items()
    }

    cpm = compute_cpm(durations, graph, es_floor, lf_cap, fixed_ef, restrict_to)

    results = {}
    for t, r in cpm.items():
        planned_start, planned_end = axis[r["es"]], axis[r["ef"]]
        conn.execute(
            "UPDATE tasks SET planned_start = ?, planned_end = ?, slack_days = ?,"
            " on_critical_path = ? WHERE task_id = ?",
            (
                planned_start.isoformat(),
                planned_end.isoformat(),
                r["slack_days"],
                1 if r["on_critical_path"] else 0,
                t,
            ),
        )
        results[t] = {
            "planned_start": planned_start,
            "planned_end": planned_end,
            "slack_days": r["slack_days"],
            "on_critical_path": r["on_critical_path"],
        }

    project_finish_idx = max(r["ef"] for r in cpm.values()) if cpm else 0
    infeasible = project_finish_idx > project_end_idx
    if infeasible:
        raise_review_item(
            conn,
            project_id,
            "infeasible_plan",
            {
                "computed_finish": axis[project_finish_idx].isoformat(),
                "timeline_end": end.isoformat(),
                "overrun_working_days": project_finish_idx - project_end_idx,
            },
            created_by_skill="scheduler",
        )

    audit.log_action(
        conn,
        skill="scheduler",
        action="schedule_project",
        input_summary={"task_count": len(cpm), "restricted": restrict_to is not None},
        output_summary={
            "computed_finish": axis[project_finish_idx].isoformat() if cpm else None,
            "infeasible": infeasible,
        },
        project_id=project_id,
    )
    conn.commit()
    return results

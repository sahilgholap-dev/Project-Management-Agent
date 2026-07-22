"""Skill 8.3 — Assignment Engine. Deterministic greedy skills-and-capacity
match, plain code. NO LLM (guardrail-tested).

Capacity is time-phased and cross-project by design (PRD section 9): a member
qualifies for a task only if, in EVERY ISO week the task's planned window
touches, their existing concurrent load across all active projects plus the
task's prorated contribution stays within that week's effective capacity
(lib/allocation.py is the single authority for that math).

Never over-allocates: no qualifying candidate -> the task is flagged
unassignable and a Tier 1 review item is raised (PRD 8.3 step 5). A task with
no planned window is refused and flagged (confirmed NEW-OQ 4), never assigned.

Deterministic ordering and tie-breaks (documented so the known-answer fixture
is reproducible):
- Tasks: critical-path first, then earliest planned_start, then task_id.
- best_skill_match: higher skill-overlap count wins; tie -> lower peak weekly
  load over the task window; tie -> lower member_id.
- balanced_workload: lower peak weekly load wins; tie -> higher overlap;
  tie -> lower member_id.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import allocation, audit
from src.lib.calendar import WorkingCalendar


def _tasks_needing_assignment(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT task_id, title, effort_hours, skill_tags, planned_start, planned_end,"
        "       on_critical_path"
        " FROM tasks"
        " WHERE project_id = ? AND owner_id IS NULL"
        "   AND status NOT IN ('done','cancelled')"
        " ORDER BY on_critical_path DESC, planned_start ASC, task_id ASC",
        (project_id,),
    ).fetchall()


def _candidates(conn: sqlite3.Connection, task_skills: set[str]) -> list[sqlite3.Row]:
    members = conn.execute(
        "SELECT member_id, name, skill_tags, capacity_hrs FROM team_members"
        " WHERE is_active = 1 ORDER BY member_id"
    ).fetchall()
    out = []
    for m in members:
        overlap = task_skills & set(json.loads(m["skill_tags"]))
        if overlap:
            out.append((m, len(overlap)))
    return out


def _peak_load_over_window(
    conn: sqlite3.Connection,
    member_id: int,
    calendar: WorkingCalendar,
    start: date,
    end: date,
) -> float:
    load = allocation.member_weekly_load(conn, member_id, calendar)
    weeks = allocation.weeks_of_window(start, end)
    return max((load.get(w, 0.0) for w in weeks), default=0.0)


def assign_tasks(
    conn: sqlite3.Connection, project_id: int, today: date | None = None
) -> dict[int, int | None]:
    """Assign every unowned open task in the project. Returns
    {task_id: member_id or None (unassignable/refused)}."""
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))
    strategy = config_loader.resolve(conn, project_id, "assignment_strategy")
    today = today or date.today()

    outcomes: dict[int, int | None] = {}
    touched_members: set[int] = set()

    for task in _tasks_needing_assignment(conn, project_id):
        task_id = task["task_id"]

        # NEW-OQ 4 treatment for a missing estimate: no effort number means
        # no capacity math — refuse and flag, never assign on a guess.
        if task["effort_hours"] is None:
            conn.execute(
                "UPDATE tasks SET unassignable = 1 WHERE task_id = ?", (task_id,)
            )
            raise_review_item(
                conn, project_id, "clarification",
                {"task_id": task_id, "title": task["title"],
                 "reason": "task has no effort estimate; cannot capacity-check"},
                created_by_skill="assignment_engine",
            )
            outcomes[task_id] = None
            continue

        # NEW-OQ 4: no planned window -> cannot be capacity-checked. Refuse.
        if not task["planned_start"] or not task["planned_end"]:
            conn.execute(
                "UPDATE tasks SET unassignable = 1,"
                " needs_clarification = 'no planned dates; run Scheduler before assignment'"
                " WHERE task_id = ?",
                (task_id,),
            )
            raise_review_item(
                conn, project_id, "clarification",
                {"task_id": task_id, "title": task["title"],
                 "reason": "task has no planned window; cannot capacity-check"},
                created_by_skill="assignment_engine",
            )
            outcomes[task_id] = None
            continue

        start = date.fromisoformat(task["planned_start"])
        end = date.fromisoformat(task["planned_end"])
        task_skills = set(json.loads(task["skill_tags"]))

        scored = []
        for member, overlap in _candidates(conn, task_skills):
            if not allocation.fits_capacity(
                conn, member["member_id"], member["capacity_hrs"],
                task["effort_hours"], start, end, calendar,
            ):
                continue
            peak = _peak_load_over_window(conn, member["member_id"], calendar, start, end)
            if strategy == "balanced_workload":
                key = (peak, -overlap, member["member_id"])
            else:  # best_skill_match
                key = (-overlap, peak, member["member_id"])
            scored.append((key, member["member_id"]))

        if not scored:
            conn.execute("UPDATE tasks SET unassignable = 1 WHERE task_id = ?", (task_id,))
            raise_review_item(
                conn, project_id, "unassignable_task",
                {"task_id": task_id, "title": task["title"],
                 "required_skills": sorted(task_skills),
                 "reason": "no active member with matching skills has remaining"
                           " capacity in every week of the task window"},
                created_by_skill="assignment_engine",
            )
            outcomes[task_id] = None
            continue

        scored.sort()
        winner = scored[0][1]
        conn.execute(
            "UPDATE tasks SET owner_id = ?, unassignable = 0 WHERE task_id = ?",
            (winner, task_id),
        )
        outcomes[task_id] = winner
        touched_members.add(winner)

    for member_id in touched_members:
        allocation.refresh_allocated_cache(conn, member_id, calendar, today)

    audit.log_action(
        conn,
        skill="assignment_engine",
        action="assign_tasks",
        input_summary={"strategy": strategy, "tasks": len(outcomes)},
        output_summary={
            "assigned": sum(1 for v in outcomes.values() if v),
            "unassignable": sum(1 for v in outcomes.values() if v is None),
        },
        project_id=project_id,
    )
    conn.commit()
    return outcomes

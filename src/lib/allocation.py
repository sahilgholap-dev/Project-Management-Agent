"""Time-phased capacity math (PRD section 9; rev-2 redesign, NEW-OQ 1/2/3/5).

THE authoritative capacity-check implementation — the Assignment Engine and the
tests both call this; nothing else computes load. Rules (all confirmed):

- Load is concurrent per ISO week (Monday start), never a flat backlog sum.
- A task's effort is spread uniformly over the WORKING DAYS of its planned
  window (weekends/holidays contribute nothing).
- Effective weekly capacity is prorated down in holiday weeks — same
  working-day basis as demand.
- Load is summed across EVERY active project the member owns tasks on.
- team_members.allocated_hrs is a display cache of current-week load; it is
  refreshed here but never read for decisions.

FF-1 (remaining-effort weighting, confirmed fast-follow): an existing task's
load contribution is effort_hours * (1 - percent_complete/100). A NULL
percent_complete counts as 0% complete — no signal means assume nothing is
confirmed done (full effort, the conservative direction). A task reported
100% but not yet statused done contributes nothing. The candidate task being
assigned always counts at full effort (it hasn't started).
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from src.lib.calendar import WorkingCalendar, week_monday, weeks_touching


class AllocationError(Exception):
    """A task window that cannot be capacity-checked (e.g. contains no working
    days). Callers refuse-and-flag rather than guessing (NEW-OQ 4 principle)."""


def task_week_contributions(
    effort_hours: float,
    planned_start: date,
    planned_end: date,
    calendar: WorkingCalendar,
) -> dict[date, float]:
    """Uniform spread of effort over the working days of the planned window,
    bucketed by ISO week Monday. Raises AllocationError on a window with no
    working days."""
    if planned_end < planned_start:
        raise AllocationError(
            f"planned_end {planned_end} precedes planned_start {planned_start}"
        )
    working_days = calendar.working_days_between(planned_start, planned_end)
    if not working_days:
        raise AllocationError(
            f"window {planned_start}..{planned_end} contains no working days"
        )
    per_day = effort_hours / len(working_days)
    buckets: dict[date, float] = {}
    for day in working_days:
        monday = week_monday(day)
        buckets[monday] = buckets.get(monday, 0.0) + per_day
    return buckets


def effective_weekly_capacity(
    capacity_hrs: float, calendar: WorkingCalendar, monday: date
) -> float:
    """Weekly capacity prorated by that week's actual working days versus the
    calendar's nominal working days per week (confirmed NEW-OQ 2)."""
    nominal = calendar.nominal_days_per_week()
    actual = calendar.count_working_days(monday, monday + timedelta(days=6))
    return capacity_hrs * (actual / nominal) if nominal else 0.0


def _open_owned_tasks(
    conn: sqlite3.Connection, member_id: int, exclude_task_id: int | None
) -> list[sqlite3.Row]:
    """Open, dated tasks the member owns across every ACTIVE project (PRD
    section 9: cross-project by design)."""
    rows = conn.execute(
        "SELECT t.task_id, t.effort_hours, t.percent_complete,"
        "       t.planned_start, t.planned_end"
        " FROM tasks t JOIN projects p ON p.project_id = t.project_id"
        " WHERE t.owner_id = ? AND p.status = 'active'"
        "   AND t.status NOT IN ('done','cancelled')"
        "   AND t.planned_start IS NOT NULL AND t.planned_end IS NOT NULL",
        (member_id,),
    ).fetchall()
    return [r for r in rows if r["task_id"] != exclude_task_id]


def remaining_effort(effort_hours: float, percent_complete: float | None) -> float:
    """FF-1: remaining-effort weighting. NULL percent_complete -> 0% complete
    (full effort counted — no signal means nothing is confirmed done)."""
    done_fraction = (percent_complete or 0.0) / 100.0
    return effort_hours * (1.0 - done_fraction)


def member_weekly_load(
    conn: sqlite3.Connection,
    member_id: int,
    calendar: WorkingCalendar,
    exclude_task_id: int | None = None,
) -> dict[date, float]:
    """Concurrent load per ISO week (Monday -> hours) from every open, dated
    task the member owns on any active project."""
    load: dict[date, float] = {}
    for task in _open_owned_tasks(conn, member_id, exclude_task_id):
        effort = remaining_effort(task["effort_hours"], task["percent_complete"])
        if effort <= 0:
            continue
        contributions = task_week_contributions(
            effort,
            date.fromisoformat(task["planned_start"]),
            date.fromisoformat(task["planned_end"]),
            calendar,
        )
        for monday, hours in contributions.items():
            load[monday] = load.get(monday, 0.0) + hours
    return load


def fits_capacity(
    conn: sqlite3.Connection,
    member_id: int,
    capacity_hrs: float,
    candidate_effort: float,
    candidate_start: date,
    candidate_end: date,
    calendar: WorkingCalendar,
    tolerance: float = 1e-9,
) -> bool:
    """True iff, in EVERY week the candidate window touches, existing load plus
    the candidate's contribution stays within that week's effective capacity.
    Never over-allocates; boundary (load == capacity) fits."""
    candidate = task_week_contributions(
        candidate_effort, candidate_start, candidate_end, calendar
    )
    existing = member_weekly_load(conn, member_id, calendar)
    for monday, hours in candidate.items():
        cap = effective_weekly_capacity(capacity_hrs, calendar, monday)
        if existing.get(monday, 0.0) + hours > cap + tolerance:
            return False
    return True


def refresh_allocated_cache(
    conn: sqlite3.Connection, member_id: int, calendar: WorkingCalendar, today: date
) -> float:
    """Refresh team_members.allocated_hrs = current-ISO-week load. Display
    only (confirmed NEW-OQ 3); decisions never read this."""
    monday = week_monday(today)
    load = member_weekly_load(conn, member_id, calendar).get(monday, 0.0)
    conn.execute(
        "UPDATE team_members SET allocated_hrs = ? WHERE member_id = ?",
        (round(load, 6), member_id),
    )
    return load


def weeks_of_window(start: date, end: date) -> list[date]:
    return weeks_touching(start, end)

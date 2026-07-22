"""Earned Value Management math (PRD 8.4 step 6) — pure functions, no LLM.

Units are HOURS of budgeted effort (the PRD gives no per-task cost rates, so
effort_hours is the value unit; budget_total is not divisible per task in v1):

- PV (Planned Value): effort that SHOULD be complete by as_of, per the planned
  windows — each task's effort spread uniformly over the working days of its
  window (the same uniform-spread rule as capacity math, NEW-OQ 1).
- EV (Earned Value): effort actually complete — effort_hours x percent
  (done = 100%; NULL percent = 0%, the conservative no-signal default
  confirmed for FF-1).
- AC (Actual Cost): hours the owners REPORTED spending (latest report per
  task). Never a fabricated accrual: no report means 0 for that task, which
  makes CV err quiet rather than alarmist — documented limitation.

SV = EV - PV (negative = behind schedule).
CV = EV - AC (negative = over cost).

Tasks with NULL effort_hours are excluded everywhere (NEW-OQ 4 treatment —
they are already flagged and cannot carry unconfirmed numbers into this math).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from src.lib.calendar import WorkingCalendar


@dataclass(frozen=True)
class EvmSnapshot:
    planned_value: float
    earned_value: float
    actual_cost: float

    @property
    def schedule_variance(self) -> float:
        return self.earned_value - self.planned_value

    @property
    def cost_variance(self) -> float:
        return self.earned_value - self.actual_cost


def planned_fraction(
    planned_start: date, planned_end: date, as_of: date, calendar: WorkingCalendar
) -> float:
    """Share of a task's working-day window elapsed by end of as_of."""
    total = calendar.count_working_days(planned_start, planned_end)
    if total == 0:
        return 0.0
    elapsed = calendar.count_working_days(planned_start, min(planned_end, as_of))
    return elapsed / total


def snapshot(
    conn: sqlite3.Connection, project_id: int, as_of: date, calendar: WorkingCalendar
) -> EvmSnapshot:
    tasks = conn.execute(
        "SELECT task_id, effort_hours, percent_complete, status,"
        "       planned_start, planned_end"
        " FROM tasks WHERE project_id = ? AND status != 'cancelled'"
        "   AND effort_hours IS NOT NULL",
        (project_id,),
    ).fetchall()

    pv = ev = 0.0
    for t in tasks:
        if t["planned_start"] and t["planned_end"]:
            pv += t["effort_hours"] * planned_fraction(
                date.fromisoformat(t["planned_start"]),
                date.fromisoformat(t["planned_end"]),
                as_of, calendar,
            )
        if t["status"] == "done":
            ev += t["effort_hours"]
        else:
            ev += t["effort_hours"] * (t["percent_complete"] or 0.0) / 100.0

    # AC: the latest reported hours_spent per task (reports are cumulative).
    ac_row = conn.execute(
        "SELECT COALESCE(SUM(hours), 0) AS ac FROM ("
        "  SELECT (SELECT r.parsed_hours_spent FROM status_reports r"
        "          WHERE r.task_id = t.task_id AND r.parsed_hours_spent IS NOT NULL"
        "          ORDER BY r.received_at DESC, r.report_id DESC LIMIT 1) AS hours"
        "  FROM tasks t WHERE t.project_id = ? AND t.status != 'cancelled'"
        ")",
        (project_id,),
    ).fetchone()

    return EvmSnapshot(
        planned_value=round(pv, 6),
        earned_value=round(ev, 6),
        actual_cost=round(ac_row["ac"], 6),
    )

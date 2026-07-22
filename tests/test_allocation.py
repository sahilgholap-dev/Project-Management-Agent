"""lib/allocation.py unit tests — the time-phased capacity math, under the
confirmed rules: uniform spread over working days, ISO Monday weeks,
holiday-prorated capacity, full-effort counting (FF-1)."""

import json
from datetime import date

import pytest

from src.lib import allocation as al
from src.lib.calendar import WorkingCalendar, week_monday, weeks_touching

CAL = WorkingCalendar(
    {"workdays": [1, 2, 3, 4, 5], "holidays": ["2026-08-14"], "hours_per_day": 8}
)

WK1 = date(2026, 8, 3)   # Mon Aug 3
WK2 = date(2026, 8, 10)  # Mon Aug 10 (contains the Fri Aug 14 holiday)
WK3 = date(2026, 8, 17)


# --- calendar basics ---------------------------------------------------------

def test_week_monday_and_weeks_touching():
    assert week_monday(date(2026, 8, 5)) == WK1
    assert weeks_touching(date(2026, 8, 5), date(2026, 8, 12)) == [WK1, WK2]


def test_working_days_skip_weekend_and_holiday():
    days = CAL.working_days_between(date(2026, 8, 13), date(2026, 8, 17))
    assert days == [date(2026, 8, 13), date(2026, 8, 17)]  # 14 holiday, 15/16 weekend


# --- task_week_contributions -------------------------------------------------

def test_single_week_task():
    got = al.task_week_contributions(16, date(2026, 8, 3), date(2026, 8, 4), CAL)
    assert got == {WK1: 16}


def test_three_week_span_uniform():
    # Mon Aug 3 .. Fri Aug 21 = 5 + 4 (holiday) + 5 = 14 working days, 28h -> 2h/day
    got = al.task_week_contributions(28, date(2026, 8, 3), date(2026, 8, 21), CAL)
    assert got == {WK1: 10, WK2: 8, WK3: 10}


def test_partial_week_boundary():
    # Wed Aug 5 .. Wed Aug 12: 3 working days each side -> 10/10
    got = al.task_week_contributions(20, date(2026, 8, 5), date(2026, 8, 12), CAL)
    assert got == {WK1: 10, WK2: 10}


def test_holiday_gets_no_effort():
    # Aug 10..14: holiday Friday -> 4 working days, all in week 2
    got = al.task_week_contributions(32, date(2026, 8, 10), date(2026, 8, 14), CAL)
    assert got == {WK2: 32}


def test_window_with_no_working_days_raises():
    with pytest.raises(al.AllocationError):
        al.task_week_contributions(8, date(2026, 8, 15), date(2026, 8, 16), CAL)  # weekend


def test_inverted_window_raises():
    with pytest.raises(al.AllocationError):
        al.task_week_contributions(8, date(2026, 8, 10), date(2026, 8, 3), CAL)


# --- effective capacity (NEW-OQ 2: prorated in holiday weeks) ----------------

def test_effective_capacity_normal_week():
    assert al.effective_weekly_capacity(40, CAL, WK1) == 40


def test_effective_capacity_holiday_week():
    assert al.effective_weekly_capacity(40, CAL, WK2) == 32


# --- DB-backed load and fits_capacity ---------------------------------------

def _world(conn):
    """One member, two active projects + one archived, tasks across them."""
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    for pid, status in [(10, "active"), (20, "active"), (30, "archived")]:
        conn.execute(
            "INSERT INTO projects (project_id, client_id, name, status)"
            " VALUES (?, 1, ?, ?)",
            (pid, f"P{pid}", status),
        )
        conn.execute(
            "INSERT INTO phases (phase_id, project_id, name, description,"
            " planned_start, planned_end, sequence_order)"
            " VALUES (?, ?, 'ph', 'd', '2026-08-03', '2026-08-28', 1)",
            (pid, pid),
        )
    conn.execute(
        "INSERT INTO team_members (member_id, client_id, name, role, skill_tags,"
        " capacity_hrs) VALUES (1, 1, 'M', 'dev', ?, 40)",
        (json.dumps(["dev"]),),
    )
    conn.commit()


def _task(conn, task_id, project_id, effort, start, end, status="todo", owner=1):
    conn.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " owner_id, planned_start, planned_end, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, project_id, project_id, f"t{task_id}", effort, owner, start, end, status),
    )
    conn.commit()


def test_load_sums_across_active_projects_only(conn):
    _world(conn)
    _task(conn, 1, 10, 16, "2026-08-03", "2026-08-04")          # active A
    _task(conn, 2, 20, 8, "2026-08-05", "2026-08-05")           # active B
    _task(conn, 3, 30, 40, "2026-08-03", "2026-08-07")          # archived: ignored
    _task(conn, 4, 10, 24, "2026-08-06", "2026-08-07", "done")  # done: ignored
    assert al.member_weekly_load(conn, 1, CAL) == {WK1: 24}


def test_dateless_tasks_are_excluded_from_load(conn):
    _world(conn)
    conn.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours, owner_id)"
        " VALUES (9, 10, 10, 'dateless', 99, 1)"
    )
    assert al.member_weekly_load(conn, 1, CAL) == {}


def test_fits_capacity_boundary_and_overflow(conn):
    _world(conn)
    _task(conn, 1, 10, 30, "2026-08-03", "2026-08-07")
    # 30 + 10 = exactly 40: fits
    assert al.fits_capacity(conn, 1, 40, 10, date(2026, 8, 3), date(2026, 8, 7), CAL)
    # 30 + 10.5 > 40: does not fit
    assert not al.fits_capacity(conn, 1, 40, 10.5, date(2026, 8, 3), date(2026, 8, 7), CAL)


def test_fits_capacity_checks_every_touched_week(conn):
    _world(conn)
    _task(conn, 1, 10, 40, "2026-08-03", "2026-08-07")  # week 1 full
    # spanning candidate contributes 10 to full week 1 -> refused even though
    # week 2 alone had room
    assert not al.fits_capacity(conn, 1, 40, 20, date(2026, 8, 5), date(2026, 8, 12), CAL)


def test_holiday_week_capacity_enforced(conn):
    _world(conn)
    # 32h in the 4-working-day week fills prorated capacity exactly
    _task(conn, 1, 10, 32, "2026-08-10", "2026-08-13")
    assert not al.fits_capacity(conn, 1, 40, 8, date(2026, 8, 10), date(2026, 8, 13), CAL)


# --- FF-1: remaining-effort weighting ----------------------------------------

def test_partially_complete_task_contributes_remaining_effort(conn):
    _world(conn)
    _task(conn, 1, 10, 32, "2026-08-03", "2026-08-06")
    conn.execute("UPDATE tasks SET percent_complete = 75 WHERE task_id = 1")
    assert al.member_weekly_load(conn, 1, CAL) == {WK1: 8}  # 32 * 25%


def test_null_percent_complete_counts_full_effort(conn):
    """No signal means nothing is confirmed done — full effort, conservative."""
    _world(conn)
    _task(conn, 1, 10, 32, "2026-08-03", "2026-08-06")  # percent_complete NULL
    assert al.member_weekly_load(conn, 1, CAL) == {WK1: 32}


def test_hundred_percent_but_not_done_contributes_nothing(conn):
    _world(conn)
    _task(conn, 1, 10, 32, "2026-08-03", "2026-08-06", status="in_progress")
    conn.execute("UPDATE tasks SET percent_complete = 100 WHERE task_id = 1")
    assert al.member_weekly_load(conn, 1, CAL) == {}


def test_fits_capacity_frees_room_as_work_completes(conn):
    _world(conn)
    _task(conn, 1, 10, 40, "2026-08-03", "2026-08-07")  # week 1 nominally full
    assert not al.fits_capacity(conn, 1, 40, 20, date(2026, 8, 3), date(2026, 8, 7), CAL)
    conn.execute("UPDATE tasks SET percent_complete = 50 WHERE task_id = 1")
    conn.commit()
    # 20h remaining + 20h candidate = 40: fits now
    assert al.fits_capacity(conn, 1, 40, 20, date(2026, 8, 3), date(2026, 8, 7), CAL)


def test_refresh_allocated_cache_is_current_week_only(conn):
    _world(conn)
    _task(conn, 1, 10, 16, "2026-08-03", "2026-08-04")   # week 1
    _task(conn, 2, 20, 24, "2026-08-10", "2026-08-12")   # week 2
    load = al.refresh_allocated_cache(conn, 1, CAL, today=date(2026, 8, 5))
    assert load == 16
    row = conn.execute("SELECT allocated_hrs FROM team_members WHERE member_id = 1").fetchone()
    assert row["allocated_hrs"] == 16

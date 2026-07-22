"""The PRD section 9 first-order requirement, time-phased (plan section 3):
one member shared by two projects; the Assignment Engine must never silently
over-allocate any week, in any assignment order.

Member capacity: 40 h/week. No holidays. All variants hand-computed."""

import json
from datetime import date

import pytest

from src import config_loader
from src.lib import allocation
from src.lib.calendar import WorkingCalendar
from src.skills import assignment_engine

TODAY = date(2026, 8, 3)
WK1 = ("2026-08-03", "2026-08-07")
WK2 = ("2026-08-10", "2026-08-14")

CONFIG = {
    "about_client": None,
    "project_definition": None,
    "reporting_cadence": "weekly",
    "comms_cadence": None,
    "skill_depth": {
        "task_breakdown": "assisted",
        "scheduler": "autonomous",
        "assignment_engine": "autonomous",
        "status_tracking": "assisted",
        "risk_tracking": "assisted",
        "dependency_manager": "autonomous",
        "meeting_summary": "assisted",
        "stakeholder_comms": "assisted",
    },
    "tools_channels": None,
    "primary_reviewer_id": 1,
    "backup_reviewer_id": None,
    "escalation_delay_hours": 24,
    "escalation_delay_by_tier": None,
    "change_approver_id": 1,
    "signoff_approver_id": 1,
    "voice_style": None,
    "working_calendar": {"workdays": [1, 2, 3, 4, 5], "holidays": [], "hours_per_day": 8},
    "assignment_strategy": "best_skill_match",
    "slip_threshold_days": 2,
}

CAL = WorkingCalendar(CONFIG["working_calendar"])
PROJECT_A, PROJECT_B = 20, 21
MEMBER = 1


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    conn.execute(
        "INSERT INTO team_members (member_id, client_id, name, role, skill_tags, capacity_hrs)"
        " VALUES (?, 1, 'Shared Dev', 'dev', ?, 40)",
        (MEMBER, json.dumps(["dev"])),
    )
    for pid, name in [(PROJECT_A, "A"), (PROJECT_B, "B")]:
        conn.execute(
            "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
            " VALUES (?, 1, ?, '2026-08-03', '2026-09-25')",
            (pid, name),
        )
        conn.execute(
            "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
            " planned_end, sequence_order)"
            " VALUES (?, ?, 'ph', 'd', '2026-08-03', '2026-09-25', 1)",
            (pid, pid),
        )
    conn.commit()
    return conn


_next_task_id = [100]


def add_task(conn, project_id, effort, window):
    _next_task_id[0] += 1
    task_id = _next_task_id[0]
    conn.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " skill_tags, planned_start, planned_end)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, project_id, project_id, f"task{task_id}", effort,
         json.dumps(["dev"]), window[0], window[1]),
    )
    conn.commit()
    return task_id


def assert_no_week_over_capacity(conn):
    """The section 15 invariant, recomputed from source of truth."""
    load = allocation.member_weekly_load(conn, MEMBER, CAL)
    for monday, hours in load.items():
        cap = allocation.effective_weekly_capacity(40, CAL, monday)
        assert hours <= cap + 1e-9, f"week {monday} over-allocated: {hours} > {cap}"


def test_variant1_same_week_contention(world):
    """A books 30h in week 1; B brings 25h (10+10+5) to the same week.
    Expected: only the first 10h fits (30+10=40); 15h flagged, never assigned."""
    a_task = add_task(world, PROJECT_A, 30, WK1)
    assert assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY) == {a_task: MEMBER}

    b1 = add_task(world, PROJECT_B, 10, WK1)
    b2 = add_task(world, PROJECT_B, 10, WK1)
    b3 = add_task(world, PROJECT_B, 5, WK1)
    outcomes = assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)
    assert outcomes == {b1: MEMBER, b2: None, b3: None}

    flagged = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'unassignable_task'"
    ).fetchone()["n"]
    assert flagged == 2
    assert_no_week_over_capacity(world)


def test_variant2_disjoint_weeks_no_contention(world):
    """Same 30h/25h totals, but B's windows are the following week: all of B
    assigns. This is the regression test against the retired flat-sum design,
    which would have wrongly refused B."""
    add_task(world, PROJECT_A, 30, WK1)
    assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY)

    b_tasks = [add_task(world, PROJECT_B, e, WK2) for e in (10, 10, 5)]
    outcomes = assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)
    assert outcomes == {t: MEMBER for t in b_tasks}
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'unassignable_task'"
    ).fetchone()["n"] == 0
    assert_no_week_over_capacity(world)


def test_variant3_spanning_task_prorates_and_fits_at_boundary(world):
    """B's 20h task spans Wed Aug 5 .. Wed Aug 12: 3 working days each week
    -> 10h/10h. Week 1 = A's 30 + 10 = exactly 40 = capacity: assignable
    (the <=-boundary test)."""
    add_task(world, PROJECT_A, 30, WK1)
    assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY)

    spanning = add_task(world, PROJECT_B, 20, ("2026-08-05", "2026-08-12"))
    outcomes = assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)
    assert outcomes == {spanning: MEMBER}

    load = allocation.member_weekly_load(world, MEMBER, CAL)
    assert load[date(2026, 8, 3)] == pytest.approx(40)
    assert load[date(2026, 8, 10)] == pytest.approx(10)
    assert_no_week_over_capacity(world)


def test_variant3b_spanning_task_refused_when_one_week_overflows(world):
    """Sub-case: A carries 32h in week 1, so 32+10=42 > 40 -> the spanning task
    is refused even though week 2 alone had room."""
    add_task(world, PROJECT_A, 32, WK1)
    assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY)

    spanning = add_task(world, PROJECT_B, 20, ("2026-08-05", "2026-08-12"))
    outcomes = assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)
    assert outcomes == {spanning: None}
    assert world.execute(
        "SELECT unassignable FROM tasks WHERE task_id = ?", (spanning,)
    ).fetchone()["unassignable"] == 1
    assert_no_week_over_capacity(world)


def test_variant4_order_independence_never_over_allocates(world):
    """B-then-A order: B's 25h assigns first; A's 30h then exceeds (25+30=55)
    and is refused. Neither order silently over-allocates any week."""
    b_tasks = [add_task(world, PROJECT_B, e, WK1) for e in (10, 10, 5)]
    outcomes_b = assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)
    assert outcomes_b == {t: MEMBER for t in b_tasks}

    a_task = add_task(world, PROJECT_A, 30, WK1)
    outcomes_a = assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY)
    assert outcomes_a == {a_task: None}
    assert_no_week_over_capacity(world)


def test_allocated_cache_matches_recomputation(world):
    add_task(world, PROJECT_A, 30, WK1)
    assignment_engine.assign_tasks(world, PROJECT_A, today=TODAY)
    add_task(world, PROJECT_B, 10, WK1)
    assignment_engine.assign_tasks(world, PROJECT_B, today=TODAY)

    cached = world.execute(
        "SELECT allocated_hrs FROM team_members WHERE member_id = ?", (MEMBER,)
    ).fetchone()["allocated_hrs"]
    recomputed = allocation.member_weekly_load(world, MEMBER, CAL)[date(2026, 8, 3)]
    assert cached == pytest.approx(recomputed) == pytest.approx(40)

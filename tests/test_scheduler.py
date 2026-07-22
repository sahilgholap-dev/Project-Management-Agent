"""Scheduler (8.2) against the hand-computed known-answer fixture."""

import pytest

from src.lib.task_graph import DependencyCycleError
from src.skills import scheduler
from tests.fixtures import known_answer_project as ka


@pytest.fixture
def world(conn):
    ka.build(conn)
    return conn


def test_cpm_matches_hand_computed_answer(world):
    scheduler.schedule_project(world, ka.PROJECT_ID)
    rows = world.execute(
        "SELECT task_id, planned_start, planned_end, slack_days, on_critical_path"
        " FROM tasks ORDER BY task_id"
    ).fetchall()
    got = {
        r["task_id"]: (
            r["planned_start"], r["planned_end"], r["slack_days"], bool(r["on_critical_path"])
        )
        for r in rows
    }
    assert got == ka.EXPECTED_SCHEDULE


def test_holiday_is_skipped(world):
    scheduler.schedule_project(world, ka.PROJECT_ID)
    row = world.execute("SELECT planned_end FROM tasks WHERE task_id = 5").fetchone()
    # T5's 3rd working day lands on Aug 17 because Fri Aug 14 is a holiday
    assert row["planned_end"] == "2026-08-17"


def test_feasible_plan_raises_no_review_item(world):
    scheduler.schedule_project(world, ka.PROJECT_ID)
    count = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'infeasible_plan'"
    ).fetchone()["n"]
    assert count == 0


def test_infeasible_plan_raises_tier1_and_still_writes_dates(world):
    world.execute(
        "UPDATE projects SET timeline_end = '2026-08-21' WHERE project_id = ?",
        (ka.PROJECT_ID,),
    )
    scheduler.schedule_project(world, ka.PROJECT_ID)
    item = world.execute(
        "SELECT tier, status FROM review_queue WHERE item_type = 'infeasible_plan'"
    ).fetchone()
    assert (item["tier"], item["status"]) == (1, "pending")  # pending, never auto-approved
    dated = world.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE planned_start IS NOT NULL"
    ).fetchone()["n"]
    assert dated == len(ka.TASKS)  # reviewer sees the real (infeasible) plan


def test_dependency_cycle_fails_loudly(world):
    world.execute("INSERT INTO task_dependencies VALUES (10, 1)")  # closes a loop
    with pytest.raises(DependencyCycleError):
        scheduler.schedule_project(world, ka.PROJECT_ID)


def test_run_is_audit_logged(world):
    scheduler.schedule_project(world, ka.PROJECT_ID)
    row = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'scheduler'"
        " AND action = 'schedule_project'"
    ).fetchone()
    assert row["n"] == 1


def test_unestimated_task_excluded_from_cpm_and_flagged(world):
    """NEW-OQ 4 treatment for NULL effort: no CPM participation, Tier 1 flag,
    known-answer schedule for every estimated task unchanged."""
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (99, 2, ?, 'converted from meeting', NULL)",
        (ka.PROJECT_ID,),
    )
    world.commit()
    scheduler.schedule_project(world, ka.PROJECT_ID)

    row = world.execute(
        "SELECT planned_start, needs_clarification FROM tasks WHERE task_id = 99"
    ).fetchone()
    assert row["planned_start"] is None  # never scheduled on a guess
    assert "no effort estimate" in row["needs_clarification"]
    item = world.execute(
        "SELECT tier, payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()
    assert item["tier"] == 1 and '"task_id": 99' in item["payload"]

    got = {
        r["task_id"]: (r["planned_start"], r["planned_end"], r["slack_days"],
                       bool(r["on_critical_path"]))
        for r in world.execute(
            "SELECT task_id, planned_start, planned_end, slack_days, on_critical_path"
            " FROM tasks WHERE task_id != 99"
        )
    }
    assert got == ka.EXPECTED_SCHEDULE  # estimated tasks unaffected


def test_unestimated_exclusion_cascades_downstream(world):
    """Review decision (Phase 3 review, item 2): a task depending — directly
    or transitively — on an unestimated task is ALSO excluded from CPM and
    flagged. The schedule must never look complete while silently depending
    on an unknown."""
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (99, 2, ?, 'unestimated', NULL)",
        (ka.PROJECT_ID,),
    )
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (100, 2, ?, 'direct downstream', 16)",
        (ka.PROJECT_ID,),
    )
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (101, 2, ?, 'transitive downstream', 8)",
        (ka.PROJECT_ID,),
    )
    world.executemany("INSERT INTO task_dependencies VALUES (?, ?)",
                      [(99, 100), (100, 101)])
    world.commit()
    scheduler.schedule_project(world, ka.PROJECT_ID)

    for task_id in (100, 101):
        row = world.execute(
            "SELECT planned_start, needs_clarification FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        assert row["planned_start"] is None, f"task {task_id} was scheduled"
        assert "scheduling blocked" in row["needs_clarification"]
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"]
    assert n == 3  # 99 unestimated + 100 and 101 blocked-downstream

    # estimated tasks not downstream of the unknown are untouched
    got = {
        r["task_id"]: (r["planned_start"], r["planned_end"], r["slack_days"],
                       bool(r["on_critical_path"]))
        for r in world.execute(
            "SELECT task_id, planned_start, planned_end, slack_days, on_critical_path"
            " FROM tasks WHERE task_id < 99"
        )
    }
    assert got == ka.EXPECTED_SCHEDULE


def test_cascade_flagging_is_idempotent_and_appends_notes(world):
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (99, 2, ?, 'unestimated', NULL)",
        (ka.PROJECT_ID,),
    )
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " needs_clarification)"
        " VALUES (100, 2, ?, 'downstream', 16, 'already had a question')",
        (ka.PROJECT_ID,),
    )
    world.execute("INSERT INTO task_dependencies VALUES (99, 100)")
    world.commit()
    scheduler.schedule_project(world, ka.PROJECT_ID)
    scheduler.schedule_project(world, ka.PROJECT_ID)  # no duplicate items

    row = world.execute(
        "SELECT needs_clarification FROM tasks WHERE task_id = 100"
    ).fetchone()
    assert row["needs_clarification"].startswith("already had a question; ")
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"]
    assert n == 2  # one for 99, one for 100 — once each


def test_unestimated_flagging_is_idempotent(world):
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (99, 2, ?, 'converted', NULL)",
        (ka.PROJECT_ID,),
    )
    world.commit()
    scheduler.schedule_project(world, ka.PROJECT_ID)
    scheduler.schedule_project(world, ka.PROJECT_ID)  # re-run: no duplicate item
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"]
    assert n == 1


def test_missing_timeline_is_a_hard_error(world):
    world.execute("UPDATE projects SET timeline_end = NULL WHERE project_id = ?", (ka.PROJECT_ID,))
    with pytest.raises(scheduler.SchedulerError):
        scheduler.schedule_project(world, ka.PROJECT_ID)

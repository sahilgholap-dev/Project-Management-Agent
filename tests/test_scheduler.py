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


def test_missing_timeline_is_a_hard_error(world):
    world.execute("UPDATE projects SET timeline_end = NULL WHERE project_id = ?", (ka.PROJECT_ID,))
    with pytest.raises(scheduler.SchedulerError):
        scheduler.schedule_project(world, ka.PROJECT_ID)

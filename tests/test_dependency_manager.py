"""Dependency Manager (8.6) against the hand-computed known-answer fixture.
Slip scenario: T5 finishes 2 working days late (Aug 19 vs Aug 17)."""

import pytest

from src.skills import dependency_manager, scheduler
from tests.fixtures import known_answer_project as ka


@pytest.fixture
def world(conn):
    ka.build(conn)
    scheduler.schedule_project(conn, ka.PROJECT_ID)
    return conn


def _slip_t5(world):
    world.execute(
        "UPDATE tasks SET actual_start = planned_start, actual_end = '2026-08-19',"
        " status = 'done' WHERE task_id = 5"
    )
    world.commit()


def test_slip_reschedules_downstream_to_hand_computed_dates(world):
    _slip_t5(world)
    result = dependency_manager.handle_slip(world, 5)
    assert result["slip_days"] == ka.EXPECTED_SLIP_DAYS
    for task_id, (start, end) in ka.EXPECTED_AFTER_SLIP.items():
        row = world.execute(
            "SELECT planned_start, planned_end FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        assert (row["planned_start"], row["planned_end"]) == (start, end), f"T{task_id}"


def test_slip_leaves_upstream_and_unrelated_tasks_untouched(world):
    _slip_t5(world)
    before = {
        r["task_id"]: (r["planned_start"], r["planned_end"])
        for r in world.execute(
            "SELECT task_id, planned_start, planned_end FROM tasks"
            " WHERE task_id IN (1,2,3,4,6,8)"
        )
    }
    dependency_manager.handle_slip(world, 5)
    after = {
        r["task_id"]: (r["planned_start"], r["planned_end"])
        for r in world.execute(
            "SELECT task_id, planned_start, planned_end FROM tasks"
            " WHERE task_id IN (1,2,3,4,6,8)"
        )
    }
    assert before == after


def test_threshold_breach_raises_tier1_slip_impact(world):
    _slip_t5(world)
    result = dependency_manager.handle_slip(world, 5)
    assert result["breach_raised"] is True  # 2-day end shift > 1-day threshold
    item = world.execute(
        "SELECT tier, status, payload FROM review_queue WHERE item_type = 'slip_impact'"
    ).fetchone()
    assert (item["tier"], item["status"]) == (1, "pending")
    assert '"project_end_shift_days": 2' in item["payload"]


def test_slip_past_timeline_also_raises_infeasible_plan(world):
    # the re-run pushes T10 to Aug 31, past the Aug 27 timeline
    _slip_t5(world)
    dependency_manager.handle_slip(world, 5)
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'infeasible_plan'"
    ).fetchone()["n"]
    assert n == 1


def test_on_time_completion_is_a_no_op(world):
    world.execute(
        "UPDATE tasks SET actual_end = planned_end, status = 'done' WHERE task_id = 5"
    )
    world.commit()
    result = dependency_manager.handle_slip(world, 5)
    assert result == {"slip_days": 0, "affected": {}, "breach_raised": False}


def test_detect_and_handle_slips_finds_the_late_task(world):
    _slip_t5(world)
    results = dependency_manager.detect_and_handle_slips(world, ka.PROJECT_ID)
    assert len(results) == 1 and results[0]["slip_days"] == 2


def test_slip_on_terminal_task_affects_nothing(world):
    world.execute(
        "UPDATE tasks SET actual_end = '2026-08-28', status = 'done' WHERE task_id = 10"
    )
    world.commit()
    result = dependency_manager.handle_slip(world, 10)
    assert result["affected"] == {} and result["slip_days"] >= 1


def test_run_is_audit_logged(world):
    _slip_t5(world)
    dependency_manager.handle_slip(world, 5)
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'dependency_manager'"
    ).fetchone()["n"]
    assert n == 1

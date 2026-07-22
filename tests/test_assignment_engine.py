"""Assignment Engine (8.3) against the hand-computed known-answer fixture."""

import json
from datetime import date

import pytest

from src import config_loader
from src.skills import assignment_engine, scheduler
from tests.fixtures import known_answer_project as ka

TODAY = date(2026, 8, 3)


@pytest.fixture
def world(conn):
    ka.build(conn)
    scheduler.schedule_project(conn, ka.PROJECT_ID)
    return conn


def test_owner_map_matches_hand_computed_answer(world):
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes == ka.EXPECTED_OWNERS


def test_nothing_flagged_unassignable_in_feasible_fixture(world):
    assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    n = world.execute("SELECT COUNT(*) AS n FROM tasks WHERE unassignable = 1").fetchone()["n"]
    assert n == 0


def test_balanced_workload_gives_same_map_on_this_fixture(world):
    """All fixture tasks have a single skill tag, so overlap ties and both
    strategies reduce to the same load-based tie-break — asserted so a future
    scoring change that breaks this is caught. Strategy divergence is covered
    by test_strategies_diverge_on_multi_skill_task."""
    config_loader.save_project_overrides(
        world, ka.PROJECT_ID, {"assignment_strategy": "balanced_workload"}
    )
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes == ka.EXPECTED_OWNERS


def test_strategies_diverge_on_multi_skill_task(world):
    """T11 needs backend+frontend in an empty week; M2 (both skills) carries
    8h there, M1 (backend only) carries none. best_skill_match -> M2 (higher
    overlap); balanced_workload -> M1 (lower peak load)."""
    assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)

    def add_t11():
        world.execute("DELETE FROM tasks WHERE task_id = 11")
        world.execute(
            "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
            " skill_tags, planned_start, planned_end)"
            " VALUES (11, 2, ?, 'T11', 8, ?, '2026-09-01', '2026-09-01')",
            (ka.PROJECT_ID, json.dumps(["backend", "frontend"])),
        )
        world.execute(
            "INSERT OR REPLACE INTO tasks (task_id, phase_id, project_id, title,"
            " effort_hours, skill_tags, owner_id, planned_start, planned_end)"
            " VALUES (12, 2, ?, 'M2 ballast', 8, '[]', ?, '2026-09-02', '2026-09-02')",
            (ka.PROJECT_ID, ka.M2),
        )
        world.commit()

    add_t11()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[11] == ka.M2  # best_skill_match: overlap 2 beats overlap 1

    config_loader.save_project_overrides(
        world, ka.PROJECT_ID, {"assignment_strategy": "balanced_workload"}
    )
    add_t11()
    world.execute("UPDATE tasks SET owner_id = NULL WHERE task_id = 11")
    world.commit()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[11] == ka.M1  # balanced: peak 0 beats peak 8


def test_no_skill_match_flags_unassignable_tier1(world):
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " skill_tags, planned_start, planned_end)"
        " VALUES (13, 2, ?, 'ML task', 8, ?, '2026-08-18', '2026-08-18')",
        (ka.PROJECT_ID, json.dumps(["ml"])),
    )
    world.commit()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[13] is None
    row = world.execute("SELECT unassignable FROM tasks WHERE task_id = 13").fetchone()
    assert row["unassignable"] == 1
    item = world.execute(
        "SELECT tier, status FROM review_queue WHERE item_type = 'unassignable_task'"
    ).fetchone()
    assert (item["tier"], item["status"]) == (1, "pending")


def test_dateless_task_is_refused_with_clarification(world):
    """Confirmed NEW-OQ 4: no planned window -> refuse and flag, never assign."""
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours, skill_tags)"
        " VALUES (14, 2, ?, 'dateless', 8, ?)",
        (ka.PROJECT_ID, json.dumps(["backend"])),
    )
    world.commit()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[14] is None
    row = world.execute(
        "SELECT owner_id, unassignable FROM tasks WHERE task_id = 14"
    ).fetchone()
    assert row["owner_id"] is None and row["unassignable"] == 1
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"] == 1


def test_unestimated_task_is_refused_with_clarification(world):
    """NEW-OQ 4 treatment for NULL effort: refuse, flag, never assign."""
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " skill_tags, planned_start, planned_end)"
        " VALUES (15, 2, ?, 'unestimated', NULL, ?, '2026-08-18', '2026-08-18')",
        (ka.PROJECT_ID, json.dumps(["backend"])),
    )
    world.commit()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[15] is None
    row = world.execute(
        "SELECT owner_id, unassignable FROM tasks WHERE task_id = 15"
    ).fetchone()
    assert row["owner_id"] is None and row["unassignable"] == 1
    payloads = [
        r["payload"] for r in world.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ]
    assert any("no effort estimate" in p for p in payloads)


def test_inactive_members_are_excluded(world):
    world.execute("UPDATE team_members SET is_active = 0 WHERE member_id = ?", (ka.M3,))
    world.commit()
    outcomes = assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    assert outcomes[5] is None and outcomes[7] is None  # qa tasks now unassignable


def test_allocated_cache_refreshed_display_only(world):
    assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=date(2026, 8, 17))
    row = world.execute(
        "SELECT allocated_hrs FROM team_members WHERE member_id = ?", (ka.M3,)
    ).fetchone()
    # M3's week of Aug 17: T5 contributes 8 (1 of 3 working days), T7 32 (4 of 5)
    assert row["allocated_hrs"] == 40


def test_run_is_audit_logged(world):
    assignment_engine.assign_tasks(world, ka.PROJECT_ID, today=TODAY)
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'assignment_engine'"
    ).fetchone()["n"]
    assert n == 1

"""Task Breakdown (8.1) flow logic with a stubbed model. Real-model quality is
measured by eval_task_breakdown.py against the holdout project."""

import json

import pytest

from src import config_loader
from src.llm.sonnet_client import LLMValidationError
from src.skills import task_breakdown
from tests.fakes import FakeSonnet
from tests.fixtures.known_answer_project import CONFIG

PROJECT_ID = 10


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    for member_id, skills in [(1, ["backend"]), (2, ["frontend"])]:
        conn.execute(
            "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
            " VALUES (?, 1, ?, 'dev', ?)",
            (member_id, f"M{member_id}", json.dumps(skills)),
        )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, scope_document,"
        " timeline_start, timeline_end)"
        " VALUES (?, 1, 'Holdout-ish', 'Build a small portal.', '2026-08-03', '2026-08-27')",
        (PROJECT_ID,),
    )
    conn.commit()
    return conn


PHASES = {
    "phases": [
        {"name": "Build", "description": "build it", "planned_start": "2026-08-03",
         "planned_end": "2026-08-14", "needs_clarification": None},
        {"name": "Test", "description": "test it", "planned_start": "2026-08-10",
         "planned_end": "2026-08-27", "needs_clarification": None},
    ],
    "clarifications": [],
}

BUILD_TASKS = {
    "tasks": [
        {"title": "API", "description": "backend api", "effort_hours": 16,
         "skill_tags": ["backend"], "depends_on": [], "needs_clarification": None},
        {"title": "UI", "description": "frontend ui", "effort_hours": 16,
         "skill_tags": ["frontend"], "depends_on": ["API"], "needs_clarification": None},
    ]
}

TEST_TASKS = {
    "tasks": [
        {"title": "E2E tests", "description": "end to end", "effort_hours": 8,
         "skill_tags": ["backend"], "depends_on": ["UI"], "needs_clarification": None},
    ]
}


def test_two_pass_breakdown_writes_phases_then_tasks(world):
    result = task_breakdown.run(
        world, PROJECT_ID, sonnet=FakeSonnet([PHASES, BUILD_TASKS, TEST_TASKS])
    )
    assert result["phases"] == 2 and result["tasks"] == 3

    phases = world.execute(
        "SELECT name, planned_start, planned_end, sequence_order FROM phases"
        " ORDER BY sequence_order"
    ).fetchall()
    assert [(p["name"], p["sequence_order"]) for p in phases] == [("Build", 1), ("Test", 2)]
    # acceptance (PRD section 15): every phase has valid dates before any task under it
    assert all(p["planned_start"] and p["planned_end"] for p in phases)

    tasks = {
        r["title"]: r
        for r in world.execute("SELECT title, phase_id, effort_hours FROM tasks")
    }
    assert set(tasks) == {"API", "UI", "E2E tests"}


def test_dependencies_recorded_including_cross_phase(world):
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([PHASES, BUILD_TASKS, TEST_TASKS]))
    deps = {
        (r["predecessor_task_id"], r["successor_task_id"])
        for r in world.execute("SELECT * FROM task_dependencies")
    }
    ids = {r["title"]: r["task_id"] for r in world.execute("SELECT task_id, title FROM tasks")}
    assert (ids["API"], ids["UI"]) in deps
    assert (ids["UI"], ids["E2E tests"]) in deps  # cross-phase


def test_scheduler_handoff_dates_every_task(world):
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([PHASES, BUILD_TASKS, TEST_TASKS]))
    undated = world.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE planned_start IS NULL"
    ).fetchone()["n"]
    assert undated == 0


def test_ambiguity_is_flagged_not_guessed(world):
    phases = json.loads(json.dumps(PHASES))
    phases["phases"][0]["needs_clarification"] = "Which SSO provider?"
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([phases, BUILD_TASKS, TEST_TASKS]))
    row = world.execute(
        "SELECT needs_clarification FROM phases WHERE name = 'Build'"
    ).fetchone()
    assert row["needs_clarification"] == "Which SSO provider?"
    items = world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchall()
    assert any("Which SSO provider?" in r["payload"] for r in items)


def test_unknown_dependency_title_is_flagged_not_recorded(world):
    tasks = json.loads(json.dumps(BUILD_TASKS))
    tasks["tasks"][1]["depends_on"] = ["Nonexistent task"]
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([PHASES, tasks, TEST_TASKS]))
    assert world.execute("SELECT COUNT(*) AS n FROM task_dependencies").fetchone()["n"] == 1
    items = world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchall()
    assert any("Nonexistent task" in r["payload"] for r in items)


def test_over_capacity_phase_is_flagged(world):
    tasks = json.loads(json.dumps(BUILD_TASKS))
    tasks["tasks"][0]["effort_hours"] = 1000  # 2 members x 10 working days x 8h = 160h
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([PHASES, tasks, TEST_TASKS]))
    items = world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchall()
    assert any("over capacity" in r["payload"] for r in items)


def test_validation_failure_halts_and_surfaces(world):
    fake = FakeSonnet([LLMValidationError("missing required field 'phases'")])
    with pytest.raises(task_breakdown.TaskBreakdownHalted):
        task_breakdown.run(world, PROJECT_ID, sonnet=fake)
    assert world.execute("SELECT COUNT(*) AS n FROM phases").fetchone()["n"] == 0
    item = world.execute(
        "SELECT tier, status FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()
    assert (item["tier"], item["status"]) == (1, "pending")


def test_missing_scope_halts(world):
    world.execute("UPDATE projects SET scope_document = NULL WHERE project_id = ?", (PROJECT_ID,))
    world.commit()
    with pytest.raises(task_breakdown.TaskBreakdownHalted, match="no scope"):
        task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([]))


def test_run_is_audit_logged(world):
    task_breakdown.run(world, PROJECT_ID, sonnet=FakeSonnet([PHASES, BUILD_TASKS, TEST_TASKS]))
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'task_breakdown'"
        " AND action = 'breakdown'"
    ).fetchone()["n"]
    assert n == 1

"""Phase 6: LangGraph orchestrator end-to-end (stubbed model), the close
path, and the section 15 acceptance checks — including the second independent
project on the same shared codebase."""

import json
from datetime import date

import pytest

from src import config_loader
from src.governance.review_queue import resolve_item
from src.lib import allocation
from src.lib.calendar import WorkingCalendar
from src.orchestrator import graph, lifecycle
from tests.fakes import FakeSonnet
from tests.fixtures.known_answer_project import CONFIG

P1, P2 = 10, 20
CAL = WorkingCalendar(CONFIG["working_calendar"])

PHASES = {
    "phases": [
        {"name": "Build", "description": "build", "planned_start": "2026-08-03",
         "planned_end": "2026-08-14", "needs_clarification": None},
        {"name": "Test", "description": "test", "planned_start": "2026-08-10",
         "planned_end": "2026-08-27", "needs_clarification": None},
    ],
    "clarifications": [],
}
BUILD_TASKS = {
    "tasks": [
        {"title": "API", "description": "d", "effort_hours": 16,
         "skill_tags": ["backend"], "depends_on": [], "needs_clarification": None},
        {"title": "UI", "description": "d", "effort_hours": 16,
         "skill_tags": ["frontend"], "depends_on": ["API"], "needs_clarification": None},
    ]
}
TEST_TASKS = {
    "tasks": [
        {"title": "E2E", "description": "d", "effort_hours": 8,
         "skill_tags": ["qa"], "depends_on": ["UI"], "needs_clarification": None},
    ]
}


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    for member_id, name, skills in [
        (1, "Dev A", ["backend"]), (2, "Dev B", ["backend", "frontend"]),
        (3, "QA", ["qa"]),
    ]:
        conn.execute(
            "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
            " VALUES (?, 1, ?, 'eng', ?)",
            (member_id, name, json.dumps(skills)),
        )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, scope_document,"
        " timeline_start, timeline_end)"
        " VALUES (?, 1, 'P1', 'Build a portal.', '2026-08-03', '2026-08-27')",
        (P1,),
    )
    conn.execute(
        "INSERT INTO stakeholders (client_id, project_id, name, audience_type)"
        " VALUES (1, ?, 'Elena', 'exec')",
        (P1,),
    )
    conn.commit()
    return conn


def _onboard(world, project_id=P1, responses=(PHASES, BUILD_TASKS, TEST_TASKS)):
    return graph.onboard_project(
        world, project_id, date(2026, 8, 3), FakeSonnet(list(responses))
    )


# --- onboarding graph ----------------------------------------------------------

def test_onboarding_produces_dated_owned_plan(world):
    state = _onboard(world)
    assert state["halted"] is False
    assert state["results"]["assignment"]["unassignable"] == 0
    rows = world.execute(
        "SELECT title, planned_start, planned_end, owner_id FROM tasks"
    ).fetchall()
    assert len(rows) == 3
    assert all(r["planned_start"] and r["owner_id"] for r in rows)


def test_onboarding_halts_cleanly_on_breakdown_failure(world):
    from src.llm.sonnet_client import LLMValidationError

    state = _onboard(world, responses=[LLMValidationError("bad output")])
    assert state["halted"] is True
    assert world.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"] == 1  # surfaced, and nothing downstream ran


# --- monitoring graph -----------------------------------------------------------

def test_monitoring_cycle_processes_status_and_drafts_comms(world):
    _onboard(world)
    api_id = world.execute(
        "SELECT task_id FROM tasks WHERE title = 'API'"
    ).fetchone()["task_id"]
    world.execute(
        "INSERT INTO status_reports (task_id, member_id, raw_text)"
        " VALUES (?, 1, 'finished it, took about 15 hours')",
        (api_id,),
    )
    world.commit()

    fake = FakeSonnet([
        {"status": "done", "percent_complete": None, "hours_spent": 15,
         "is_ambiguous": False, "note": None},         # status parse
        {"candidates": []},                             # risk pattern scan
        "Exec update: on track.",                       # comms draft
    ])
    state = graph.run_monitoring_cycle(
        world, P1, date(2026, 8, 5), draft_comms=True, sonnet=fake
    )
    assert state["results"]["status"]["updated"] == 1
    assert state["results"]["comms"] == {"drafts": 1}
    task = world.execute(
        "SELECT status, actual_end FROM tasks WHERE task_id = ?", (api_id,)
    ).fetchone()
    assert task["status"] == "done" and task["actual_end"] == "2026-08-05"
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'comms_draft'"
        " AND status = 'pending'"
    ).fetchone()["n"] == 1
    # the comms draft was created after this cycle's escalation node ran; the
    # NEXT escalation check picks it up and notifies the primary reviewer
    from src.governance import escalation

    escalation.check_escalations(world)
    assert world.execute(
        "SELECT COUNT(*) AS n FROM escalation_log WHERE stage = 'primary_notified'"
    ).fetchone()["n"] >= 1


def test_slip_detection_with_plain_language_explanation(world):
    _onboard(world)
    # UI planned Aug 5-6; it lands Aug 12 -> 4 working days late,
    # pushing E2E and the project end past the 1-day threshold
    world.execute(
        "UPDATE tasks SET status = 'done', actual_start = planned_start,"
        " actual_end = '2026-08-12' WHERE title = 'UI'"
    )
    world.commit()

    # no meetings/status reports exist, so the risk pattern scan is skipped
    # without a model call — the only LLM call this cycle is the explanation
    fake = FakeSonnet([
        "UI finished 4 working days late, pushing E2E testing"
        " and the project end to Aug 13.",
    ])
    state = graph.run_monitoring_cycle(world, P1, date(2026, 8, 13), sonnet=fake)
    assert state["results"]["slips"]["handled"] == 1
    assert state["results"]["slips"]["explained"] == 1

    payload = json.loads(world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'slip_impact'"
    ).fetchone()["payload"])
    assert "explanation" in payload and "4 working days late" in payload["explanation"]
    assert payload["downstream_diffs"]  # the raw diff is still there
    e2e = world.execute(
        "SELECT planned_start FROM tasks WHERE title = 'E2E'"
    ).fetchone()
    assert e2e["planned_start"] == "2026-08-13"


def test_paused_project_runs_nothing_but_escalations(world):
    _onboard(world)
    world.execute(
        "UPDATE projects SET status = 'paused', paused_reason = 'test' WHERE project_id = ?",
        (P1,),
    )
    world.commit()
    audits_before = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill IN"
        " ('status_tracking','risk_tracking','dependency_manager','stakeholder_comms')"
    ).fetchone()["n"]

    state = graph.run_monitoring_cycle(
        world, P1, date(2026, 8, 10), draft_comms=True, sonnet=FakeSonnet([])
    )
    assert state["paused"] is True
    assert "status" not in state["results"] and "comms" not in state["results"]
    assert "escalations" in state["results"]  # the one thing that still runs
    audits_after = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill IN"
        " ('status_tracking','risk_tracking','dependency_manager','stakeholder_comms')"
    ).fetchone()["n"]
    assert audits_after == audits_before


@pytest.mark.parametrize("error_name", ["refusal", "transport"])
def test_explanation_failure_never_blocks_cycle_or_duplicates_items(world, error_name):
    """Review clarification (Phase 6): enrichment failure — refusal OR
    transport error — leaves the slip_impact standing with its raw diff, adds
    no second item, and the cycle completes."""
    import anthropic

    from src.llm.sonnet_client import LLMRefusalError

    error = (
        LLMRefusalError("declined") if error_name == "refusal"
        else anthropic.APIConnectionError(request=None)
    )
    _onboard(world)
    world.execute(
        "UPDATE tasks SET status = 'done', actual_start = planned_start,"
        " actual_end = '2026-08-12' WHERE title = 'UI'"
    )
    world.commit()

    state = graph.run_monitoring_cycle(
        world, P1, date(2026, 8, 13), draft_comms=False,
        sonnet=FakeSonnet([error]),
    )
    # cycle ran to completion: escalations node was reached
    assert "escalations" in state["results"]
    assert state["results"]["slips"]["handled"] == 1
    assert state["results"]["slips"]["explained"] == 0
    payload = json.loads(world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'slip_impact'"
    ).fetchone()["payload"])
    assert "explanation" not in payload
    assert payload["downstream_diffs"]  # raw diff intact — load-bearing
    # exactly ONE slip item, and no clarification stacked on top of it
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'slip_impact'"
    ).fetchone()["n"] == 1
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
        " AND created_by_skill IN ('orchestrator', 'dependency_manager')"
    ).fetchone()["n"] == 0


def test_comms_cadence_gate(world):
    """draft_comms=None applies the configured cadence (biweekly here): due
    when never drafted, not due the next day, due again after the interval."""
    config_loader.save_client_config(world, 1, dict(CONFIG, comms_cadence="biweekly"))
    _onboard(world)
    assert graph.comms_due(world, P1, date(2026, 8, 5)) is True  # never drafted

    fake = FakeSonnet([{"candidates": []}, "Exec update."])
    world.execute(
        "INSERT INTO status_reports (task_id, member_id, raw_text)"
        " VALUES ((SELECT task_id FROM tasks WHERE title='API'), 1, 'x')"
    )
    world.commit()
    fake = FakeSonnet([
        {"status": "in_progress", "percent_complete": 25, "hours_spent": 4,
         "is_ambiguous": False, "note": None},
        {"candidates": []},
        "Exec update.",
    ])
    state = graph.run_monitoring_cycle(world, P1, date(2026, 8, 5), sonnet=fake)
    assert state["results"]["comms"] == {"drafts": 1}  # cadence made it due

    # pin the draft's wall-clock created_at to the simulated cycle date
    world.execute(
        "UPDATE review_queue SET created_at = '2026-08-05 12:00:00'"
        " WHERE item_type = 'comms_draft'"
    )
    world.commit()
    assert graph.comms_due(world, P1, date(2026, 8, 6)) is False   # next day: not due
    assert graph.comms_due(world, P1, date(2026, 8, 19)) is True   # 14 days later


# --- close path -----------------------------------------------------------------

def test_close_path_retrospective_gated_archive(world):
    _onboard(world)
    item_id = lifecycle.generate_retrospective(
        world, P1, date(2026, 8, 28), FakeSonnet(["Retro: delivered with one slip."])
    )
    item = world.execute(
        "SELECT tier, item_type, status FROM review_queue WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    assert (item["tier"], item["item_type"], item["status"]) == (
        2, "retrospective", "pending",
    )
    assert world.execute(
        "SELECT status FROM projects WHERE project_id = ?", (P1,)
    ).fetchone()["status"] == "closed"

    # archive is refused until the retrospective is explicitly approved
    assert lifecycle.archive_project(world, P1) is False
    resolve_item(world, item_id, resolved_by=1, decision="approved")
    assert lifecycle.archive_project(world, P1) is True
    assert world.execute(
        "SELECT status FROM projects WHERE project_id = ?", (P1,)
    ).fetchone()["status"] == "archived"
    artifact = world.execute(
        "SELECT artifact_type, content FROM artifact_versions"
    ).fetchone()
    assert artifact["artifact_type"] == "retrospective"
    assert artifact["content"] == "Retro: delivered with one slip."


# --- section 15: second independent project, same shared codebase ---------------

P2_PHASES = {
    "phases": [
        {"name": "Sprint", "description": "one sprint", "planned_start": "2026-09-01",
         "planned_end": "2026-09-11", "needs_clarification": None},
    ],
    "clarifications": [],
}
P2_TASKS = {
    "tasks": [
        {"title": "Service A", "description": "d", "effort_hours": 16,
         "skill_tags": ["backend"], "depends_on": [], "needs_clarification": None},
        {"title": "Service B", "description": "d", "effort_hours": 16,
         "skill_tags": ["backend"], "depends_on": [], "needs_clarification": None},
    ]
}


def test_second_project_runs_on_same_codebase_with_overrides(world):
    _onboard(world)  # project 1 in place

    world.execute(
        "INSERT INTO projects (project_id, client_id, name, scope_document,"
        " timeline_start, timeline_end)"
        " VALUES (?, 1, 'P2', 'A second engagement.', '2026-09-01', '2026-09-25')",
        (P2,),
    )
    world.commit()
    config_loader.save_project_overrides(
        world, P2, {"assignment_strategy": "balanced_workload"}
    )

    state = _onboard(world, project_id=P2, responses=(P2_PHASES, P2_TASKS))
    assert state["halted"] is False
    rows = world.execute(
        "SELECT title, owner_id, planned_start FROM tasks WHERE project_id = ?",
        (P2,),
    ).fetchall()
    assert len(rows) == 2 and all(r["owner_id"] and r["planned_start"] for r in rows)
    # override resolved per project: P2 balanced, P1 still client default
    assert config_loader.resolve(world, P2, "assignment_strategy") == "balanced_workload"
    assert config_loader.resolve(world, P1, "assignment_strategy") == "best_skill_match"
    # balanced strategy split the two equal tasks across the two backend devs
    owners = {r["owner_id"] for r in rows}
    assert owners == {1, 2}

    # the section 15 capacity invariant holds ACROSS both projects
    for member_id in (1, 2, 3):
        cap = world.execute(
            "SELECT capacity_hrs FROM team_members WHERE member_id = ?", (member_id,)
        ).fetchone()["capacity_hrs"]
        for monday, hours in allocation.member_weekly_load(world, member_id, CAL).items():
            assert hours <= allocation.effective_weekly_capacity(cap, CAL, monday) + 1e-9

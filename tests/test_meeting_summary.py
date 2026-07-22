"""Meeting Summary (8.7) flow logic with a stubbed model. Real-model quality
is measured by eval_meeting_summary.py against the holdout transcripts."""

import json

import pytest

from src import config_loader
from src.llm.sonnet_client import LLMValidationError
from src.skills import meeting_summary
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
    for member_id, name in [(1, "Priya"), (2, "Marcus")]:
        conn.execute(
            "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
            " VALUES (?, 1, ?, 'dev', '[]')",
            (member_id, name),
        )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
        " VALUES (?, 1, 'P', '2026-08-03', '2026-08-27')",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order) VALUES (1, ?, 'Build', 'd', '2026-08-03',"
        " '2026-08-27', 1)",
        (PROJECT_ID,),
    )
    conn.commit()
    return conn


EXTRACTED = {
    "decisions": [{"decision": "Ship weekly", "decided_by": "Priya"}],
    "action_items": [
        {"description": "Send notes to the team", "owner": "Marcus",
         "due_date": "2026-08-05", "implies_new_work": False},
        {"description": "Build the CSV export endpoint", "owner": "Priya",
         "due_date": None, "implies_new_work": True},
    ],
    "blockers": [
        {"description": "Waiting on API credentials", "blocked_member": "Priya",
         "assigned_to": "Marcus"},
        {"description": "Staging environment down", "blocked_member": "Marcus",
         "assigned_to": None},
    ],
}


def _run(world, extracted=EXTRACTED):
    return meeting_summary.run(
        world, PROJECT_ID, "raw transcript text", uploaded_by=1,
        meeting_date="2026-08-04", sonnet=FakeSonnet([extracted]),
    )


def test_meeting_record_with_structured_decisions(world):
    result = _run(world)
    row = world.execute("SELECT decisions, raw_transcript FROM meetings").fetchone()
    assert json.loads(row["decisions"]) == EXTRACTED["decisions"]
    assert row["raw_transcript"] == "raw transcript text"
    assert result["decisions"] == 1


def test_action_items_with_matched_owners(world):
    _run(world)
    rows = world.execute(
        "SELECT description, owner_id, due_date FROM meeting_action_items"
        " ORDER BY action_item_id"
    ).fetchall()
    assert rows[0]["owner_id"] == 2  # Marcus, matched case-insensitively
    assert rows[1]["owner_id"] == 1  # Priya


def test_new_work_action_item_converts_to_linked_flagged_task(world):
    result = _run(world)
    assert result["converted_tasks"] == 1
    item = world.execute(
        "SELECT action_item_id, converted_task_id, status FROM meeting_action_items"
        " WHERE converted_task_id IS NOT NULL"
    ).fetchone()
    assert item["status"] == "converted"
    task = world.execute(
        "SELECT title, effort_hours, source_action_item_id, needs_clarification"
        " FROM tasks WHERE task_id = ?",
        (item["converted_task_id"],),
    ).fetchone()
    assert task["source_action_item_id"] == item["action_item_id"]
    # placeholder estimate is flagged, never silently trusted
    assert task["needs_clarification"] is not None
    payloads = [
        r["payload"] for r in world.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ]
    assert any("effort estimate" in p for p in payloads)


def test_unclear_blocker_owner_left_null_and_flagged(world):
    _run(world)
    rows = world.execute(
        "SELECT description, assigned_to, blocked_member_id FROM blockers"
        " ORDER BY blocker_id"
    ).fetchall()
    assert rows[0]["assigned_to"] == 2  # clear owner recorded
    assert rows[1]["assigned_to"] is None  # unclear -> NULL, never guessed
    payloads = [
        r["payload"] for r in world.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ]
    assert any("no clear resolution owner" in p for p in payloads)


def test_unknown_owner_name_is_flagged(world):
    extracted = json.loads(json.dumps(EXTRACTED))
    extracted["action_items"][0]["owner"] = "Somebody Unknown"
    _run(world, extracted)
    row = world.execute(
        "SELECT owner_id FROM meeting_action_items ORDER BY action_item_id"
    ).fetchone()
    assert row["owner_id"] is None
    payloads = [
        r["payload"] for r in world.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ]
    assert any("Somebody Unknown" in p for p in payloads)


def test_no_open_phase_flags_instead_of_creating_orphan_task(world):
    world.execute("UPDATE phases SET status = 'done'")
    world.commit()
    result = _run(world)
    assert result["converted_tasks"] == 0
    assert world.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
    payloads = [
        r["payload"] for r in world.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ]
    assert any("no open" in p for p in payloads)


def test_validation_failure_halts_and_surfaces(world):
    fake = FakeSonnet([LLMValidationError("not three buckets")])
    with pytest.raises(meeting_summary.MeetingSummaryHalted):
        meeting_summary.run(world, PROJECT_ID, "text", sonnet=fake)
    assert world.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"] == 0
    item = world.execute(
        "SELECT tier FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()
    assert item["tier"] == 1


def test_run_is_audit_logged(world):
    _run(world)
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'meeting_summary'"
    ).fetchone()["n"]
    assert n == 1

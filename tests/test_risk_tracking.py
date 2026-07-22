"""Risk & Issue Tracking (8.5): rule pass is pure code; pattern pass and
duplicate check are stubbed here (real-model quality via the holdout evals)."""

from datetime import date

import pytest

from src import config_loader
from src.skills import risk_tracking
from tests.fakes import FakeSonnet
from tests.test_status_tracking import CONFIG

PROJECT_ID = 10
EMPTY_SCAN = {"candidates": []}


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    conn.execute(
        "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
        " VALUES (1, 1, 'Dev', 'dev', '[]')"
    )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
        " VALUES (?, 1, 'P', '2026-08-03', '2026-08-14')",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order)"
        " VALUES (1, ?, 'Ph', 'd', '2026-08-03', '2026-08-14', 1)",
        (PROJECT_ID,),
    )
    conn.commit()
    return conn


def _behind_schedule(world):
    """One 40h task planned Aug 3-7, still at 0% on Aug 12 -> SV = -40."""
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " owner_id, planned_start, planned_end, status, percent_complete)"
        " VALUES (1, 1, ?, 'T1', 40, 1, '2026-08-03', '2026-08-07', 'in_progress', 0)",
        (PROJECT_ID,),
    )
    world.commit()


def _meeting(world, text):
    world.execute(
        "INSERT INTO meetings (project_id, raw_transcript, decisions)"
        " VALUES (?, ?, '[]')",
        (PROJECT_ID, text),
    )
    world.commit()


def test_rule_pass_inserts_variance_issue_without_llm(world):
    _behind_schedule(world)
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12),
                                     FakeSonnet([]))  # no meetings/reports: no LLM call
    assert len(result["inserted"]) == 1
    risk = world.execute("SELECT title, kind, source, score FROM risks_issues").fetchone()
    assert risk["source"] == "rule_based" and risk["kind"] == "issue"
    assert risk["score"] == 25  # severity 5 (ratio 40/8 >= 3) x likelihood 5
    alert = world.execute(
        "SELECT tier, status FROM review_queue WHERE item_type = 'risk_alert'"
    ).fetchone()
    assert (alert["tier"], alert["status"]) == (1, "pending")


def test_rule_pass_is_idempotent_via_exact_title(world):
    _behind_schedule(world)
    risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12), FakeSonnet([]))
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12), FakeSonnet([]))
    assert result["skipped_duplicates"] == 1 and not result["inserted"]
    assert world.execute("SELECT COUNT(*) AS n FROM risks_issues").fetchone()["n"] == 1


def test_capacity_over_allocation_candidate(world):
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " unassignable) VALUES (1, 1, ?, 'T1', 8, 1)",
        (PROJECT_ID,),
    )
    world.commit()
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 3), FakeSonnet([]))
    assert len(result["inserted"]) == 1
    risk = world.execute("SELECT title FROM risks_issues").fetchone()
    assert "over-allocation" in risk["title"]


def test_pattern_pass_inserts_with_clamped_scores(world):
    _meeting(world, "Gerald keeps saying the security board might reject the design.")
    scan = {"candidates": [{
        "title": "Security board may reject the auth design",
        "description": "Raised repeatedly in the last meeting.",
        "severity": 9,       # out of range -> clamped to 5
        "likelihood": 0,     # out of range -> clamped to 1
        "kind": "risk",
    }]}
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 3),
                                     FakeSonnet([scan]))
    assert len(result["inserted"]) == 1
    risk = world.execute(
        "SELECT severity, likelihood, source, kind FROM risks_issues"
    ).fetchone()
    assert (risk["severity"], risk["likelihood"]) == (5, 1)
    assert risk["source"] == "pattern_detected" and risk["kind"] == "risk"


def test_pattern_duplicate_is_skipped_via_sonnet_check(world):
    world.execute(
        "INSERT INTO risks_issues (project_id, kind, title, description, severity,"
        " likelihood, source)"
        " VALUES (?, 'risk', 'Auth design rejection risk', 'existing', 3, 3,"
        " 'pattern_detected')",
        (PROJECT_ID,),
    )
    _meeting(world, "Security board concerns again.")
    scan = {"candidates": [{
        "title": "Security board may reject the design",
        "description": "Same underlying concern, new wording.",
        "severity": 3, "likelihood": 3, "kind": "risk",
    }]}
    verdict = {"is_duplicate": True, "duplicate_of_risk_id": 1}
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 3),
                                     FakeSonnet([scan, verdict]))
    assert result["skipped_duplicates"] == 1 and not result["inserted"]
    assert world.execute("SELECT COUNT(*) AS n FROM risks_issues").fetchone()["n"] == 1


def test_scan_failure_flags_and_rule_pass_still_runs(world):
    from src.llm.sonnet_client import LLMValidationError

    _behind_schedule(world)
    _meeting(world, "notes")
    result = risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12),
                                     FakeSonnet([LLMValidationError("bad")]))
    assert len(result["inserted"]) == 1  # rule candidate unaffected
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"]
    assert n == 1


def test_cycle_is_audit_logged(world):
    risk_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 3), FakeSonnet([]))
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'risk_tracking'"
    ).fetchone()["n"]
    assert n == 1

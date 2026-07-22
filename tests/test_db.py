"""Schema and migration-runner tests. The review_queue constraints are Phase 0
artifacts: the no-auto-approval guarantee (PRD sections 10/15) must hold at the
database layer before any skill exists to exercise it."""

import sqlite3

import pytest

from src import db

ALL_TABLES = {
    "clients", "users", "client_config", "projects",
    "phases", "tasks", "task_dependencies", "team_members", "status_reports",
    "risks_issues", "blockers", "meetings", "meeting_action_items", "stakeholders",
    "review_queue", "escalation_log", "change_requests", "signoff_packets",
    "artifact_versions", "audit_log",
}


def test_migrate_creates_all_tables(conn):
    names = {
        r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert ALL_TABLES <= names


def test_migrate_is_idempotent(conn):
    assert db.migrate(conn) == []  # open_db already applied version 1


def _queue_row(conn, **overrides):
    row = {
        "project_id": 10,
        "tier": 1,
        "item_type": "risk_alert",
        "payload": "{}",
        "created_by_skill": "risk_tracking",
        "status": "pending",
        "resolved_by": None,
    }
    row.update(overrides)
    conn.execute(
        "INSERT INTO review_queue (project_id, tier, item_type, payload,"
        " created_by_skill, status, resolved_by)"
        " VALUES (:project_id, :tier, :item_type, :payload,"
        " :created_by_skill, :status, :resolved_by)",
        row,
    )


def test_review_queue_rejects_tier_0(seeded):
    with pytest.raises(sqlite3.IntegrityError):
        _queue_row(seeded, tier=0)


def test_review_queue_rejects_approval_without_human(seeded):
    """The no-auto-approval CHECK: approved/rejected require a resolved_by user."""
    for status in ("approved", "rejected"):
        with pytest.raises(sqlite3.IntegrityError):
            _queue_row(seeded, status=status, resolved_by=None)


def test_review_queue_has_no_auto_approved_status(seeded):
    with pytest.raises(sqlite3.IntegrityError):
        _queue_row(seeded, status="auto_approved")


def test_review_queue_accepts_human_approval(seeded):
    _queue_row(seeded, status="approved", resolved_by=2)


def test_risk_score_is_generated(seeded):
    seeded.execute(
        "INSERT INTO risks_issues (project_id, kind, title, severity, likelihood, source)"
        " VALUES (10, 'risk', 'API vendor delay', 4, 3, 'rule_based')"
    )
    row = seeded.execute("SELECT score FROM risks_issues").fetchone()
    assert row["score"] == 12


def test_task_dependency_rejects_self_loop(seeded):
    seeded.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order) VALUES (1, 10, 'P1', 'd', '2026-08-03', '2026-08-07', 1)"
    )
    seeded.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (1, 1, 10, 'T1', 8)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        seeded.execute("INSERT INTO task_dependencies VALUES (1, 1)")


def test_foreign_keys_enforced(seeded):
    with pytest.raises(sqlite3.IntegrityError):
        seeded.execute(
            "INSERT INTO projects (client_id, name) VALUES (999, 'orphan')"
        )

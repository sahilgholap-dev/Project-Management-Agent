import json

import pytest

from src import db


@pytest.fixture
def conn():
    connection = db.open_db(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    """One client, three users (admin/reviewer/backup), one project — the
    minimum world Phase 0 code operates on."""
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'Acme')")
    conn.executemany(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (?, 1, ?, ?, ?, 'active')",
        [
            (1, "admin@acme.test", "Admin", "client_admin"),
            (2, "reviewer@acme.test", "Reviewer", "member"),
            (3, "backup@acme.test", "Backup", "member"),
        ],
    )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, config_overrides)"
        " VALUES (10, 1, 'Project A', '{}')"
    )
    conn.commit()
    return conn


@pytest.fixture
def valid_config():
    return {
        "about_client": "Test client",
        "project_definition": "Discrete engagement with own budget and timeline.",
        "reporting_cadence": "weekly",
        "comms_cadence": "biweekly",
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
        "primary_reviewer_id": 2,
        "backup_reviewer_id": 3,
        "escalation_delay_hours": 24,
        "escalation_delay_by_tier": {"1": 8, "3": 48},
        "change_approver_id": 1,
        "signoff_approver_id": 1,
        "voice_style": "Concise and factual.",
        "working_calendar": {
            "workdays": [1, 2, 3, 4, 5],
            "holidays": ["2026-08-15"],
            "hours_per_day": 8,
        },
        "assignment_strategy": "best_skill_match",
        "slip_threshold_days": 2,
    }


def set_overrides_raw(conn, project_id, overrides):
    """Write overrides bypassing the validator — for simulating direct edits."""
    conn.execute(
        "UPDATE projects SET config_overrides = ? WHERE project_id = ?",
        (json.dumps(overrides), project_id),
    )
    conn.commit()

"""OQ-6 additions: blocker assign/resolve and risk score adjustment — both
audited with a real human actor, neither raising review items."""

import pytest

from src.skills import blockers, risk_tracking
from tests.test_risk_tracking import PROJECT_ID, world  # noqa: F401  (fixture reuse)


@pytest.fixture
def with_rows(world):  # noqa: F811
    world.execute(
        "INSERT INTO blockers (blocker_id, project_id, description, raised_by)"
        " VALUES (1, ?, 'Waiting on credentials', 1)",
        (PROJECT_ID,),
    )
    world.execute(
        "INSERT INTO risks_issues (risk_id, project_id, kind, title, severity,"
        " likelihood, source)"
        " VALUES (1, ?, 'risk', 'ERP unknown', 3, 3, 'pattern_detected')",
        (PROJECT_ID,),
    )
    world.commit()
    return world


def test_assign_blocker_updates_and_audits_human_actor(with_rows):
    result = blockers.assign_blocker(with_rows, 1, assigned_to=1, by_user=1)
    assert result == {"blocker_id": 1, "assigned_to": 1}
    row = with_rows.execute("SELECT assigned_to FROM blockers WHERE blocker_id = 1").fetchone()
    assert row["assigned_to"] == 1
    log = with_rows.execute(
        "SELECT actor FROM audit_log WHERE skill = 'blockers' AND action = 'assign_blocker'"
    ).fetchone()
    assert log["actor"] == "1"  # a human, never 'agent'


def test_assign_blocker_rejects_missing_or_inactive_member(with_rows):
    with pytest.raises(ValueError, match="does not exist or is inactive"):
        blockers.assign_blocker(with_rows, 1, assigned_to=99, by_user=1)
    with_rows.execute("UPDATE team_members SET is_active = 0 WHERE member_id = 1")
    with pytest.raises(ValueError, match="inactive"):
        blockers.assign_blocker(with_rows, 1, assigned_to=1, by_user=1)


def test_resolve_blocker_sets_timestamp_once(with_rows):
    blockers.resolve_blocker(with_rows, 1, by_user=1)
    row = with_rows.execute(
        "SELECT status, resolved_at FROM blockers WHERE blocker_id = 1"
    ).fetchone()
    assert row["status"] == "resolved" and row["resolved_at"] is not None
    with pytest.raises(ValueError, match="already resolved"):
        blockers.resolve_blocker(with_rows, 1, by_user=1)


def test_adjust_score_updates_and_audits(with_rows):
    result = risk_tracking.adjust_score(with_rows, 1, severity=5, likelihood=2, by_user=1)
    assert result["score"] == 10
    row = with_rows.execute(
        "SELECT severity, likelihood, score FROM risks_issues WHERE risk_id = 1"
    ).fetchone()
    assert (row["severity"], row["likelihood"], row["score"]) == (5, 2, 10)
    log = with_rows.execute(
        "SELECT actor, input_summary FROM audit_log WHERE action = 'adjust_score'"
    ).fetchone()
    assert log["actor"] == "1" and '"from": [3, 3]' in log["input_summary"]


def test_adjust_score_bounds_and_existence(with_rows):
    with pytest.raises(ValueError, match="1-5"):
        risk_tracking.adjust_score(with_rows, 1, severity=6, likelihood=3, by_user=1)
    with pytest.raises(ValueError, match="1-5"):
        risk_tracking.adjust_score(with_rows, 1, severity=3, likelihood=0, by_user=1)
    with pytest.raises(ValueError, match="does not exist"):
        risk_tracking.adjust_score(with_rows, 99, severity=3, likelihood=3, by_user=1)


def test_no_review_items_raised_by_either_action(with_rows):
    blockers.assign_blocker(with_rows, 1, assigned_to=1, by_user=1)
    risk_tracking.adjust_score(with_rows, 1, severity=4, likelihood=4, by_user=1)
    n = with_rows.execute("SELECT COUNT(*) AS n FROM review_queue").fetchone()["n"]
    assert n == 0  # actions during review, not new tiered decisions (OQ-6)
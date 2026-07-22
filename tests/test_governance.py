"""Phase 4 gate (plan section 2): prove no code path auto-approves a Tier >= 1
item — silence only ever escalates and ultimately pauses; approval always
requires a live human through resolve_item."""

from datetime import datetime, timedelta

import pytest

from src import config_loader
from src.governance import escalation, forms
from src.governance.review_queue import ResolutionError, raise_review_item, resolve_item
from src.governance.tiers import TIER_BY_ITEM_TYPE
from tests.fixtures.known_answer_project import CONFIG as KA_CONFIG

PROJECT_ID = 10
T0 = datetime(2026, 8, 3, 9, 0, 0)

CONFIG = dict(
    KA_CONFIG,
    primary_reviewer_id=2,
    backup_reviewer_id=3,
    escalation_delay_hours=24,
    escalation_delay_by_tier={"1": 8},
)


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.executemany(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (?, 1, ?, ?, ?, 'active')",
        [
            (1, "admin@c.test", "Admin", "client_admin"),
            (2, "rev@c.test", "Reviewer", "member"),
            (3, "backup@c.test", "Backup", "member"),
        ],
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, status)"
        " VALUES (?, 1, 'P', 'active')",
        (PROJECT_ID,),
    )
    conn.commit()
    return conn


def _item(world, item_type="risk_alert"):
    return raise_review_item(
        world, PROJECT_ID, item_type, {"x": 1}, created_by_skill="test"
    )


# --- human resolution ---------------------------------------------------------

def test_human_approval_records_resolver(world):
    item_id = _item(world)
    result = resolve_item(world, item_id, resolved_by=2, decision="approved",
                          notes="looks right")
    assert result["decision"] == "approved"
    row = world.execute(
        "SELECT status, resolved_by, resolved_at, reviewer_notes FROM review_queue"
        " WHERE item_id = ?", (item_id,),
    ).fetchone()
    assert row["status"] == "approved" and row["resolved_by"] == 2
    assert row["resolved_at"] is not None and row["reviewer_notes"] == "looks right"


def test_rejection_flow(world):
    item_id = _item(world)
    resolve_item(world, item_id, resolved_by=2, decision="rejected")
    row = world.execute(
        "SELECT status FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()
    assert row["status"] == "rejected"


def test_resolution_requires_live_human(world):
    item_id = _item(world)
    with pytest.raises(ResolutionError, match="does not exist"):
        resolve_item(world, item_id, resolved_by=999, decision="approved")
    world.execute("UPDATE users SET invite_status = 'disabled' WHERE user_id = 2")
    with pytest.raises(ResolutionError, match="disabled"):
        resolve_item(world, item_id, resolved_by=2, decision="approved")


def test_invalid_decision_and_double_resolution_rejected(world):
    item_id = _item(world)
    with pytest.raises(ResolutionError, match="approved or rejected"):
        resolve_item(world, item_id, resolved_by=2, decision="auto_approved")
    resolve_item(world, item_id, resolved_by=2, decision="approved")
    with pytest.raises(ResolutionError, match="already"):
        resolve_item(world, item_id, resolved_by=3, decision="rejected")


def test_tier_map_is_frozen(world):
    with pytest.raises(TypeError):
        TIER_BY_ITEM_TYPE["comms_draft"] = 0  # nothing can weaken oversight


# --- silence-escalation ladder (PRD section 10) --------------------------------

def test_full_ladder_primary_backup_pause_never_approves(world):
    item_id = _item(world)  # tier 1 -> per-tier delay 8h

    r = escalation.check_escalations(world, now=T0)
    assert r["primary_notified"] == [item_id]

    # before the delay elapses: nothing moves
    r = escalation.check_escalations(world, now=T0 + timedelta(hours=7))
    assert r == {"primary_notified": [], "backup_notified": [], "paused": []}

    r = escalation.check_escalations(world, now=T0 + timedelta(hours=9))
    assert r["backup_notified"] == [item_id]
    assert world.execute(
        "SELECT status FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()["status"] == "escalated"

    r = escalation.check_escalations(world, now=T0 + timedelta(hours=18))
    assert r["paused"] == [item_id]
    project = world.execute(
        "SELECT status, paused_reason FROM projects WHERE project_id = ?",
        (PROJECT_ID,),
    ).fetchone()
    assert project["status"] == "paused" and "silent" in project["paused_reason"]
    # the item was NEVER approved at any rung
    assert world.execute(
        "SELECT status FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()["status"] == "paused"
    stages = [
        r["stage"] for r in world.execute(
            "SELECT stage FROM escalation_log WHERE item_id = ? ORDER BY escalation_id",
            (item_id,),
        )
    ]
    assert stages == ["primary_notified", "backup_notified", "work_paused"]


def test_unset_backup_goes_straight_to_pause(world):
    config = dict(CONFIG, backup_reviewer_id=None)
    config_loader.save_client_config(world, 1, config)
    item_id = _item(world)
    escalation.check_escalations(world, now=T0)
    r = escalation.check_escalations(world, now=T0 + timedelta(hours=9))
    assert r["paused"] == [item_id] and r["backup_notified"] == []
    reason = world.execute(
        "SELECT paused_reason FROM projects WHERE project_id = ?", (PROJECT_ID,)
    ).fetchone()["paused_reason"]
    assert "no backup reviewer" in reason


def test_config_defect_pauses_instead_of_erroring(world):
    item_id = _item(world)
    world.execute("DELETE FROM client_config WHERE client_id = 1")
    world.commit()
    r = escalation.check_escalations(world, now=T0)
    assert r["paused"] == [item_id]
    reason = world.execute(
        "SELECT paused_reason FROM projects WHERE project_id = ?", (PROJECT_ID,)
    ).fetchone()["paused_reason"]
    assert "config defect" in reason


def test_per_tier_delay_override(world):
    tier1 = _item(world, "risk_alert")       # 8h via by_tier override
    tier2 = _item(world, "status_report")    # 24h client default
    escalation.check_escalations(world, now=T0)
    r = escalation.check_escalations(world, now=T0 + timedelta(hours=9))
    assert r["backup_notified"] == [tier1]   # tier 2 item still waiting
    r = escalation.check_escalations(world, now=T0 + timedelta(hours=25))
    assert tier2 in r["backup_notified"]


def test_escalation_is_idempotent_per_stage(world):
    _item(world)
    escalation.check_escalations(world, now=T0)
    escalation.check_escalations(world, now=T0 + timedelta(minutes=5))
    n = world.execute(
        "SELECT COUNT(*) AS n FROM escalation_log WHERE stage = 'primary_notified'"
    ).fetchone()["n"]
    assert n == 1


def test_resolve_from_paused_then_resume(world):
    item_id = _item(world)
    escalation.check_escalations(world, now=T0)
    escalation.check_escalations(world, now=T0 + timedelta(hours=9))
    escalation.check_escalations(world, now=T0 + timedelta(hours=18))

    assert escalation.resume_project(world, PROJECT_ID, by_user=1) is False  # still unresolved
    resolve_item(world, item_id, resolved_by=3, decision="approved")
    assert escalation.resume_project(world, PROJECT_ID, by_user=1) is True
    project = world.execute(
        "SELECT status, paused_reason FROM projects WHERE project_id = ?",
        (PROJECT_ID,),
    ).fetchone()
    assert project["status"] == "active" and project["paused_reason"] is None


# --- Tier 3 forms (human-initiated only, confirmed Q17) ------------------------

def test_change_request_gated_by_tier3_review(world):
    created = forms.create_change_request(
        world, PROJECT_ID, "Extend timeline", "Client asked for +2 weeks",
        requested_by=1,
    )
    item = world.execute(
        "SELECT tier, item_type FROM review_queue WHERE item_id = ?",
        (created["review_item_id"],),
    ).fetchone()
    assert (item["tier"], item["item_type"]) == (3, "change_request")

    resolve_item(world, created["review_item_id"], resolved_by=1, decision="approved")
    status = world.execute(
        "SELECT status FROM change_requests WHERE change_request_id = ?",
        (created["change_request_id"],),
    ).fetchone()["status"]
    assert status == "approved"


def test_signoff_packet_rejection_propagates(world):
    created = forms.create_signoff_packet(
        world, PROJECT_ID, "Milestone 1 deliverable", "packet body", requested_by=1
    )
    resolve_item(world, created["review_item_id"], resolved_by=1, decision="rejected")
    status = world.execute(
        "SELECT status FROM signoff_packets WHERE packet_id = ?",
        (created["packet_id"],),
    ).fetchone()["status"]
    assert status == "rejected"

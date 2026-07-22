"""Stakeholder Comms (8.8): draft-only, one Tier 2 item per audience, approved
text versioned. The no-send property is held statically by
test_import_guardrail.py; real-model draft quality is a pilot concern."""

import json
from datetime import date

import pytest

from src import config_loader
from src.governance.review_queue import resolve_item
from src.skills import stakeholder_comms
from tests.fakes import FakeSonnet
from tests.test_status_tracking import CONFIG

PROJECT_ID = 10
TODAY = date(2026, 8, 10)


@pytest.fixture
def world(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, dict(CONFIG, voice_style="Plain and direct."))
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
        " VALUES (?, 1, 'P', '2026-08-03', '2026-08-14')",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name) VALUES (99, 1, 'Other')"
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order)"
        " VALUES (1, ?, 'Build', 'd', '2026-08-03', '2026-08-14', 1)",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO risks_issues (project_id, kind, title, severity, likelihood, source)"
        " VALUES (?, 'risk', 'ERP access unconfirmed', 4, 3, 'pattern_detected')",
        (PROJECT_ID,),
    )
    conn.executemany(
        "INSERT INTO stakeholders (client_id, project_id, name, audience_type)"
        " VALUES (1, ?, ?, ?)",
        [
            (PROJECT_ID, "Elena", "exec"),      # project-scoped
            (None, "Whole Team", "team"),       # client-wide
            (99, "Investor Bob", "investor"),   # other project: excluded
        ],
    )
    conn.commit()
    return conn


def test_one_tier2_draft_per_audience(world):
    fake = FakeSonnet(["Team draft text.", "Exec draft text."])
    items = stakeholder_comms.run(world, PROJECT_ID, TODAY, fake)
    assert set(items) == {"team", "exec"}  # investor is on another project

    rows = world.execute(
        "SELECT tier, status, payload FROM review_queue WHERE item_type = 'comms_draft'"
    ).fetchall()
    assert len(rows) == 2
    for row in rows:
        assert (row["tier"], row["status"]) == (2, "pending")  # full review, never auto
        payload = json.loads(row["payload"])
        assert payload["draft"].endswith("draft text.")
        assert payload["data_basis"]["open_risks"][0]["title"] == "ERP access unconfirmed"


def test_drafts_carry_their_factual_basis(world):
    fake = FakeSonnet(["Team draft.", "Exec draft."])
    stakeholder_comms.run(world, PROJECT_ID, TODAY, fake)
    # the prompt received the project data, so the reviewer can trace claims
    assert '"open_risks"' in fake.calls[0]["user"]
    assert "Plain and direct." in fake.calls[0]["user"]


def test_approval_versions_the_final_text(world):
    fake = FakeSonnet(["Team draft.", "Exec draft."])
    items = stakeholder_comms.run(world, PROJECT_ID, TODAY, fake)

    # reviewer edits the exec draft before approving
    resolve_item(world, items["exec"], resolved_by=1, decision="approved",
                 final_text="Exec draft, edited by reviewer.")
    # team draft approved as-is
    resolve_item(world, items["team"], resolved_by=1, decision="approved")

    versions = {
        r["artifact_ref"]: r
        for r in world.execute(
            "SELECT artifact_ref, artifact_type, version_number, content, created_by"
            " FROM artifact_versions"
        )
    }
    assert versions[items["exec"]]["content"] == "Exec draft, edited by reviewer."
    assert versions[items["team"]]["content"] == "Team draft."
    for v in versions.values():
        assert v["artifact_type"] == "comms_message"
        assert v["version_number"] == 1 and v["created_by"] == 1


def test_rejection_versions_nothing(world):
    fake = FakeSonnet(["Team draft.", "Exec draft."])
    items = stakeholder_comms.run(world, PROJECT_ID, TODAY, fake)
    resolve_item(world, items["team"], resolved_by=1, decision="rejected")
    n = world.execute("SELECT COUNT(*) AS n FROM artifact_versions").fetchone()["n"]
    assert n == 0


def test_no_stakeholders_flags_instead_of_drafting(world):
    world.execute("DELETE FROM stakeholders")
    world.commit()
    items = stakeholder_comms.run(world, PROJECT_ID, TODAY, FakeSonnet([]))
    assert items == {}
    payload = world.execute(
        "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["payload"]
    assert "no stakeholders" in payload


def test_run_is_audit_logged(world):
    stakeholder_comms.run(world, PROJECT_ID, TODAY, FakeSonnet(["a.", "b."]))
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'stakeholder_comms'"
    ).fetchone()["n"]
    assert n == 1

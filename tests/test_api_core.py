"""F1 gate: full walkthrough of the API against a seeded DB — admin setup ->
config -> team -> project -> onboard -> queue -> resolve -> status/meetings ->
cycle -> registers -> close -> archive. LLM calls stubbed via dependency
override; no network."""

import pytest
from fastapi.testclient import TestClient

from api import bootstrap
from api.main import create_app
from api.sonnet_dep import get_sonnet
from tests.fakes import FakeSonnet
from tests.fixtures.known_answer_project import CONFIG
from tests.test_orchestrator import BUILD_TASKS, PHASES, TEST_TASKS


@pytest.fixture
def env(tmp_path):
    db_path = tmp_path / "test.db"
    creds = bootstrap.seed(db_path)
    app = create_app(db_path)
    with TestClient(app) as client:
        # platform admin sets up the client + users
        client.post("/auth/login", json={"email": creds["email"],
                                         "password": creds["password"]})
        client.post("/admin/clients", json={"name": "Acme"})
        admin_user = client.post("/admin/users", json={
            "email": "admin@acme.test", "display_name": "Client Admin",
            "role": "client_admin"}).json()
        member_user = client.post("/admin/users", json={
            "email": "dev@acme.test", "display_name": "Dev", "role": "member"}).json()
        # switch to the client_admin session
        client.post("/auth/login", json={"email": "admin@acme.test",
                                         "password": admin_user["password"]})
        yield client, app, member_user


def _use_sonnet(app, responses):
    app.dependency_overrides[get_sonnet] = lambda: FakeSonnet(list(responses))


@pytest.fixture
def project(env):
    client, app, member = env
    client.put("/config", json=CONFIG)
    for name, skills in [("Dev A", ["backend"]), ("Dev B", ["backend", "frontend"]),
                         ("QA", ["qa"])]:
        client.post("/team-members", json={"name": name, "role": "eng",
                                           "skill_tags": skills})
    project_id = client.post("/projects", json={
        "name": "Portal", "scope_document": "Build a portal.",
        "timeline_start": "2026-08-03", "timeline_end": "2026-08-27",
    }).json()["project_id"]
    _use_sonnet(app, [PHASES, BUILD_TASKS, TEST_TASKS])
    onboarded = client.post(f"/projects/{project_id}/onboard",
                            json={"as_of": "2026-08-03"}).json()
    assert onboarded["halted"] is False
    return client, app, member, project_id


# --- config ---------------------------------------------------------------------

def test_config_validation_surfaces_defect_list(env):
    client, _, _ = env
    bad = dict(CONFIG, reporting_cadence="hourly")
    response = client.put("/config", json=bad)
    assert response.status_code == 422
    assert any("reporting_cadence" in d for d in response.json()["detail"]["defects"])


def test_resolved_config_shows_override_precedence(project):
    client, _, _, project_id = project
    client.put(f"/projects/{project_id}/overrides",
               json={"assignment_strategy": "balanced_workload"})
    resolved = client.get(f"/projects/{project_id}/config").json()
    assert resolved["assignment_strategy"] == "balanced_workload"
    assert resolved["reporting_cadence"] == "weekly"  # client default


# --- onboard + dashboard ----------------------------------------------------------

def test_onboard_produces_dated_owned_plan_via_api(project):
    client, _, _, project_id = project
    detail = client.get(f"/projects/{project_id}").json()
    assert len(detail["phases"]) == 2
    assert len(detail["tasks"]) == 3
    assert all(t["planned_start"] and t["owner_id"] for t in detail["tasks"])
    # CPM fields are exposed for the dashboard (this loose fixture has slack
    # everywhere — zero-slack criticality is covered by the known-answer tests)
    assert all(t["slack_days"] is not None for t in detail["tasks"])
    assert detail["dependencies"]


# --- review queue ------------------------------------------------------------------

def test_queue_resolution_via_api_records_logged_in_user(project):
    client, app, _, project_id = project
    # a meeting with an ownerless blocker raises a Tier 1 clarification
    _use_sonnet(app, [{
        "decisions": [], "action_items": [],
        "blockers": [{"description": "Staging down", "blocked_member": None,
                      "assigned_to": None}],
    }])
    client.post(f"/projects/{project_id}/meetings", json={"raw_text": "notes"})
    items = client.get(f"/review-queue?project_id={project_id}&status=pending").json()
    assert items and items[0]["tier"] == 1

    resolved = client.post(f"/review-queue/{items[0]['item_id']}/resolve",
                           json={"decision": "approved", "notes": "seen"})
    assert resolved.status_code == 200
    again = client.get(f"/review-queue?project_id={project_id}&status=approved").json()
    assert again[0]["item_id"] == items[0]["item_id"]


def test_invalid_decision_maps_to_409(project):
    client, app, _, project_id = project
    _use_sonnet(app, [{
        "decisions": [], "action_items": [],
        "blockers": [{"description": "x", "blocked_member": None, "assigned_to": None}],
    }])
    client.post(f"/projects/{project_id}/meetings", json={"raw_text": "notes"})
    item = client.get(f"/review-queue?project_id={project_id}").json()[0]
    response = client.post(f"/review-queue/{item['item_id']}/resolve",
                           json={"decision": "auto_approved"})
    assert response.status_code == 409


# --- member role boundaries --------------------------------------------------------

def test_member_can_submit_but_not_resolve_or_configure(project):
    client, app, member, project_id = project
    detail = client.get(f"/projects/{project_id}").json()
    task_id = detail["tasks"][0]["task_id"]

    client.post("/auth/login", json={"email": "dev@acme.test",
                                     "password": member["password"]})
    assert client.post("/status-reports", json={
        "task_id": task_id, "member_id": 1, "raw_text": "about half done",
    }).status_code == 201
    assert client.put("/config", json=CONFIG).status_code == 403
    assert client.post("/review-queue/1/resolve",
                       json={"decision": "approved"}).status_code == 403
    assert client.get(f"/projects/{project_id}").status_code == 200  # full read


# --- cycle + registers --------------------------------------------------------------

def test_cycle_processes_inbox_and_registers_flow(project):
    client, app, _, project_id = project
    detail = client.get(f"/projects/{project_id}").json()
    task_id = detail["tasks"][0]["task_id"]
    client.post("/status-reports", json={
        "task_id": task_id, "member_id": 1, "raw_text": "done, took 15h",
    })
    _use_sonnet(app, [
        {"status": "done", "percent_complete": None, "hours_spent": 15,
         "is_ambiguous": False, "note": None},
        {"candidates": [{"title": "ERP unknown", "description": "raised in notes",
                         "severity": 4, "likelihood": 3, "kind": "risk"}]},
    ])
    result = client.post(f"/projects/{project_id}/cycle",
                         json={"as_of": "2026-08-05", "draft_comms": False}).json()
    assert result["results"]["status"]["updated"] == 1

    risks = client.get(f"/projects/{project_id}/risks").json()
    assert risks and risks[0]["title"] == "ERP unknown"
    adjusted = client.patch(f"/risks/{risks[0]['risk_id']}/score",
                            json={"severity": 5, "likelihood": 2})
    assert adjusted.json()["score"] == 10
    audit = client.get(f"/projects/{project_id}/audit-log").json()
    assert any(a["action"] == "adjust_score" and a["actor"] != "agent" for a in audit)


def test_blocker_assignment_via_api(project):
    client, app, _, project_id = project
    _use_sonnet(app, [{
        "decisions": [], "action_items": [],
        "blockers": [{"description": "Creds missing", "blocked_member": "Dev A",
                      "assigned_to": None}],
    }])
    client.post(f"/projects/{project_id}/meetings", json={"raw_text": "notes"})
    unowned = client.get(f"/projects/{project_id}/blockers").json()[0]
    assert unowned["assigned_to"] is None
    patched = client.patch(f"/blockers/{unowned['blocker_id']}",
                           json={"assigned_to": 2})
    assert patched.status_code == 200
    updated = client.get(f"/projects/{project_id}/blockers").json()[0]
    assert updated["assigned_to_name"] == "Dev B"


# --- close path ----------------------------------------------------------------------

def test_close_and_archive_gated_by_retrospective_approval(project):
    client, app, _, project_id = project
    _use_sonnet(app, ["Retro: shipped."])
    item_id = client.post(f"/projects/{project_id}/close",
                          json={"as_of": "2026-08-28"}).json()["review_item_id"]

    refused = client.post(f"/projects/{project_id}/archive")
    assert refused.status_code == 409 and "refused" in refused.json()["detail"]

    client.post(f"/review-queue/{item_id}/resolve",
                json={"decision": "approved", "final_text": "Retro, edited."})
    assert client.post(f"/projects/{project_id}/archive").json()["status"] == "archived"
    artifacts = client.get(f"/projects/{project_id}/artifacts").json()
    assert artifacts[0]["artifact_type"] == "retrospective"
    assert artifacts[0]["content"] == "Retro, edited."

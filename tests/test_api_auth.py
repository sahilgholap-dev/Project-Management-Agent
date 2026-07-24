"""F0 gate: bootstrap, login/session, role gating, admin portal flows —
including the credentials-shown-once "invite" constraint (no send exists)."""

import pytest
from fastapi.testclient import TestClient

from api import bootstrap
from api.main import create_app
from src import db


@pytest.fixture
def env(tmp_path):
    db_path = tmp_path / "test.db"
    creds = bootstrap.seed(db_path)
    app = create_app(db_path)
    with TestClient(app) as client:
        yield client, creds, db_path


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def admin(env):
    client, creds, db_path = env
    assert _login(client, creds["email"], creds["password"]).status_code == 200
    return client, db_path


# --- auth ----------------------------------------------------------------------

def test_bootstrap_login_and_me(env):
    client, creds, _ = env
    response = _login(client, creds["email"], creds["password"])
    assert response.status_code == 200
    assert response.json()["role"] == "platform_admin"
    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["email"] == creds["email"]


def test_first_login_activates_invited_user(env):
    client, creds, db_path = env
    _login(client, creds["email"], creds["password"])
    conn = db.connect(db_path)
    status = conn.execute(
        "SELECT invite_status FROM users WHERE user_id = ?", (creds["user_id"],)
    ).fetchone()["invite_status"]
    conn.close()
    assert status == "active"


def test_wrong_password_and_unknown_user_rejected(env):
    client, creds, _ = env
    assert _login(client, creds["email"], "wrong").status_code == 401
    assert _login(client, "nobody@x.test", "x").status_code == 401


def test_unauthenticated_and_logout(env):
    client, creds, _ = env
    assert client.get("/auth/me").status_code == 401
    _login(client, creds["email"], creds["password"])
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_tampered_session_cookie_rejected(env):
    client, creds, _ = env
    _login(client, creds["email"], creds["password"])
    client.cookies.set("nexus_session", "1.9999999999.deadbeef")
    assert client.get("/auth/me").status_code == 401


def test_api_connections_survive_threadpool_handoff(env):
    """Regression (live bug): FastAPI runs sync dependencies and endpoint
    bodies on different threadpool threads; the per-request sqlite connection
    must tolerate the sequential cross-thread hand-off. The in-process test
    transport masks this, so reproduce the hand-off explicitly."""
    import threading

    _, _, db_path = env
    from api.deps import get_conn

    class FakeApp:
        pass

    class FakeRequest:
        app = FakeApp()

    FakeRequest.app.state = FakeApp()
    FakeRequest.app.state.db_path = str(db_path)

    generator = get_conn(FakeRequest())
    conn = next(generator)  # "dependency thread" = this thread

    result: list = []

    def use_in_other_thread():
        try:
            result.append(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
        except Exception as err:  # pragma: no cover - the failure branch
            result.append(err)

    thread = threading.Thread(target=use_in_other_thread)
    thread.start()
    thread.join()
    generator.close()
    assert not isinstance(result[0], Exception), f"cross-thread use failed: {result[0]}"
    assert result[0] >= 1


def test_bootstrap_refuses_second_run(env):
    _, _, db_path = env
    with pytest.raises(SystemExit, match="refused"):
        bootstrap.seed(db_path)


# --- admin portal: companies ------------------------------------------------------

def _create_company(client, name):
    response = client.post("/admin/clients", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _create_user(client, client_id, email, role="member", name="X"):
    return client.post("/admin/users", json={
        "client_id": client_id, "email": email, "display_name": name, "role": role,
    })


def test_multiple_companies_and_duplicate_name_rejected(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    other = _create_company(client, "Other")
    assert acme["client_id"] != other["client_id"]
    dup = client.post("/admin/clients", json={"name": "acme"})  # case-insensitive
    assert dup.status_code == 409


def test_company_list_excludes_platform_row_and_counts(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    _create_company(client, "Other")
    _create_user(client, acme["client_id"], "a@acme.test")
    companies = client.get("/admin/clients").json()
    assert [c["name"] for c in companies] == ["Acme", "Other"]
    assert companies[0]["user_count"] == 1 and companies[1]["user_count"] == 0


def test_rename_company(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    renamed = client.patch(f"/admin/clients/{acme['client_id']}",
                           json={"name": "Acme Corp"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Acme Corp"


def test_delete_company_safe_only(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    _create_user(client, acme["client_id"], "a@acme.test")
    blocked = client.delete(f"/admin/clients/{acme['client_id']}")
    assert blocked.status_code == 409 and "never deleted" in blocked.json()["detail"]
    empty = _create_company(client, "Empty Co")
    assert client.delete(f"/admin/clients/{empty['client_id']}").status_code == 204
    assert [c["name"] for c in client.get("/admin/clients").json()] == ["Acme"]


def test_platform_row_is_not_a_manageable_company(admin):
    # the __platform__ bootstrap row is client_id 1
    client, _ = admin
    assert client.patch("/admin/clients/1", json={"name": "X"}).status_code == 404
    assert client.delete("/admin/clients/1").status_code == 404
    assert _create_user(client, 1, "x@x.test").status_code == 404


# --- admin portal: users ----------------------------------------------------------

def test_create_user_returns_credentials_once_never_stores_plaintext(admin):
    """The plaintext exists ONLY in the one HTTP response. Verified against
    the entire database — every table and value via iterdump(), which covers
    auth_credentials AND audit_log summaries — not just the hash column."""
    client, db_path = admin
    acme = _create_company(client, "Acme")
    response = _create_user(client, acme["client_id"], "sahil@acme.test",
                            role="client_admin", name="Sahil")
    assert response.status_code == 201
    body = response.json()
    assert body["password"] and "manually" in body["handoff_note"]
    assert body["client_id"] == acme["client_id"]

    # the creation IS audited (section 13), with a human actor and no secret
    conn = db.connect(db_path)
    audit_row = conn.execute(
        "SELECT actor, input_summary, output_summary FROM audit_log"
        " WHERE skill = 'admin_portal' AND action = 'create_user'"
    ).fetchone()
    assert audit_row is not None and audit_row["actor"] != "agent"

    # plaintext appears nowhere in the ENTIRE database dump
    full_dump = "\n".join(conn.iterdump())
    conn.close()
    assert body["password"] not in full_dump

    # and the new client_admin can log in with them
    assert _login(client, "sahil@acme.test", body["password"]).status_code == 200


def test_platform_admin_role_cannot_be_created_via_api(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    response = _create_user(client, acme["client_id"], "x@acme.test",
                            role="platform_admin")
    assert response.status_code == 422


def test_user_creation_requires_existing_company(admin):
    client, _ = admin
    assert _create_user(client, 999, "x@acme.test").status_code == 404


def test_admin_user_list_spans_companies_and_hides_platform_admin(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    other = _create_company(client, "Other")
    _create_user(client, acme["client_id"], "a@acme.test")
    _create_user(client, other["client_id"], "b@other.test", role="client_admin")
    users = client.get("/admin/users").json()
    assert [(u["email"], u["client_name"]) for u in users] == [
        ("a@acme.test", "Acme"), ("b@other.test", "Other")]
    assert all(u["role"] != "platform_admin" for u in users)
    assert all("password" not in u and "password_hash" not in u for u in users)


def test_update_user_and_disable_blocks_login(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    created = _create_user(client, acme["client_id"], "a@acme.test").json()
    patched = client.patch(f"/admin/users/{created['user_id']}", json={
        "display_name": "Renamed", "role": "client_admin",
        "invite_status": "disabled",
    })
    assert patched.status_code == 200
    body = patched.json()
    assert (body["display_name"], body["role"], body["invite_status"]) == \
        ("Renamed", "client_admin", "disabled")
    assert _login(client, "a@acme.test", created["password"]).status_code == 401
    # re-enable restores access (a failed login leaves the admin session intact)
    reenabled = client.patch(f"/admin/users/{created['user_id']}",
                             json={"invite_status": "active"})
    assert reenabled.status_code == 200
    assert _login(client, "a@acme.test", created["password"]).status_code == 200


def test_reset_password_rotates_credentials(admin):
    client, db_path = admin
    acme = _create_company(client, "Acme")
    created = _create_user(client, acme["client_id"], "a@acme.test").json()
    reset = client.post(f"/admin/users/{created['user_id']}/reset-password")
    assert reset.status_code == 200
    new_password = reset.json()["password"]
    assert new_password and new_password != created["password"]

    # plaintext never stored, old password dead, new one works
    conn = db.connect(db_path)
    full_dump = "\n".join(conn.iterdump())
    conn.close()
    assert new_password not in full_dump
    assert _login(client, "a@acme.test", created["password"]).status_code == 401
    assert _login(client, "a@acme.test", new_password).status_code == 200


def test_platform_admin_account_not_manageable_via_portal(admin):
    # user_id 1 is the bootstrap platform_admin
    client, _ = admin
    assert client.patch("/admin/users/1",
                        json={"display_name": "X"}).status_code == 404
    assert client.post("/admin/users/1/reset-password").status_code == 404


def test_role_gating_client_admin_cannot_use_admin_portal(admin):
    client, _ = admin
    acme = _create_company(client, "Acme")
    created = _create_user(client, acme["client_id"], "sahil@acme.test",
                           role="client_admin", name="Sahil").json()
    _login(client, "sahil@acme.test", created["password"])  # replaces session
    assert client.post("/admin/clients", json={"name": "Nope"}).status_code == 403
    assert _create_user(client, acme["client_id"], "y@acme.test").status_code == 403
    assert client.get("/admin/clients").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert client.patch(f"/admin/users/{created['user_id']}",
                        json={"display_name": "X"}).status_code == 403
    assert client.post(
        f"/admin/users/{created['user_id']}/reset-password").status_code == 403


# --- admin portal: per-company config ---------------------------------------------

def test_admin_can_read_and_write_company_config(admin):
    from tests.fixtures.known_answer_project import CONFIG

    client, _ = admin
    acme = _create_company(client, "Acme")
    cid = acme["client_id"]
    reviewer = _create_user(client, cid, "rev@acme.test",
                            role="client_admin", name="Reviewer").json()

    assert client.get(f"/admin/clients/{cid}/config").status_code == 404  # unsaved
    config = dict(CONFIG, primary_reviewer_id=reviewer["user_id"],
                  change_approver_id=reviewer["user_id"],
                  signoff_approver_id=reviewer["user_id"])
    saved = client.put(f"/admin/clients/{cid}/config", json=config)
    assert saved.status_code == 200
    assert client.get(f"/admin/clients/{cid}/config").status_code == 200

    # defective saves surface the defect list, same contract as PUT /config
    bad = dict(config, reporting_cadence="hourly")
    response = client.put(f"/admin/clients/{cid}/config", json=bad)
    assert response.status_code == 422

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


# --- admin portal ----------------------------------------------------------------

def test_create_client_once_only(admin):
    client, _ = admin
    assert client.post("/admin/clients", json={"name": "Acme"}).status_code == 201
    second = client.post("/admin/clients", json={"name": "Other"})
    assert second.status_code == 409 and "single-client" in second.json()["detail"]


def test_create_user_returns_credentials_once_never_stores_plaintext(admin):
    """The plaintext exists ONLY in the one HTTP response. Verified against
    the entire database — every table and value via iterdump(), which covers
    auth_credentials AND audit_log summaries — not just the hash column."""
    client, db_path = admin
    client.post("/admin/clients", json={"name": "Acme"})
    response = client.post("/admin/users", json={
        "email": "sahil@acme.test", "display_name": "Sahil", "role": "client_admin",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["password"] and "manually" in body["handoff_note"]

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
    client.post("/admin/clients", json={"name": "Acme"})
    response = client.post("/admin/users", json={
        "email": "x@acme.test", "display_name": "X", "role": "platform_admin",
    })
    assert response.status_code == 422


def test_user_creation_requires_client_first(admin):
    client, _ = admin
    response = client.post("/admin/users", json={
        "email": "x@acme.test", "display_name": "X", "role": "member",
    })
    assert response.status_code == 409


def test_role_gating_client_admin_cannot_use_admin_portal(admin):
    client, _ = admin
    client.post("/admin/clients", json={"name": "Acme"})
    created = client.post("/admin/users", json={
        "email": "sahil@acme.test", "display_name": "Sahil", "role": "client_admin",
    }).json()
    _login(client, "sahil@acme.test", created["password"])  # replaces session
    assert client.post("/admin/clients", json={"name": "Nope"}).status_code == 403
    assert client.post("/admin/users", json={
        "email": "y@acme.test", "display_name": "Y", "role": "member",
    }).status_code == 403

"""client_config + per-project overrides — thin wrappers over config_loader.
Validation-on-every-save comes from the backend; a defective config returns
422 with the full defect list for the UI to render."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import Conn, User, require_role
from api.errors import backend_errors
from src import config_loader

router = APIRouter(tags=["config"])

CLIENT_WRITE = require_role("client_admin")
CLIENT_READ = require_role("client_admin", "member")


@router.get("/users", dependencies=[CLIENT_READ])
def list_users(conn: Conn, user: User) -> list[dict]:
    """Client-scoped user list (id/name/role) so the config screen can offer
    reviewer/approver selects. Plain read — no credentials exposed."""
    return [dict(r) for r in conn.execute(
        "SELECT user_id, display_name, email, role, invite_status FROM users"
        " WHERE client_id = ? ORDER BY user_id",
        (user["client_id"],),
    )]


@router.get("/config", dependencies=[CLIENT_READ])
def get_config(conn: Conn, user: User) -> dict:
    with backend_errors():
        return config_loader.load_client_config(conn, user["client_id"])


@router.put("/config", dependencies=[CLIENT_WRITE])
def put_config(body: dict, conn: Conn, user: User) -> dict:
    with backend_errors():
        config_loader.save_client_config(conn, user["client_id"], body)
    return config_loader.load_client_config(conn, user["client_id"])


@router.put("/projects/{project_id}/overrides", dependencies=[CLIENT_WRITE])
def put_overrides(project_id: int, body: dict, conn: Conn) -> dict:
    with backend_errors():
        config_loader.save_project_overrides(conn, project_id, body)
    return {"project_id": project_id, "config_overrides": body}


@router.get("/projects/{project_id}/config", dependencies=[CLIENT_READ])
def get_resolved_config(project_id: int, conn: Conn) -> dict:
    """The RESOLVED view (project override first, client default otherwise) so
    override behavior is visible during testing. Keys that fail resolution
    (required-missing-at-both-levels) surface as their defect text."""
    resolved = {}
    for key in sorted(config_loader.config_keys()):
        try:
            resolved[key] = config_loader.resolve(conn, project_id, key)
        except config_loader.ConfigDefectError as err:
            resolved[key] = {"config_defect": err.defects}
    return resolved

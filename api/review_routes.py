"""Review queue — the core testing surface (PRD section 10). Resolution goes
EXCLUSIVELY through review_queue.resolve_item; this module contains no SQL
writes to review_queue at all (the widened status-writer guardrail scans
this directory)."""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import Conn, User, require_role
from api.errors import backend_errors
from src.governance import escalation
from src.governance.review_queue import resolve_item

router = APIRouter(tags=["review"])

RESOLVER = require_role("client_admin")
CLIENT_READ = require_role("client_admin")  # members: My Work portal only


class ResolveBody(BaseModel):
    decision: str  # approved | rejected — validated by resolve_item itself
    notes: str | None = None
    final_text: str | None = None  # reviewer's edit for artifact-bearing items


@router.get("/review-queue", dependencies=[CLIENT_READ])
def list_items(
    conn: Conn,
    project_id: int | None = None,
    status: str | None = None,
    tier: int | None = None,
) -> list[dict]:
    clauses, values = [], []
    if project_id is not None:
        clauses.append("q.project_id = ?")
        values.append(project_id)
    if status is not None:
        clauses.append("q.status = ?")
        values.append(status)
    if tier is not None:
        clauses.append("q.tier = ?")
        values.append(tier)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT q.* FROM review_queue q {where} ORDER BY q.item_id DESC", values
    ).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        # escalation ladder state, so silence-escalation is verifiable in the UI
        item["escalation_stages"] = [
            dict(s) for s in conn.execute(
                "SELECT stage, reason, outcome, occurred_at FROM escalation_log"
                " WHERE item_id = ? ORDER BY escalation_id",
                (row["item_id"],),
            )
        ]
        items.append(item)
    return items


@router.post("/review-queue/{item_id}/resolve", dependencies=[RESOLVER])
def resolve(item_id: int, body: ResolveBody, conn: Conn, user: User) -> dict:
    """Wraps review_queue.resolve_item — the single human resolution path.
    resolved_by is ALWAYS the logged-in user; the client cannot supply it."""
    with backend_errors():
        return resolve_item(
            conn, item_id, resolved_by=user["user_id"],
            decision=body.decision, notes=body.notes, final_text=body.final_text,
        )


@router.post("/escalations/check", dependencies=[RESOLVER])
def check_escalations(conn: Conn) -> dict:
    """Wraps escalation.check_escalations (manual trigger for testing; it also
    runs inside every monitoring cycle)."""
    return escalation.check_escalations(conn)

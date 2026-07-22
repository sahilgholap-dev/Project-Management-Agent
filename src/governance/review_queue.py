"""The ONLY write path into review_queue. Skills never insert queue rows
directly — they call raise_review_item, which derives the tier from the frozen
map (never from config or a caller argument) and always starts at 'pending'.

Resolution (approve/reject) requires a live human user id — resolve_item is
the only resolution path, there is no auto-approve function anywhere, and the
DB CHECK independently rejects approved/rejected rows without resolved_by.
Silence never resolves anything: it escalates (escalation.py) and ultimately
pauses the project."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.governance.tiers import TIER_BY_ITEM_TYPE
from src.lib import audit


class ResolutionError(Exception):
    pass


def raise_review_item(
    conn: sqlite3.Connection,
    project_id: int,
    item_type: str,
    payload: Any,
    created_by_skill: str,
) -> int:
    """Insert a pending review item and return its id. Tier is looked up from
    the frozen map — callers cannot choose it."""
    tier = TIER_BY_ITEM_TYPE.get(item_type)
    if tier is None:
        raise ValueError(f"unknown review item_type: {item_type}")
    cur = conn.execute(
        "INSERT INTO review_queue (project_id, tier, item_type, payload, created_by_skill)"
        " VALUES (?, ?, ?, ?, ?)",
        (project_id, tier, item_type, json.dumps(payload), created_by_skill),
    )
    item_id = cur.lastrowid
    audit.log_action(
        conn,
        skill="governance",
        action="raise_review_item",
        input_summary={"item_type": item_type, "tier": tier, "by": created_by_skill},
        output_summary={"item_id": item_id},
        project_id=project_id,
    )
    return item_id


def resolve_item(
    conn: sqlite3.Connection,
    item_id: int,
    resolved_by: int,
    decision: str,
    notes: str | None = None,
    final_text: str | None = None,
) -> dict:
    """Human resolution — the single approve/reject path (PRD section 10).

    resolved_by must be an existing, non-disabled user; decision is 'approved'
    or 'rejected'. Resolvable from pending, escalated, or paused (a paused
    project's reviewer finally responding is exactly this call). Resolution of
    a Tier 3 item propagates to its linked change request / sign-off packet.

    final_text carries the reviewer's edited text for artifact-bearing items
    (comms drafts, status reports, retrospectives); on approval the final text
    (edit if provided, else the original draft) is versioned in
    artifact_versions here, so an approved-but-unversioned artifact cannot
    exist (PRD 8.8 step 7 / section 13).
    """
    if decision not in ("approved", "rejected"):
        raise ResolutionError(f"decision must be approved or rejected, not {decision!r}")
    user = conn.execute(
        "SELECT invite_status FROM users WHERE user_id = ?", (resolved_by,)
    ).fetchone()
    if user is None or user["invite_status"] == "disabled":
        raise ResolutionError(f"resolver user {resolved_by} does not exist or is disabled")
    item = conn.execute(
        "SELECT project_id, item_type, tier, status, payload FROM review_queue"
        " WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if item is None:
        raise ResolutionError(f"review item {item_id} does not exist")
    if item["status"] in ("approved", "rejected"):
        raise ResolutionError(f"review item {item_id} is already {item['status']}")

    conn.execute(
        "UPDATE review_queue SET status = ?, resolved_by = ?,"
        " resolved_at = datetime('now'), reviewer_notes = ? WHERE item_id = ?",
        (decision, resolved_by, notes, item_id),
    )

    # Artifact-bearing items: version the final approved text (PRD section 13
    # — every status report / comms message / retrospective is versioned).
    _ARTIFACT_TYPES = {
        "comms_draft": "comms_message",
        "status_report": "status_report",
        "retrospective": "retrospective",
    }
    if decision == "approved" and item["item_type"] in _ARTIFACT_TYPES:
        payload = json.loads(item["payload"])
        content = final_text or payload.get("draft") or payload.get("content")
        if content:
            version = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS v FROM artifact_versions"
                " WHERE artifact_type = ? AND artifact_ref = ?",
                (_ARTIFACT_TYPES[item["item_type"]], item_id),
            ).fetchone()["v"]
            conn.execute(
                "INSERT INTO artifact_versions (project_id, artifact_type, artifact_ref,"
                " version_number, content, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                (item["project_id"], _ARTIFACT_TYPES[item["item_type"]], item_id,
                 version, content, resolved_by),
            )

    # Tier 3 linkage: the review item IS the approval gate for the form row.
    if item["item_type"] == "change_request":
        conn.execute(
            "UPDATE change_requests SET status = ? WHERE review_item_id = ?",
            ("approved" if decision == "approved" else "rejected", item_id),
        )
    elif item["item_type"] == "signoff_packet":
        conn.execute(
            "UPDATE signoff_packets SET status = ? WHERE review_item_id = ?",
            ("signed_off" if decision == "approved" else "rejected", item_id),
        )

    audit.log_action(
        conn, skill="governance", action="resolve_item",
        input_summary={"item_id": item_id, "decision": decision,
                       "item_type": item["item_type"], "tier": item["tier"]},
        actor=str(resolved_by),
        project_id=item["project_id"],
    )
    conn.commit()
    return {"item_id": item_id, "decision": decision, "tier": item["tier"]}

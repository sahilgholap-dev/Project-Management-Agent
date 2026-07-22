"""Change requests and sign-off packets — human-initiated only in v1
(confirmed Q17): a reviewer/admin fills a basic form; no skill ever creates a
Tier 3 item. Skills raise their normal Tier 1 alerts and stop; auto-escalation
from alert to formal change request is Upgrade-phase.

Approval flows through the review_queue Tier 3 gate: resolve_item() on the
linked item is what moves these rows to approved / signed_off / rejected.
"""

from __future__ import annotations

import sqlite3

from src.governance.review_queue import raise_review_item
from src.lib import audit


def create_change_request(
    conn: sqlite3.Connection, project_id: int, title: str, description: str,
    requested_by: int,
) -> dict:
    cur = conn.execute(
        "INSERT INTO change_requests (project_id, title, description, requested_by,"
        " status) VALUES (?, ?, ?, ?, 'pending_approval')",
        (project_id, title, description, requested_by),
    )
    change_request_id = cur.lastrowid
    item_id = raise_review_item(
        conn, project_id, "change_request",
        {"change_request_id": change_request_id, "title": title,
         "requested_by": requested_by},
        created_by_skill="governance_form",
    )
    conn.execute(
        "UPDATE change_requests SET review_item_id = ? WHERE change_request_id = ?",
        (item_id, change_request_id),
    )
    audit.log_action(
        conn, skill="governance", action="create_change_request",
        input_summary={"change_request_id": change_request_id, "item_id": item_id},
        actor=str(requested_by), project_id=project_id,
    )
    conn.commit()
    return {"change_request_id": change_request_id, "review_item_id": item_id}


def create_signoff_packet(
    conn: sqlite3.Connection, project_id: int, title: str, content: str,
    requested_by: int,
) -> dict:
    cur = conn.execute(
        "INSERT INTO signoff_packets (project_id, title, content, status)"
        " VALUES (?, ?, ?, 'pending_signoff')",
        (project_id, title, content),
    )
    packet_id = cur.lastrowid
    item_id = raise_review_item(
        conn, project_id, "signoff_packet",
        {"packet_id": packet_id, "title": title, "requested_by": requested_by},
        created_by_skill="governance_form",
    )
    conn.execute(
        "UPDATE signoff_packets SET review_item_id = ? WHERE packet_id = ?",
        (item_id, packet_id),
    )
    audit.log_action(
        conn, skill="governance", action="create_signoff_packet",
        input_summary={"packet_id": packet_id, "item_id": item_id},
        actor=str(requested_by), project_id=project_id,
    )
    conn.commit()
    return {"packet_id": packet_id, "review_item_id": item_id}

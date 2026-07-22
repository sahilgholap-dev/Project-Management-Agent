"""The ONLY write path into review_queue. Skills never insert queue rows
directly — they call raise_review_item, which derives the tier from the frozen
map (never from config or a caller argument) and always starts at 'pending'.

The reviewer approve/reject flow and the silence-escalation ladder land in
Phase 4; raising items is final as of Phase 1 because every deterministic
skill needs it."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.governance.tiers import TIER_BY_ITEM_TYPE
from src.lib import audit


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

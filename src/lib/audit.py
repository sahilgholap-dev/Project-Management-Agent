"""audit_log writer (PRD section 13: every agent action is audit-logged with
timestamp, input, and output). Summaries only, never full document bodies
(confirmed Q16)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def log_action(
    conn: sqlite3.Connection,
    skill: str,
    action: str,
    input_summary: Any = None,
    output_summary: Any = None,
    project_id: int | None = None,
    actor: str = "agent",
) -> int:
    """Insert one audit_log row and return its id. Caller owns the transaction."""
    cur = conn.execute(
        "INSERT INTO audit_log (project_id, skill, action, input_summary, output_summary, actor)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            project_id,
            skill,
            action,
            json.dumps(input_summary) if input_summary is not None else None,
            json.dumps(output_summary) if output_summary is not None else None,
            actor,
        ),
    )
    return cur.lastrowid

"""Skill 8.7 — Meeting Summary. LLM reasoning (Claude Sonnet 5).

Extracts exactly three buckets — decisions, action items, blockers — validates
the structure, and writes meetings / meeting_action_items / blockers. Runs
before Task Breakdown and Risk Tracking in each cycle: its output is their
input.

Conversion (PRD 8.7 step 5): an action item implying new work becomes a linked
task (converted_task_id / source_action_item_id) in the earliest open phase.
The effort estimate cannot be known from meeting notes, so effort_hours is
left NULL — the Scheduler and Assignment Engine refuse-and-flag such tasks
(same treatment as a NULL planned window, NEW-OQ 4) until a reviewer supplies
a real estimate. Never a guessed number in correctness-critical math. A
blocker with unclear ownership is left unassigned and flagged (PRD 8.7 step 6).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.governance.review_queue import raise_review_item
from src.lib import audit
from src.llm.sonnet_client import LLMRefusalError, LLMValidationError, SonnetClient

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"

MEETING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions", "action_items", "blockers"],
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["decision", "decided_by"],
                "properties": {
                    "decision": {"type": "string"},
                    "decided_by": {"type": ["string", "null"]},
                },
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "owner", "due_date", "implies_new_work"],
                "properties": {
                    "description": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "implies_new_work": {"type": "boolean"},
                },
            },
        },
        "blockers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["description", "blocked_member", "assigned_to"],
                "properties": {
                    "description": {"type": "string"},
                    "blocked_member": {"type": ["string", "null"]},
                    "assigned_to": {"type": ["string", "null"]},
                },
            },
        },
    },
}


class MeetingSummaryHalted(Exception):
    pass


def _match_member(conn: sqlite3.Connection, name: str | None) -> int | None:
    """Case-insensitive roster lookup; None when unmatched — never guessed."""
    if not name:
        return None
    row = conn.execute(
        "SELECT member_id FROM team_members WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    return row["member_id"] if row else None


def _earliest_open_phase(conn: sqlite3.Connection, project_id: int) -> int | None:
    row = conn.execute(
        "SELECT phase_id FROM phases WHERE project_id = ? AND status != 'done'"
        " ORDER BY sequence_order LIMIT 1",
        (project_id,),
    ).fetchone()
    return row["phase_id"] if row else None


def run(
    conn: sqlite3.Connection,
    project_id: int,
    raw_text: str,
    uploaded_by: int | None = None,
    meeting_date: str | None = None,
    sonnet: SonnetClient | None = None,
) -> dict:
    sonnet = sonnet or SonnetClient()
    system = (_PROMPTS / "meeting_extract.md").read_text(encoding="utf-8")

    try:
        extracted = sonnet.structured(system, raw_text, MEETING_SCHEMA)
    except (LLMValidationError, LLMRefusalError) as err:
        raise_review_item(
            conn, project_id, "clarification",
            {"reason": f"meeting extraction failed validation: {err}"},
            created_by_skill="meeting_summary",
        )
        conn.commit()
        raise MeetingSummaryHalted(str(err)) from err

    cur = conn.execute(
        "INSERT INTO meetings (project_id, meeting_date, raw_transcript, decisions,"
        " uploaded_by) VALUES (?, ?, ?, ?, ?)",
        (project_id, meeting_date, raw_text, json.dumps(extracted["decisions"]), uploaded_by),
    )
    meeting_id = cur.lastrowid

    converted = 0
    for item in extracted["action_items"]:
        owner_id = _match_member(conn, item["owner"])
        cur = conn.execute(
            "INSERT INTO meeting_action_items (meeting_id, description, owner_id, due_date)"
            " VALUES (?, ?, ?, ?)",
            (meeting_id, item["description"], owner_id, item["due_date"]),
        )
        action_item_id = cur.lastrowid
        if item["owner"] and owner_id is None:
            raise_review_item(
                conn, project_id, "clarification",
                {"reason": f"action item owner '{item['owner']}' not found on the roster",
                 "action_item_id": action_item_id},
                created_by_skill="meeting_summary",
            )

        if item["implies_new_work"]:
            phase_id = _earliest_open_phase(conn, project_id)
            if phase_id is None:
                raise_review_item(
                    conn, project_id, "clarification",
                    {"reason": "action item implies new work but the project has no open"
                               " phase to attach it to",
                     "action_item_id": action_item_id},
                    created_by_skill="meeting_summary",
                )
                continue
            task_cur = conn.execute(
                "INSERT INTO tasks (phase_id, project_id, title, description,"
                " effort_hours, skill_tags, owner_id, source_action_item_id,"
                " needs_clarification)"
                " VALUES (?, ?, ?, ?, NULL, '[]', ?, ?, ?)",
                (phase_id, project_id, item["description"][:120], item["description"],
                 owner_id, action_item_id,
                 "no effort estimate — converted from a meeting action item;"
                 " excluded from scheduling and assignment until estimated"),
            )
            conn.execute(
                "UPDATE meeting_action_items SET converted_task_id = ?, status = 'converted'"
                " WHERE action_item_id = ?",
                (task_cur.lastrowid, action_item_id),
            )
            raise_review_item(
                conn, project_id, "clarification",
                {"reason": "task converted from meeting action item needs a real effort"
                           " estimate and skill tags",
                 "task_id": task_cur.lastrowid},
                created_by_skill="meeting_summary",
            )
            converted += 1

    unowned_blockers = 0
    for blocker in extracted["blockers"]:
        assigned_to = _match_member(conn, blocker["assigned_to"])
        cur = conn.execute(
            "INSERT INTO blockers (project_id, description, blocked_member_id,"
            " assigned_to, meeting_id) VALUES (?, ?, ?, ?, ?)",
            (project_id, blocker["description"],
             _match_member(conn, blocker["blocked_member"]), assigned_to, meeting_id),
        )
        if assigned_to is None:
            unowned_blockers += 1
            raise_review_item(
                conn, project_id, "clarification",
                {"reason": "blocker has no clear resolution owner",
                 "blocker_id": cur.lastrowid,
                 "description": blocker["description"]},
                created_by_skill="meeting_summary",
            )

    audit.log_action(
        conn, skill="meeting_summary", action="extract",
        input_summary={"transcript_chars": len(raw_text), "meeting_id": meeting_id},
        output_summary={
            "decisions": len(extracted["decisions"]),
            "action_items": len(extracted["action_items"]),
            "blockers": len(extracted["blockers"]),
            "converted_tasks": converted,
            "unowned_blockers": unowned_blockers,
        },
        project_id=project_id,
    )
    conn.commit()
    return {
        "meeting_id": meeting_id,
        "decisions": len(extracted["decisions"]),
        "action_items": len(extracted["action_items"]),
        "blockers": len(extracted["blockers"]),
        "converted_tasks": converted,
    }

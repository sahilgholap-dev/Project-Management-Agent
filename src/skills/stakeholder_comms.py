"""Skill 8.8 — Stakeholder Comms. LLM reasoning (Claude Sonnet 5).

DRAFT-ONLY BY DESIGN. This module's terminal write is a Tier 2 review_queue
row. There is no send function, no email/channel client, and no dispatch
capability anywhere in this codebase (statically enforced by
tests/test_import_guardrail.py) — after explicit approval, a HUMAN sends the
text through whatever channel they use. This is the one skill that never gets
an autonomous depth setting (enforced in the config schema itself).

Versioning (PRD 8.8 step 7 / section 13): the final approved text — the
reviewer's edit when provided, else the draft — is written to
artifact_versions by resolve_item at approval time, so an approved-but-
unversioned comms message cannot exist.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit, evm
from src.lib.calendar import WorkingCalendar
from src.llm.sonnet_client import LLMRefusalError, SonnetClient

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"

AUDIENCE_TYPES = ("team", "exec", "client", "investor")


def _project_data(conn: sqlite3.Connection, project_id: int, today: date) -> dict:
    """The factual basis every draft must trace to (PRD 8.8 step 1)."""
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))
    snap = evm.snapshot(conn, project_id, today, calendar)
    risks = [
        dict(r)
        for r in conn.execute(
            "SELECT title, description, severity, likelihood, score, kind"
            " FROM risks_issues WHERE project_id = ? AND status = 'open'"
            " ORDER BY score DESC LIMIT 10",
            (project_id,),
        )
    ]
    milestone_changes = [
        json.loads(r["payload"])
        for r in conn.execute(
            "SELECT payload FROM review_queue WHERE project_id = ?"
            " AND item_type = 'slip_impact' ORDER BY item_id DESC LIMIT 5",
            (project_id,),
        )
    ]
    phases = [
        dict(r)
        for r in conn.execute(
            "SELECT name, planned_start, planned_end, status FROM phases"
            " WHERE project_id = ? ORDER BY sequence_order",
            (project_id,),
        )
    ]
    return {
        "as_of": today.isoformat(),
        "evm": {
            "planned_value_hours": snap.planned_value,
            "earned_value_hours": snap.earned_value,
            "actual_cost_hours": snap.actual_cost,
            "schedule_variance_hours": round(snap.schedule_variance, 2),
            "cost_variance_hours": round(snap.cost_variance, 2),
            "cost_data_complete": snap.cost_data_complete,
        },
        "open_risks": risks,
        "recent_milestone_changes": milestone_changes,
        "phases": phases,
    }


def _audiences(conn: sqlite3.Connection, project_id: int) -> list[str]:
    """Distinct audience types from stakeholders: project-scoped plus
    client-wide (project_id NULL) rows (PRD 8.8 step 2)."""
    rows = conn.execute(
        "SELECT DISTINCT audience_type FROM stakeholders s"
        " JOIN projects p ON p.client_id = s.client_id"
        " WHERE p.project_id = ? AND (s.project_id = ? OR s.project_id IS NULL)",
        (project_id, project_id),
    ).fetchall()
    found = {r["audience_type"] for r in rows}
    return [a for a in AUDIENCE_TYPES if a in found]  # stable order


def run(
    conn: sqlite3.Connection,
    project_id: int,
    today: date,
    sonnet: SonnetClient | None = None,
) -> dict:
    """Draft one message per stakeholder audience; each lands in review_queue
    as a Tier 2 comms_draft. Returns {audience: item_id}."""
    sonnet = sonnet or SonnetClient()
    audiences = _audiences(conn, project_id)
    if not audiences:
        raise_review_item(
            conn, project_id, "clarification",
            {"reason": "no stakeholders configured for this project; cannot"
                       " determine a comms audience"},
            created_by_skill="stakeholder_comms",
        )
        conn.commit()
        return {}

    voice_style = config_loader.resolve(conn, project_id, "voice_style")
    data = _project_data(conn, project_id, today)
    system = (_PROMPTS / "comms_draft.md").read_text(encoding="utf-8")

    items: dict[str, int] = {}
    for audience in audiences:
        user_content = (
            f"Audience: {audience}\n"
            f"Voice/style instruction: {voice_style or 'none given'}\n\n"
            f"PROJECT DATA (the only permissible factual basis):\n"
            f"{json.dumps(data, indent=2)}"
        )
        try:
            draft = sonnet.text(system, user_content).strip()
        except LLMRefusalError as err:
            raise_review_item(
                conn, project_id, "clarification",
                {"reason": f"comms drafting for audience '{audience}' was refused: {err}"},
                created_by_skill="stakeholder_comms",
            )
            continue
        items[audience] = raise_review_item(
            conn, project_id, "comms_draft",
            {"audience_type": audience, "draft": draft,
             "data_basis": data, "voice_style": voice_style},
            created_by_skill="stakeholder_comms",
        )

    audit.log_action(
        conn, skill="stakeholder_comms", action="draft",
        input_summary={"as_of": today.isoformat(), "audiences": audiences},
        output_summary={"drafts": len(items)},
        project_id=project_id,
    )
    conn.commit()
    return items

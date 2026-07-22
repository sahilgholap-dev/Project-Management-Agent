"""Skill 8.4 — Status Tracking. Hybrid: Sonnet 5 parses free text, then
deterministic EVM math (lib/evm.py) does everything that matters.

Self-reports arrive via the status_reports inbox (manual entry in v1 —
confirmed Q7, no channel integrations). Sonnet's ONLY job is turning a
person's free-text reply into a structured status; a reply that doesn't
clearly map is flagged ambiguous and surfaced (PRD 8.4 step 4), never
guessed. The variance math and threshold checks are pure code.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit, evm
from src.lib.calendar import WorkingCalendar
from src.llm.sonnet_client import LLMRefusalError, LLMValidationError, SonnetClient

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"

STATUS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "percent_complete", "hours_spent", "is_ambiguous", "note"],
    "properties": {
        "status": {"enum": ["todo", "in_progress", "blocked", "done", None]},
        "percent_complete": {"type": ["number", "null"]},
        "hours_spent": {"type": ["number", "null"]},
        "is_ambiguous": {"type": "boolean"},
        "note": {"type": ["string", "null"]},
    },
}


def process_inbox(
    conn: sqlite3.Connection,
    project_id: int,
    today: date,
    sonnet: SonnetClient | None = None,
) -> dict:
    """Consume unprocessed status_reports rows for this project's tasks."""
    sonnet = sonnet or SonnetClient()
    system = (_PROMPTS / "status_parse.md").read_text(encoding="utf-8")
    rows = conn.execute(
        "SELECT r.report_id, r.task_id, r.raw_text, t.title, t.status,"
        "       t.actual_start"
        " FROM status_reports r JOIN tasks t ON t.task_id = r.task_id"
        " WHERE t.project_id = ? AND r.processed_at IS NULL"
        " ORDER BY r.received_at, r.report_id",
        (project_id,),
    ).fetchall()

    updated = ambiguous = 0
    for row in rows:
        user_content = (
            f"Task: {row['title']}\nCurrent status: {row['status']}\n\n"
            f"REPLY:\n{row['raw_text']}"
        )
        try:
            parsed = sonnet.structured(system, user_content, STATUS_SCHEMA)
        except (LLMValidationError, LLMRefusalError) as err:
            parsed = {"status": None, "percent_complete": None, "hours_spent": None,
                      "is_ambiguous": True, "note": f"parse failed: {err}"}

        percent = parsed["percent_complete"]
        if percent is not None:
            percent = max(0.0, min(100.0, float(percent)))

        if parsed["is_ambiguous"] or (
            parsed["status"] is None and percent is None and parsed["hours_spent"] is None
        ):
            ambiguous += 1
            conn.execute(
                "UPDATE status_reports SET is_ambiguous = 1, processed_at = ?"
                " WHERE report_id = ?",
                (today.isoformat(), row["report_id"]),
            )
            raise_review_item(
                conn, project_id, "clarification",
                {"report_id": row["report_id"], "task_id": row["task_id"],
                 "raw_text": row["raw_text"],
                 "reason": "status reply does not clearly map to a status — flagged,"
                           " not guessed"},
                created_by_skill="status_tracking",
            )
            continue

        conn.execute(
            "UPDATE status_reports SET parsed_status = ?, parsed_percent_complete = ?,"
            " parsed_hours_spent = ?, processed_at = ? WHERE report_id = ?",
            (parsed["status"], percent, parsed["hours_spent"],
             today.isoformat(), row["report_id"]),
        )

        new_status = parsed["status"] or row["status"]
        actual_start = row["actual_start"]
        if new_status in ("in_progress", "done") and not actual_start:
            actual_start = today.isoformat()
        actual_end = today.isoformat() if new_status == "done" else None
        if new_status == "done":
            percent = 100.0
        conn.execute(
            "UPDATE tasks SET status = ?,"
            " percent_complete = COALESCE(?, percent_complete),"
            " actual_start = COALESCE(?, actual_start),"
            " actual_end = COALESCE(?, actual_end)"
            " WHERE task_id = ?",
            (new_status, percent, actual_start, actual_end, row["task_id"]),
        )
        updated += 1

    conn.commit()
    return {"processed": len(rows), "updated": updated, "ambiguous": ambiguous}


def breach_thresholds(
    snap: evm.EvmSnapshot, threshold_hours: float
) -> dict[str, float]:
    """Deterministic threshold check: negative variance beyond the threshold
    (behind schedule / over cost) breaches. Positive variances never do."""
    breaches = {}
    if snap.schedule_variance < -threshold_hours:
        breaches["schedule_variance"] = snap.schedule_variance
    if snap.cost_variance < -threshold_hours:
        breaches["cost_variance"] = snap.cost_variance
    return breaches


def _severity_for(magnitude_hours: float, threshold_hours: float) -> int:
    ratio = magnitude_hours / threshold_hours if threshold_hours else 5
    return 5 if ratio >= 3 else 4 if ratio >= 2 else 3


def _upsert_rule_risk(
    conn: sqlite3.Connection, project_id: int, title: str, description: str,
    severity: int,
) -> tuple[int, bool]:
    """Create or update the corresponding risks_issues entry (PRD 8.4 step 8).
    Rule risks carry stable titles, so the update path is an exact match."""
    row = conn.execute(
        "SELECT risk_id FROM risks_issues WHERE project_id = ? AND title = ?"
        " AND status = 'open' AND source = 'rule_based'",
        (project_id, title),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE risks_issues SET description = ?, severity = ?,"
            " updated_at = datetime('now') WHERE risk_id = ?",
            (description, severity, row["risk_id"]),
        )
        return row["risk_id"], False
    cur = conn.execute(
        "INSERT INTO risks_issues (project_id, kind, title, description, severity,"
        " likelihood, source) VALUES (?, 'issue', ?, ?, ?, 5, 'rule_based')",
        (project_id, title, description, severity),
    )
    return cur.lastrowid, True


def run_cycle(
    conn: sqlite3.Connection,
    project_id: int,
    today: date,
    sonnet: SonnetClient | None = None,
) -> dict:
    """One reporting-cadence cycle: parse inbox -> EVM -> thresholds -> alerts."""
    inbox = process_inbox(conn, project_id, today, sonnet)

    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))
    snap = evm.snapshot(conn, project_id, today, calendar)
    threshold_hours = (
        float(config_loader.resolve(conn, project_id, "slip_threshold_days"))
        * calendar.hours_per_day
    )
    breaches = breach_thresholds(snap, threshold_hours)

    for name, value in breaches.items():
        pretty = name.replace("_", " ")
        risk_id, created = _upsert_rule_risk(
            conn, project_id,
            title=f"EVM breach: {pretty}",
            description=(
                f"{pretty} is {value:+.1f}h against a threshold of"
                f" -{threshold_hours:.1f}h (PV={snap.planned_value:.1f},"
                f" EV={snap.earned_value:.1f}, AC={snap.actual_cost:.1f})"
            ),
            severity=_severity_for(abs(value), threshold_hours),
        )
        raise_review_item(
            conn, project_id, "off_track_alert",
            {"metric": name, "value_hours": round(value, 2),
             "threshold_hours": threshold_hours, "risk_id": risk_id,
             "risk_created": created,
             "pv": snap.planned_value, "ev": snap.earned_value,
             "ac": snap.actual_cost},
            created_by_skill="status_tracking",
        )

    audit.log_action(
        conn, skill="status_tracking", action="run_cycle",
        input_summary={"as_of": today.isoformat(), **inbox},
        output_summary={
            "pv": snap.planned_value, "ev": snap.earned_value, "ac": snap.actual_cost,
            "sv": round(snap.schedule_variance, 2), "cv": round(snap.cost_variance, 2),
            "breaches": sorted(breaches),
        },
        project_id=project_id,
    )
    conn.commit()
    return {"inbox": inbox, "evm": snap, "breaches": breaches}

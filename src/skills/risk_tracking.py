"""Skill 8.5 — Risk & Issue Tracking. Hybrid: rule triggers + Sonnet 5 scan.

Two independent detection paths feed one register, with a duplicate check
before anything new is inserted (PRD 8.5):

1. Rule pass (no LLM): EVM variance breaches and capacity over-allocation
   flagged by the Assignment Engine. Rule candidates carry stable titles, so
   their duplicate check is an exact title match — fully deterministic.
2. Pattern pass (Sonnet 5): recent meeting notes and status free-text scanned
   for emerging risks the rules can't see. Pattern candidates are checked
   against every open risk via a Sonnet duplicate check.

Scores are severity x likelihood (1-5 each): rule-assigned for rule
candidates, Sonnet-suggested for pattern candidates — always
reviewer-adjustable. Every insert raises a Tier 1 risk_alert.
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
from src.llm.sonnet_client import LLMRefusalError, LLMValidationError, SonnetClient
from src.skills.status_tracking import _severity_for, breach_thresholds

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"

PATTERN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "description", "severity", "likelihood", "kind"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "severity": {"type": "integer"},
                    "likelihood": {"type": "integer"},
                    "kind": {"enum": ["risk", "issue"]},
                },
            },
        },
    },
}

DUPLICATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["is_duplicate", "duplicate_of_risk_id"],
    "properties": {
        "is_duplicate": {"type": "boolean"},
        "duplicate_of_risk_id": {"type": ["integer", "null"]},
    },
}


def _clamp_score(value: int) -> int:
    """Schema-level min/max isn't supported by structured outputs; clamp
    deterministically (reviewer-adjustable anyway)."""
    return max(1, min(5, int(value)))


def _open_risks(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT risk_id, title, description FROM risks_issues"
        " WHERE project_id = ? AND status = 'open'",
        (project_id,),
    ).fetchall()


def _rule_candidates(
    conn: sqlite3.Connection, project_id: int, today: date, calendar: WorkingCalendar
) -> list[dict]:
    candidates = []
    snap = evm.snapshot(conn, project_id, today, calendar)
    threshold_hours = (
        float(config_loader.resolve(conn, project_id, "slip_threshold_days"))
        * calendar.hours_per_day
    )
    for name, value in breach_thresholds(snap, threshold_hours).items():
        pretty = name.replace("_", " ")
        candidates.append({
            "title": f"EVM breach: {pretty}",
            "description": f"{pretty} is {value:+.1f}h against a threshold of"
                           f" -{threshold_hours:.1f}h",
            "severity": _severity_for(abs(value), threshold_hours),
            "likelihood": 5,
            "kind": "issue",
        })

    unassignable = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE project_id = ? AND unassignable = 1"
        " AND status NOT IN ('done','cancelled')",
        (project_id,),
    ).fetchone()["n"]
    if unassignable:
        candidates.append({
            "title": "Capacity over-allocation: unassignable tasks",
            "description": f"{unassignable} open task(s) could not be assigned within"
                           " anyone's remaining weekly capacity",
            "severity": 4 if unassignable > 2 else 3,
            "likelihood": 5,
            "kind": "issue",
        })
    return candidates


def _pattern_candidates(
    conn: sqlite3.Connection, project_id: int, sonnet: SonnetClient,
    open_risks: list[sqlite3.Row],
) -> list[dict]:
    meetings = conn.execute(
        "SELECT raw_transcript FROM meetings WHERE project_id = ?"
        " ORDER BY meeting_id DESC LIMIT 3",
        (project_id,),
    ).fetchall()
    reports = conn.execute(
        "SELECT r.raw_text FROM status_reports r JOIN tasks t ON t.task_id = r.task_id"
        " WHERE t.project_id = ? ORDER BY r.report_id DESC LIMIT 20",
        (project_id,),
    ).fetchall()
    if not meetings and not reports:
        return []

    open_list = "\n".join(f"- [{r['risk_id']}] {r['title']}" for r in open_risks) or "none"
    body = (
        f"ALREADY-OPEN RISKS (do not re-flag):\n{open_list}\n\n"
        "RECENT MEETING NOTES:\n"
        + ("\n---\n".join(m["raw_transcript"] for m in meetings) or "none")
        + "\n\nRECENT STATUS REPLIES:\n"
        + ("\n".join(r["raw_text"] for r in reports) or "none")
    )
    system = (_PROMPTS / "risk_pattern_scan.md").read_text(encoding="utf-8")
    return sonnet.structured(system, body, PATTERN_SCHEMA)["candidates"]


def _is_duplicate(
    candidate: dict, open_risks: list[sqlite3.Row], sonnet: SonnetClient,
    rule_based: bool,
) -> bool:
    """PRD 8.5 step 3. Exact-title match first (covers stable rule titles
    deterministically); Sonnet judgment for everything else."""
    titles = {r["title"] for r in open_risks}
    if candidate["title"] in titles:
        return True
    if rule_based or not open_risks:
        return False
    system = (_PROMPTS / "risk_duplicate_check.md").read_text(encoding="utf-8")
    body = (
        f"CANDIDATE:\n{json.dumps(candidate, indent=2)}\n\nOPEN RISKS:\n"
        + "\n".join(
            f"- id={r['risk_id']}: {r['title']} — {r['description'] or ''}"
            for r in open_risks
        )
    )
    try:
        verdict = sonnet.structured(system, body, DUPLICATE_SCHEMA)
    except (LLMValidationError, LLMRefusalError):
        return False  # inserting a possible duplicate beats dropping a real risk
    return bool(verdict["is_duplicate"])


def adjust_score(
    conn: sqlite3.Connection, risk_id: int, severity: int, likelihood: int,
    by_user: int,
) -> dict:
    """Reviewer adjustment of a risk's scores (PRD 8.5 step 4: 'always
    reviewer-adjustable'). Approved OQ-6: a real human actor is recorded in
    audit_log; this is an action taken while reviewing an existing Tier 1
    item, NOT a new tiered decision — no review item is raised."""
    if not (1 <= int(severity) <= 5 and 1 <= int(likelihood) <= 5):
        raise ValueError("severity and likelihood must be integers 1-5")
    row = conn.execute(
        "SELECT project_id, severity, likelihood FROM risks_issues WHERE risk_id = ?",
        (risk_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"risk {risk_id} does not exist")
    conn.execute(
        "UPDATE risks_issues SET severity = ?, likelihood = ?,"
        " updated_at = datetime('now') WHERE risk_id = ?",
        (int(severity), int(likelihood), risk_id),
    )
    audit.log_action(
        conn, skill="risk_tracking", action="adjust_score",
        input_summary={"risk_id": risk_id,
                       "from": [row["severity"], row["likelihood"]],
                       "to": [int(severity), int(likelihood)]},
        actor=str(by_user),
        project_id=row["project_id"],
    )
    conn.commit()
    return {"risk_id": risk_id, "severity": int(severity),
            "likelihood": int(likelihood), "score": int(severity) * int(likelihood)}


def run_cycle(
    conn: sqlite3.Connection,
    project_id: int,
    today: date,
    sonnet: SonnetClient | None = None,
) -> dict:
    sonnet = sonnet or SonnetClient()
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))

    rule = _rule_candidates(conn, project_id, today, calendar)
    open_risks = _open_risks(conn, project_id)
    try:
        pattern = _pattern_candidates(conn, project_id, sonnet, open_risks)
    except (LLMValidationError, LLMRefusalError) as err:
        pattern = []
        raise_review_item(
            conn, project_id, "clarification",
            {"reason": f"risk pattern scan failed validation: {err}"},
            created_by_skill="risk_tracking",
        )

    inserted = []
    skipped_duplicates = 0
    for candidate, source in (
        [(c, "rule_based") for c in rule] + [(c, "pattern_detected") for c in pattern]
    ):
        if _is_duplicate(candidate, open_risks, sonnet, source == "rule_based"):
            skipped_duplicates += 1
            continue
        cur = conn.execute(
            "INSERT INTO risks_issues (project_id, kind, title, description,"
            " severity, likelihood, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, candidate["kind"], candidate["title"],
             candidate["description"], _clamp_score(candidate["severity"]),
             _clamp_score(candidate["likelihood"]), source),
        )
        risk_id = cur.lastrowid
        inserted.append(risk_id)
        raise_review_item(
            conn, project_id, "risk_alert",
            {"risk_id": risk_id, "title": candidate["title"], "source": source,
             "severity": _clamp_score(candidate["severity"]),
             "likelihood": _clamp_score(candidate["likelihood"]),
             "note": "scores are reviewer-adjustable"},
            created_by_skill="risk_tracking",
        )
        open_risks = _open_risks(conn, project_id)  # later candidates see it

    audit.log_action(
        conn, skill="risk_tracking", action="run_cycle",
        input_summary={"as_of": today.isoformat(), "rule_candidates": len(rule),
                       "pattern_candidates": len(pattern)},
        output_summary={"inserted": len(inserted),
                        "skipped_duplicates": skipped_duplicates},
        project_id=project_id,
    )
    conn.commit()
    return {"inserted": inserted, "skipped_duplicates": skipped_duplicates,
            "rule_candidates": len(rule), "pattern_candidates": len(pattern)}

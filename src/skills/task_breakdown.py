"""Skill 8.1 — Task Breakdown. LLM reasoning (Claude Sonnet 5).

Strictly two passes (PRD section 6): project -> phases first (validated and
written), then each phase -> its own detailed tasks. Never generates tasks
directly from the raw scope document.

Failure discipline: a validation failure or refusal from the model HALTS the
run and surfaces to the reviewer as a Tier 1 clarification item (PRD 8.1 step
4) — nothing is silently patched. Ambiguity comes back as needs_clarification
flags, each of which also raises a Tier 1 item.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date
from pathlib import Path

from src import config_loader
from src.governance.review_queue import raise_review_item
from src.lib import audit
from src.lib.calendar import WorkingCalendar
from src.llm.sonnet_client import LLMRefusalError, LLMValidationError, SonnetClient
from src.skills import scheduler

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"

PHASES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phases", "clarifications"],
    "properties": {
        "phases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "description", "planned_start", "planned_end",
                    "needs_clarification",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "planned_start": {"type": "string", "format": "date"},
                    "planned_end": {"type": "string", "format": "date"},
                    "needs_clarification": {"type": ["string", "null"]},
                },
            },
        },
        "clarifications": {"type": "array", "items": {"type": "string"}},
    },
}

TASKS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title", "description", "effort_hours", "skill_tags",
                    "depends_on", "needs_clarification",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "effort_hours": {"type": "number"},
                    "skill_tags": {"type": "array", "items": {"type": "string"}},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "needs_clarification": {"type": ["string", "null"]},
                },
            },
        },
    },
}


class TaskBreakdownHalted(Exception):
    """Run halted and surfaced to the reviewer — do not proceed downstream."""


def _halt(conn, project_id, reason: str) -> None:
    raise_review_item(
        conn, project_id, "clarification",
        {"reason": reason}, created_by_skill="task_breakdown",
    )
    audit.log_action(
        conn, skill="task_breakdown", action="halted",
        input_summary={"reason": reason}, project_id=project_id,
    )
    conn.commit()
    raise TaskBreakdownHalted(reason)


def run(conn: sqlite3.Connection, project_id: int, sonnet: SonnetClient | None = None) -> dict:
    sonnet = sonnet or SonnetClient()
    project = conn.execute(
        "SELECT name, scope_summary, scope_document, budget_total,"
        " timeline_start, timeline_end FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if project is None:
        raise ValueError(f"project {project_id} does not exist")

    scope = project["scope_document"] or project["scope_summary"]
    if not scope:
        _halt(conn, project_id, "no scope document or scope summary on the project")
    if not project["timeline_start"] or not project["timeline_end"]:
        _halt(conn, project_id, "project has no timeline; cannot plan phases")

    project_definition = config_loader.resolve(conn, project_id, "project_definition")
    calendar = WorkingCalendar(config_loader.resolve(conn, project_id, "working_calendar"))

    # ---- Pass 1: scope -> phases only (PRD 8.1 steps 2-5) -------------------
    phases_prompt = (_PROMPTS / "task_breakdown_phases.md").read_text(encoding="utf-8")
    user_content = (
        f"Project: {project['name']}\n"
        f"Timeline: {project['timeline_start']} to {project['timeline_end']}\n"
        f"Budget: {project['budget_total']}\n"
        f"Client's definition of a project: {project_definition or 'not specified'}\n\n"
        f"SCOPE DOCUMENT:\n{scope}"
    )
    try:
        phase_output = sonnet.structured(phases_prompt, user_content, PHASES_SCHEMA)
    except (LLMValidationError, LLMRefusalError) as err:
        _halt(conn, project_id, f"phase decomposition failed validation: {err}")

    phases = phase_output["phases"]
    if not phases:
        _halt(conn, project_id, "model returned zero phases for a non-empty scope")
    for p in phases:
        if p["planned_end"] < p["planned_start"]:
            _halt(conn, project_id, f"phase '{p['name']}' has an inverted date range")

    clarifications = list(phase_output["clarifications"])
    phase_ids: list[int] = []
    for order, p in enumerate(phases, start=1):
        cur = conn.execute(
            "INSERT INTO phases (project_id, name, description, planned_start,"
            " planned_end, sequence_order, needs_clarification)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, p["name"], p["description"], p["planned_start"],
             p["planned_end"], order, p["needs_clarification"]),
        )
        phase_ids.append(cur.lastrowid)
        if p["needs_clarification"]:
            clarifications.append(f"phase '{p['name']}': {p['needs_clarification']}")

    # ---- Pass 2: each phase -> detailed tasks (PRD 8.1 steps 6-9) -----------
    tasks_prompt = (_PROMPTS / "task_breakdown_tasks.md").read_text(encoding="utf-8")
    roster_skills = sorted({
        tag
        for row in conn.execute("SELECT skill_tags FROM team_members WHERE is_active = 1")
        for tag in json.loads(row["skill_tags"])
    })
    active_members = conn.execute(
        "SELECT COUNT(*) AS n FROM team_members WHERE is_active = 1"
    ).fetchone()["n"]

    title_to_id: dict[str, int] = {}
    dependency_rows: list[tuple[int, str]] = []  # (successor_id, predecessor_title)
    task_count = 0
    for p, phase_id in zip(phases, phase_ids, strict=True):
        phase_user = (
            f"Phase: {p['name']}\nDescription: {p['description']}\n"
            f"Date range: {p['planned_start']} to {p['planned_end']}\n"
            f"Available roster skills: {', '.join(roster_skills) or 'unknown'}\n"
            f"Task titles from earlier phases: {', '.join(title_to_id) or 'none'}\n\n"
            f"FULL SCOPE (for context):\n{scope}"
        )
        try:
            task_output = sonnet.structured(tasks_prompt, phase_user, TASKS_SCHEMA)
        except (LLMValidationError, LLMRefusalError) as err:
            _halt(conn, project_id, f"task decomposition for phase '{p['name']}' failed: {err}")

        # Capacity pre-check (PRD 8.1 step 7): effort vs the phase window under
        # the working calendar, across the active roster.
        total_effort = sum(t["effort_hours"] for t in task_output["tasks"])
        window_days = calendar.count_working_days(
            date.fromisoformat(p["planned_start"]), date.fromisoformat(p["planned_end"])
        )
        phase_capacity = window_days * calendar.hours_per_day * max(1, active_members)
        if total_effort > phase_capacity:
            clarifications.append(
                f"phase '{p['name']}' is over capacity before starting:"
                f" {total_effort}h of tasks vs {phase_capacity}h available"
                f" ({window_days} working days x {calendar.hours_per_day}h"
                f" x {max(1, active_members)} active members)"
            )

        for t in task_output["tasks"]:
            cur = conn.execute(
                "INSERT INTO tasks (phase_id, project_id, title, description,"
                " effort_hours, skill_tags, needs_clarification)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (phase_id, project_id, t["title"], t["description"],
                 t["effort_hours"], json.dumps(t["skill_tags"]),
                 t["needs_clarification"]),
            )
            title_to_id[t["title"]] = cur.lastrowid
            task_count += 1
            if t["needs_clarification"]:
                clarifications.append(f"task '{t['title']}': {t['needs_clarification']}")
            for dep_title in t["depends_on"]:
                dependency_rows.append((cur.lastrowid, dep_title))

    dep_count = 0
    for successor_id, dep_title in dependency_rows:
        pred_id = title_to_id.get(dep_title)
        if pred_id is None or pred_id == successor_id:
            clarifications.append(
                f"dependency on unknown task title '{dep_title}' — not recorded"
            )
            continue
        conn.execute(
            "INSERT OR IGNORE INTO task_dependencies VALUES (?, ?)", (pred_id, successor_id)
        )
        dep_count += 1

    for note in clarifications:
        raise_review_item(
            conn, project_id, "clarification", {"reason": note},
            created_by_skill="task_breakdown",
        )
    conn.commit()

    # ---- Hand off to the Scheduler (PRD 8.1 step 10) ------------------------
    scheduler.schedule_project(conn, project_id)

    audit.log_action(
        conn, skill="task_breakdown", action="breakdown",
        input_summary={"scope_chars": len(scope)},
        output_summary={
            "phases": len(phases), "tasks": task_count,
            "dependencies": dep_count, "clarifications": len(clarifications),
        },
        project_id=project_id,
    )
    conn.commit()
    return {
        "phases": len(phases),
        "tasks": task_count,
        "dependencies": dep_count,
        "clarifications": clarifications,
    }


def estimate_duration_days(effort_hours: float, hours_per_day: float) -> int:
    return max(1, math.ceil(effort_hours / hours_per_day))

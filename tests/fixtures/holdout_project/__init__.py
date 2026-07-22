"""Holdout sample project (PRD section 15: LLM skills are evaluated against a
held-out project not used during development).

Discipline: the prompts in /prompts were written and frozen BEFORE this
fixture was used in any eval run. Do not iterate on prompts while looking at
eval output from this fixture and then report the same fixture's score as
held-out — that converts it into a dev set. If prompt iteration against this
data ever happens, say so in the eval report and build a fresh holdout.

Shape is deliberately different from the Phase 1 known-answer fixture:
different domain (field service vs generic build/test), more phases expected,
5 team members instead of 3, and planted ambiguity (unknown ERP, unresolved
offline-conflict policy, an explicitly ownerless blocker).
"""

import json
from pathlib import Path

from src import config_loader

HERE = Path(__file__).resolve().parent
CLIENT_ID = 1
PROJECT_ID = 50

SCOPE_DOCUMENT = (HERE / "scope_document.md").read_text(encoding="utf-8")
TRANSCRIPT_KICKOFF = (HERE / "transcript_kickoff.md").read_text(encoding="utf-8")

CONFIG = {
    "about_client": "Meridian Facilities Group — field service operations.",
    "project_definition": "Each project is a discrete delivery engagement with its"
                          " own budget, timeline, and sign-off.",
    "reporting_cadence": "weekly",
    "comms_cadence": "biweekly",
    "skill_depth": {
        "task_breakdown": "assisted",
        "scheduler": "autonomous",
        "assignment_engine": "autonomous",
        "status_tracking": "assisted",
        "risk_tracking": "assisted",
        "dependency_manager": "autonomous",
        "meeting_summary": "assisted",
        "stakeholder_comms": "assisted",
    },
    "tools_channels": None,
    "primary_reviewer_id": 1,
    "backup_reviewer_id": None,
    "escalation_delay_hours": 24,
    "escalation_delay_by_tier": None,
    "change_approver_id": 1,
    "signoff_approver_id": 1,
    "voice_style": "Plain, direct, no marketing language.",
    "working_calendar": {"workdays": [1, 2, 3, 4, 5], "holidays": [], "hours_per_day": 8},
    "assignment_strategy": "best_skill_match",
    "slip_threshold_days": 2,
}

ROSTER = [
    (1, "Dana", "pm", ["planning", "requirements"]),
    (2, "Rob", "backend", ["backend", "integration"]),
    (3, "Yuki", "mobile", ["mobile", "backend"]),
    (4, "Sofia", "design", ["design", "frontend"]),
    (5, "Tom", "qa", ["qa"]),
]


def build(conn):
    conn.execute("INSERT INTO clients (client_id, name) VALUES (?, 'Meridian')", (CLIENT_ID,))
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, ?, 'admin@meridian.test', 'Admin', 'client_admin', 'active')",
        (CLIENT_ID,),
    )
    config_loader.save_client_config(conn, CLIENT_ID, CONFIG)
    for member_id, name, role, skills in ROSTER:
        conn.execute(
            "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
            " VALUES (?, ?, ?, ?, ?)",
            (member_id, CLIENT_ID, name, role, json.dumps(skills)),
        )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, scope_document,"
        " budget_total, timeline_start, timeline_end)"
        " VALUES (?, ?, 'Meridian Field Service App', ?, 180000,"
        " '2026-09-07', '2026-12-18')",
        (PROJECT_ID, CLIENT_ID, SCOPE_DOCUMENT),
    )
    conn.commit()

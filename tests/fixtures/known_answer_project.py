"""Hand-built known-answer dataset (PRD section 15: deterministic skills are
verified against a hand-verified test dataset with a known answer).

Every expected value below was computed BY HAND before any skill code ran.

Calendar: Mon-Fri, 8 h/day, one holiday Fri 2026-08-14.
Project 10 timeline: Mon 2026-08-03 .. Thu 2026-08-27.
Working-day axis (index: date):
   1:Aug03  2:Aug04  3:Aug05  4:Aug06  5:Aug07
   6:Aug10  7:Aug11  8:Aug12  9:Aug13  (Aug14 holiday)
  10:Aug17 11:Aug18 12:Aug19 13:Aug20 14:Aug21
  15:Aug24 16:Aug25 17:Aug26 18:Aug27

Phase 1 "Build"  Aug03..Aug14 (seq 1): T1..T4
Phase 2 "Test"   Aug10..Aug27 (seq 2): T5..T10

Tasks (effort -> duration at 8 h/day) and dependencies:
  T1 16h/2d  -            T6  8h/1d  T4
  T2 24h/3d  T1           T7 40h/5d  T5
  T3  8h/1d  T1           T8 16h/2d  T6
  T4 16h/2d  T2,T3        T9 16h/2d  T7,T8
  T5 24h/3d  T4           T10 8h/1d  T9

Hand CPM (indexes): critical chain T1(1-2) T2(3-5) T4(6-7) T5(8-10) T7(11-15)
T9(16-17) T10(18) = 18 working days = exactly the timeline -> slack 0.
T3: ES3 EF3, LF5 -> slack 2.  T6: ES8 EF8, LF13 -> slack 5.
T8: ES9 EF10, LF15 -> slack 5.

Assignment (best_skill_match; members M1 [backend], M2 [backend, frontend],
M3 [qa], all capacity 40 h/week; tie-breaks per assignment_engine docstring),
hand-walked in assignment order T1,T2,T4,T5,T7,T9,T10,T3,T6,T8:
  T1->M1  T2->M2 (skill tie, M1 already carries 16h wk1)  T4->M1
  T5->M3  T7->M3 (wk Aug17: 8+32 = 40, fits exactly)      T9->M1
  T10->M2 (M1 already carries T9's 16h that week)
  T3->M2  T6->M2  T8->M2  (only frontend member)
Week of Aug10 has the holiday -> effective capacity 32 h; no one exceeds it.

Slip scenario (dependency manager): T5 actual_end Aug19 (planned Aug17,
slip = 2 working days). Descendants T7, T9, T10 reschedule to:
  T7 Aug20..Aug26, T9 Aug27..Aug28, T10 Aug31.
Project finish Aug27 -> Aug31 = 2 working days late; threshold 1 -> breach
(slip_impact raised) and the re-run finish exceeds the timeline
(infeasible_plan raised).
"""

import json

from src import config_loader

CLIENT_ID = 1
PROJECT_ID = 10
M1, M2, M3 = 1, 2, 3

CONFIG = {
    "about_client": "Fixture client",
    "project_definition": None,
    "reporting_cadence": "weekly",
    "comms_cadence": None,
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
    "voice_style": None,
    "working_calendar": {
        "workdays": [1, 2, 3, 4, 5],
        "holidays": ["2026-08-14"],
        "hours_per_day": 8,
    },
    "assignment_strategy": "best_skill_match",
    "slip_threshold_days": 1,
}

# (task_id, phase_id, title, effort_hours, skill_tags)
TASKS = [
    (1, 1, "T1", 16, ["backend"]),
    (2, 1, "T2", 24, ["backend"]),
    (3, 1, "T3", 8, ["frontend"]),
    (4, 1, "T4", 16, ["backend"]),
    (5, 2, "T5", 24, ["qa"]),
    (6, 2, "T6", 8, ["frontend"]),
    (7, 2, "T7", 40, ["qa"]),
    (8, 2, "T8", 16, ["frontend"]),
    (9, 2, "T9", 16, ["backend"]),
    (10, 2, "T10", 8, ["backend"]),
]

DEPENDENCIES = [
    (1, 2), (1, 3), (2, 4), (3, 4),
    (4, 5), (4, 6), (5, 7), (6, 8), (7, 9), (8, 9), (9, 10),
]

# task_id -> (planned_start, planned_end, slack_days, on_critical_path)
EXPECTED_SCHEDULE = {
    1: ("2026-08-03", "2026-08-04", 0, True),
    2: ("2026-08-05", "2026-08-07", 0, True),
    3: ("2026-08-05", "2026-08-05", 2, False),
    4: ("2026-08-10", "2026-08-11", 0, True),
    5: ("2026-08-12", "2026-08-17", 0, True),
    6: ("2026-08-12", "2026-08-12", 5, False),
    7: ("2026-08-18", "2026-08-24", 0, True),
    8: ("2026-08-13", "2026-08-17", 5, False),
    9: ("2026-08-25", "2026-08-26", 0, True),
    10: ("2026-08-27", "2026-08-27", 0, True),
}

EXPECTED_OWNERS = {1: M1, 2: M2, 3: M2, 4: M1, 5: M3, 6: M2, 7: M3, 8: M2, 9: M1, 10: M2}

# After the T5 slip (actual_end 2026-08-19), hand-computed downstream dates:
EXPECTED_AFTER_SLIP = {
    7: ("2026-08-20", "2026-08-26"),
    9: ("2026-08-27", "2026-08-28"),
    10: ("2026-08-31", "2026-08-31"),
}
EXPECTED_SLIP_DAYS = 2
EXPECTED_PROJECT_END_SHIFT = 2  # Aug27 -> Aug31, working days


def build(conn):
    """Create the fixture world: client, admin user, config, roster, project,
    phases, tasks, dependencies. Tasks start undated (Scheduler's job)."""
    conn.execute("INSERT INTO clients (client_id, name) VALUES (?, 'Fixture Co')", (CLIENT_ID,))
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, ?, 'admin@fixture.test', 'Admin', 'client_admin', 'active')",
        (CLIENT_ID,),
    )
    config_loader.save_client_config(conn, CLIENT_ID, CONFIG)

    for member_id, name, skills in [
        (M1, "Dev A", ["backend"]),
        (M2, "Dev B", ["backend", "frontend"]),
        (M3, "QA", ["qa"]),
    ]:
        conn.execute(
            "INSERT INTO team_members (member_id, client_id, name, role, skill_tags,"
            " capacity_hrs) VALUES (?, ?, ?, 'engineer', ?, 40)",
            (member_id, CLIENT_ID, name, json.dumps(skills)),
        )

    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
        " VALUES (?, ?, 'Known Answer', '2026-08-03', '2026-08-27')",
        (PROJECT_ID, CLIENT_ID),
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order)"
        " VALUES (1, ?, 'Build', 'build phase', '2026-08-03', '2026-08-14', 1)",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order)"
        " VALUES (2, ?, 'Test', 'test phase', '2026-08-10', '2026-08-27', 2)",
        (PROJECT_ID,),
    )
    for task_id, phase_id, title, effort, skills in TASKS:
        conn.execute(
            "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
            " skill_tags) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, phase_id, PROJECT_ID, title, effort, json.dumps(skills)),
        )
    conn.executemany("INSERT INTO task_dependencies VALUES (?, ?)", DEPENDENCIES)
    conn.commit()

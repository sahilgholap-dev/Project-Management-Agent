"""Status Tracking (8.4): (a) EVM pure-function math against hand-computed
values, (b) inbox parse flow with a stubbed model, (c) threshold cycle."""

import json
from datetime import date

import pytest

from src import config_loader
from src.lib import evm
from src.lib.calendar import WorkingCalendar
from src.llm.sonnet_client import LLMValidationError
from src.skills import status_tracking
from tests.fakes import FakeSonnet
from tests.fixtures.known_answer_project import CONFIG as KA_CONFIG

PROJECT_ID = 10

# no holidays; slip threshold 1 day = 8h
CONFIG = dict(
    KA_CONFIG,
    working_calendar={"workdays": [1, 2, 3, 4, 5], "holidays": [], "hours_per_day": 8},
)
CAL = WorkingCalendar(CONFIG["working_calendar"])


@pytest.fixture
def world(conn):
    """Hand-computed EVM world. T1 40h Aug 3-7 done; T2 40h Aug 10-14 at 25%,
    reported hours: T1 45h, T2 12h.
    As of Mon Aug 10: PV = 40 + 40*(1/5) = 48; EV = 40 + 10 = 50; AC = 57;
    SV = +2; CV = -7 (inside the 8h threshold)."""
    conn.execute("INSERT INTO clients (client_id, name) VALUES (1, 'C')")
    conn.execute(
        "INSERT INTO users (user_id, client_id, email, display_name, role, invite_status)"
        " VALUES (1, 1, 'a@c.test', 'Admin', 'client_admin', 'active')"
    )
    config_loader.save_client_config(conn, 1, CONFIG)
    conn.execute(
        "INSERT INTO team_members (member_id, client_id, name, role, skill_tags)"
        " VALUES (1, 1, 'Dev', 'dev', '[]')"
    )
    conn.execute(
        "INSERT INTO projects (project_id, client_id, name, timeline_start, timeline_end)"
        " VALUES (?, 1, 'P', '2026-08-03', '2026-08-14')",
        (PROJECT_ID,),
    )
    conn.execute(
        "INSERT INTO phases (phase_id, project_id, name, description, planned_start,"
        " planned_end, sequence_order)"
        " VALUES (1, ?, 'Ph', 'd', '2026-08-03', '2026-08-14', 1)",
        (PROJECT_ID,),
    )
    conn.executemany(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours,"
        " owner_id, planned_start, planned_end, status, percent_complete)"
        " VALUES (?, 1, ?, ?, 40, 1, ?, ?, ?, ?)",
        [
            (1, PROJECT_ID, "T1", "2026-08-03", "2026-08-07", "done", 100),
            (2, PROJECT_ID, "T2", "2026-08-10", "2026-08-14", "in_progress", 25),
        ],
    )
    conn.executemany(
        "INSERT INTO status_reports (task_id, member_id, raw_text, parsed_hours_spent,"
        " processed_at) VALUES (?, 1, ?, ?, '2026-08-07')",
        [
            (1, "spent 41h", 41),   # superseded by the later 45h report
            (1, "spent 45h", 45),
            (2, "spent 12h", 12),
        ],
    )
    conn.commit()
    return conn


# --- (a) EVM math, hand-computed ---------------------------------------------

def test_evm_snapshot_matches_hand_computation(world):
    snap = evm.snapshot(world, PROJECT_ID, date(2026, 8, 10), CAL)
    assert snap.planned_value == pytest.approx(48)
    assert snap.earned_value == pytest.approx(50)
    assert snap.actual_cost == pytest.approx(57)  # latest report per task: 45 + 12
    assert snap.schedule_variance == pytest.approx(2)
    assert snap.cost_variance == pytest.approx(-7)


def test_pv_caps_at_full_effort_after_window(world):
    snap = evm.snapshot(world, PROJECT_ID, date(2026, 9, 1), CAL)
    assert snap.planned_value == pytest.approx(80)


def test_null_percent_counts_as_zero_and_null_effort_excluded(world):
    world.execute("UPDATE tasks SET percent_complete = NULL WHERE task_id = 2")
    world.execute(
        "INSERT INTO tasks (task_id, phase_id, project_id, title, effort_hours)"
        " VALUES (3, 1, ?, 'unestimated', NULL)",
        (PROJECT_ID,),
    )
    world.commit()
    snap = evm.snapshot(world, PROJECT_ID, date(2026, 8, 10), CAL)
    assert snap.earned_value == pytest.approx(40)  # T2 contributes 0, T3 excluded


def test_breach_thresholds_only_negative_beyond_threshold(world):
    snap = evm.EvmSnapshot(planned_value=64, earned_value=40, actual_cost=40)
    assert status_tracking.breach_thresholds(snap, 8) == {"schedule_variance": -24}
    snap = evm.EvmSnapshot(planned_value=48, earned_value=50, actual_cost=57)
    assert status_tracking.breach_thresholds(snap, 8) == {}  # +2 / -7 inside


# --- (b) inbox parse flow -----------------------------------------------------

def _report(world, task_id, text):
    world.execute(
        "INSERT INTO status_reports (task_id, member_id, raw_text) VALUES (?, 1, ?)",
        (task_id, text),
    )
    world.commit()


def test_clear_reply_updates_task_and_report(world):
    world.execute("UPDATE tasks SET status = 'todo', percent_complete = NULL,"
                  " actual_start = NULL WHERE task_id = 2")
    _report(world, 2, "about half done, 20h in so far")
    fake = FakeSonnet([{"status": "in_progress", "percent_complete": 50,
                        "hours_spent": 20, "is_ambiguous": False, "note": None}])
    result = status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 11), fake)
    assert result == {"processed": 1, "updated": 1, "ambiguous": 0}
    task = world.execute(
        "SELECT status, percent_complete, actual_start FROM tasks WHERE task_id = 2"
    ).fetchone()
    assert (task["status"], task["percent_complete"]) == ("in_progress", 50)
    assert task["actual_start"] == "2026-08-11"
    report = world.execute(
        "SELECT parsed_status, parsed_hours_spent, processed_at FROM status_reports"
        " WHERE processed_at = '2026-08-11'"
    ).fetchone()
    assert (report["parsed_status"], report["parsed_hours_spent"]) == ("in_progress", 20)


def test_done_reply_sets_actual_end_and_100_percent(world):
    world.execute("UPDATE tasks SET status = 'in_progress', percent_complete = 25,"
                  " actual_end = NULL WHERE task_id = 2")
    _report(world, 2, "shipped it this morning")
    fake = FakeSonnet([{"status": "done", "percent_complete": None,
                        "hours_spent": None, "is_ambiguous": False, "note": None}])
    status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 12), fake)
    task = world.execute(
        "SELECT status, percent_complete, actual_end FROM tasks WHERE task_id = 2"
    ).fetchone()
    assert (task["status"], task["percent_complete"], task["actual_end"]) == (
        "done", 100, "2026-08-12",
    )


def test_ambiguous_reply_flags_and_leaves_task_untouched(world):
    _report(world, 2, "ask Sam about that one")
    fake = FakeSonnet([{"status": None, "percent_complete": None,
                        "hours_spent": None, "is_ambiguous": True,
                        "note": "reply defers to someone else"}])
    result = status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 11), fake)
    assert result["ambiguous"] == 1 and result["updated"] == 0
    task = world.execute(
        "SELECT status, percent_complete FROM tasks WHERE task_id = 2"
    ).fetchone()
    assert (task["status"], task["percent_complete"]) == ("in_progress", 25)
    item = world.execute(
        "SELECT tier FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()
    assert item["tier"] == 1


def test_parse_failure_is_treated_as_ambiguous(world):
    _report(world, 2, "gibberish")
    fake = FakeSonnet([LLMValidationError("bad output")])
    result = status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 11), fake)
    assert result["ambiguous"] == 1


def test_inbox_rows_consumed_exactly_once(world):
    _report(world, 2, "halfway")
    fake = FakeSonnet([{"status": "in_progress", "percent_complete": 50,
                        "hours_spent": None, "is_ambiguous": False, "note": None}])
    status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 11), fake)
    again = status_tracking.process_inbox(world, PROJECT_ID, date(2026, 8, 12),
                                          FakeSonnet([]))
    assert again == {"processed": 0, "updated": 0, "ambiguous": 0}


# --- (c) threshold cycle ------------------------------------------------------

def _make_behind(world):
    """T2 at 0% as of Aug 12: PV = 40 + 40*(3/5) = 64, EV = 40, SV = -24 (breach);
    AC pinned to 40 so CV = 0 (no cost breach)."""
    world.execute("UPDATE tasks SET percent_complete = 0 WHERE task_id = 2")
    world.execute("UPDATE status_reports SET parsed_hours_spent = NULL"
                  " WHERE task_id = 2")
    world.execute("UPDATE status_reports SET parsed_hours_spent = 40"
                  " WHERE parsed_hours_spent = 45")
    world.commit()


def test_breach_raises_off_track_alert_and_rule_risk(world):
    _make_behind(world)
    result = status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12),
                                       FakeSonnet([]))
    assert set(result["breaches"]) == {"schedule_variance"}
    alert = world.execute(
        "SELECT tier, payload FROM review_queue WHERE item_type = 'off_track_alert'"
    ).fetchone()
    assert alert["tier"] == 1
    assert json.loads(alert["payload"])["value_hours"] == pytest.approx(-24)
    risk = world.execute(
        "SELECT title, source, status FROM risks_issues"
    ).fetchone()
    assert risk["source"] == "rule_based" and risk["status"] == "open"


def test_second_cycle_updates_risk_instead_of_duplicating(world):
    _make_behind(world)
    status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 12), FakeSonnet([]))
    status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 13), FakeSonnet([]))
    assert world.execute("SELECT COUNT(*) AS n FROM risks_issues").fetchone()["n"] == 1
    assert world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'off_track_alert'"
    ).fetchone()["n"] == 2  # alert each cycle, register entry updated in place


def test_unreported_hours_flag_themselves(world):
    """Review decision (Phase 3 review, item 3): a started task with no
    reported hours must raise its own flag — missing cost data never reads
    as a healthy CV."""
    world.execute("DELETE FROM status_reports WHERE task_id = 2")  # T2 started, no hours
    world.commit()
    result = status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 10),
                                       FakeSonnet([]))
    assert result["evm"].unreported_started_tasks == (2,)
    assert result["evm"].cost_data_complete is False
    item = world.execute(
        "SELECT tier, payload FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()
    assert item["tier"] == 1
    payload = json.loads(item["payload"])
    assert payload["cv_understated"] is True and payload["unreported_task_ids"] == [2]


def test_todo_tasks_do_not_count_as_unreported(world):
    world.execute("DELETE FROM status_reports WHERE task_id = 2")
    world.execute("UPDATE tasks SET status = 'todo', percent_complete = NULL"
                  " WHERE task_id = 2")
    world.commit()
    result = status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 10),
                                       FakeSonnet([]))
    assert result["evm"].cost_data_complete is True
    n = world.execute(
        "SELECT COUNT(*) AS n FROM review_queue WHERE item_type = 'clarification'"
    ).fetchone()["n"]
    assert n == 0


def test_healthy_cycle_raises_nothing(world):
    status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 10), FakeSonnet([]))
    assert world.execute("SELECT COUNT(*) AS n FROM review_queue").fetchone()["n"] == 0
    assert world.execute("SELECT COUNT(*) AS n FROM risks_issues").fetchone()["n"] == 0


def test_cycle_is_audit_logged(world):
    status_tracking.run_cycle(world, PROJECT_ID, date(2026, 8, 10), FakeSonnet([]))
    n = world.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE skill = 'status_tracking'"
    ).fetchone()["n"]
    assert n == 1

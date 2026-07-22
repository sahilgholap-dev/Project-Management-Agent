"""Silence-escalation ladder (PRD section 10).

Notify the primary reviewer -> if silent past the escalation delay, notify the
backup -> if the backup is silent too (or unset, PRD section 16), pause all
work on the project with a visible banner reason. The system NEVER
auto-approves a Tier 1/2/3 item under any configuration — silence only ever
moves an item UP the ladder, and the terminal state is a paused project, not
an approval.

"Notify" in v1 is an escalation_log row + audit entry (no channel
integrations, confirmed Q7/Q15); the reviewer works from the queue itself.

Delays resolve per item tier: escalation_delay_by_tier override first, then
escalation_delay_hours — each subject to project-level config overrides
(config_loader.resolve_escalation_delay_hours).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from src import config_loader
from src.lib import audit

_SQLITE_TS = "%Y-%m-%d %H:%M:%S"


def _utcnow() -> datetime:
    """Naive UTC, matching sqlite datetime('now') strings."""
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, _SQLITE_TS)


def _log_stage(
    conn: sqlite3.Connection, item_id: int, stage: str, reason: str,
    outcome: str | None = None, now: datetime | None = None,
) -> None:
    conn.execute(
        "INSERT INTO escalation_log (item_id, stage, reason, outcome, occurred_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (item_id, stage, reason, outcome,
         (now or _utcnow()).strftime(_SQLITE_TS)),
    )


def _stages(conn: sqlite3.Connection, item_id: int) -> dict[str, datetime]:
    return {
        r["stage"]: _parse_ts(r["occurred_at"])
        for r in conn.execute(
            "SELECT stage, MIN(occurred_at) AS occurred_at FROM escalation_log"
            " WHERE item_id = ? GROUP BY stage",
            (item_id,),
        )
    }


def _pause_project(
    conn: sqlite3.Connection, project_id: int, item_id: int, reason: str,
    now: datetime,
) -> None:
    conn.execute(
        "UPDATE projects SET status = 'paused', paused_reason = ?"
        " WHERE project_id = ? AND status != 'paused'",
        (reason, project_id),
    )
    conn.execute(
        "UPDATE review_queue SET status = 'paused' WHERE item_id = ?", (item_id,)
    )
    _log_stage(conn, item_id, "work_paused", reason,
               outcome="project paused; visible banner set", now=now)
    audit.log_action(
        conn, skill="governance", action="pause_project",
        input_summary={"item_id": item_id, "reason": reason},
        project_id=project_id,
    )


def check_escalations(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """Advance the ladder for every unresolved review item. Idempotent per
    stage; call on the orchestrator's cycle (and in tests with an explicit
    `now` to simulate elapsed time)."""
    now = now or _utcnow()
    items = conn.execute(
        "SELECT item_id, project_id, tier, item_type, created_at FROM review_queue"
        " WHERE status IN ('pending', 'escalated')"
        " ORDER BY item_id",
    ).fetchall()

    notified_primary, notified_backup, paused = [], [], []
    for item in items:
        item_id, project_id = item["item_id"], item["project_id"]
        try:
            delay_hours = config_loader.resolve_escalation_delay_hours(
                conn, project_id, item["tier"]
            )
            primary = config_loader.resolve(conn, project_id, "primary_reviewer_id")
            backup = config_loader.resolve(conn, project_id, "backup_reviewer_id")
        except config_loader.ConfigDefectError as err:
            # PRD s16: reviewer unresolvable at either level -> the ladder has
            # nowhere to go; pause rather than erroring or silently proceeding.
            _pause_project(
                conn, project_id, item_id,
                f"config defect blocks review of item {item_id}: {err}", now,
            )
            paused.append(item_id)
            continue

        stages = _stages(conn, item_id)
        delay = delay_hours * 3600

        if "primary_notified" not in stages:
            _log_stage(
                conn, item_id, "primary_notified",
                f"tier {item['tier']} {item['item_type']} awaiting review"
                f" (reviewer user {primary})", now=now,
            )
            notified_primary.append(item_id)
            continue

        if "backup_notified" not in stages:
            elapsed = (now - stages["primary_notified"]).total_seconds()
            if elapsed < delay:
                continue
            if backup is None:
                # PRD s16: backup also unset -> straight to paused-work.
                _pause_project(
                    conn, project_id, item_id,
                    f"reviewer silent for {delay_hours:g}h on item {item_id}"
                    " and no backup reviewer is configured", now,
                )
                paused.append(item_id)
                continue
            _log_stage(
                conn, item_id, "backup_notified",
                f"primary reviewer silent for {delay_hours:g}h"
                f" (backup user {backup})", now=now,
            )
            conn.execute(
                "UPDATE review_queue SET status = 'escalated' WHERE item_id = ?",
                (item_id,),
            )
            notified_backup.append(item_id)
            continue

        elapsed = (now - stages["backup_notified"]).total_seconds()
        if elapsed >= delay:
            _pause_project(
                conn, project_id, item_id,
                f"primary and backup reviewers both silent on item {item_id};"
                " all work on this project is paused until a human responds", now,
            )
            paused.append(item_id)

    conn.commit()
    return {
        "primary_notified": notified_primary,
        "backup_notified": notified_backup,
        "paused": paused,
    }


def resume_project(conn: sqlite3.Connection, project_id: int, by_user: int) -> bool:
    """Human-initiated resume after the paused items are resolved. Refuses
    while any paused-status item on the project is still unresolved."""
    unresolved = conn.execute(
        "SELECT COUNT(*) AS n FROM review_queue"
        " WHERE project_id = ? AND status = 'paused'",
        (project_id,),
    ).fetchone()["n"]
    if unresolved:
        return False
    conn.execute(
        "UPDATE projects SET status = 'active', paused_reason = NULL"
        " WHERE project_id = ? AND status = 'paused'",
        (project_id,),
    )
    audit.log_action(
        conn, skill="governance", action="resume_project",
        actor=str(by_user), project_id=project_id,
    )
    conn.commit()
    return True

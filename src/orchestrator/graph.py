"""LangGraph wiring for the PRD section 11 operating cycle.

Two graphs plus the close path (lifecycle.py):

ONBOARDING   (per project intake, section 11 steps 1-3):
    breakdown (-> phases -> tasks -> scheduler handoff) -> assign
    A halted breakdown (validation failure, missing scope) surfaces to the
    reviewer and ends the graph — nothing downstream runs on a bad plan.

MONITORING   (repeats on cadence, section 11 step 4-5):
    pause_gate -> status -> risk -> slips -> escalations [-> comms] -> END
    The pause gate honors the paused-work state (PRD section 10): a paused
    project runs NOTHING except the escalation check, which is what lets a
    late reviewer response eventually unblock it. The slips node enriches
    each new Tier 1 slip_impact item with a Sonnet plain-language summary —
    explanation only, the dates were decided by the Dependency Manager.

Conditional edges carry the tier-routing/threshold behavior: every skill
raises its own review items; the graph only decides what still gets to run.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import anthropic
from langgraph.graph import END, START, StateGraph

from src import config_loader
from src.governance import escalation
from src.governance.review_queue import annotate_item
from src.lib import audit
from src.llm.explainers import explain_slip
from src.llm.sonnet_client import LLMRefusalError, LLMValidationError, SonnetClient
from src.orchestrator.state import ProjectState
from src.skills import (
    assignment_engine,
    dependency_manager,
    risk_tracking,
    stakeholder_comms,
    status_tracking,
    task_breakdown,
)


def _today(state: ProjectState) -> date:
    return date.fromisoformat(state["today"])


_CADENCE_DAYS = {"daily": 1, "weekly": 7, "biweekly": 14}


def comms_due(conn: sqlite3.Connection, project_id: int, today: date) -> bool:
    """The comms_cadence gate (PRD 8.8 trigger): drafts run on the client's
    configured cadence — project overrides respected — not every monitoring
    cycle. No cadence configured means comms are ad-hoc only (a reviewer can
    still request a draft by passing draft_comms=True explicitly)."""
    cadence = config_loader.resolve(conn, project_id, "comms_cadence")
    if cadence is None:
        return False
    last = conn.execute(
        "SELECT MAX(created_at) AS last FROM review_queue"
        " WHERE project_id = ? AND item_type = 'comms_draft'",
        (project_id,),
    ).fetchone()["last"]
    if last is None:
        return True
    last_date = date.fromisoformat(last[:10])
    return (today - last_date).days >= _CADENCE_DAYS[cadence]


def build_onboarding_graph(conn: sqlite3.Connection, sonnet: SonnetClient | None = None):
    sonnet = sonnet or SonnetClient()

    def breakdown(state: ProjectState) -> dict:
        try:
            result = task_breakdown.run(conn, state["project_id"], sonnet=sonnet)
        except task_breakdown.TaskBreakdownHalted as err:
            return {"halted": True, "results": {"breakdown": {"halted": str(err)}}}
        return {"halted": False, "results": {"breakdown": result}}

    def assign(state: ProjectState) -> dict:
        outcomes = assignment_engine.assign_tasks(
            conn, state["project_id"], today=_today(state)
        )
        results = dict(state.get("results", {}))
        results["assignment"] = {
            "assigned": sum(1 for v in outcomes.values() if v),
            "unassignable": sum(1 for v in outcomes.values() if v is None),
        }
        return {"results": results}

    graph = StateGraph(ProjectState)
    graph.add_node("breakdown", breakdown)
    graph.add_node("assign", assign)
    graph.add_edge(START, "breakdown")
    graph.add_conditional_edges(
        "breakdown", lambda s: "halt" if s.get("halted") else "continue",
        {"halt": END, "continue": "assign"},
    )
    graph.add_edge("assign", END)
    return graph.compile()


def build_monitoring_graph(conn: sqlite3.Connection, sonnet: SonnetClient | None = None):
    sonnet = sonnet or SonnetClient()

    def pause_gate(state: ProjectState) -> dict:
        row = conn.execute(
            "SELECT status FROM projects WHERE project_id = ?", (state["project_id"],)
        ).fetchone()
        return {"paused": row is not None and row["status"] == "paused"}

    def status(state: ProjectState) -> dict:
        result = status_tracking.run_cycle(
            conn, state["project_id"], _today(state), sonnet
        )
        results = dict(state.get("results", {}))
        results["status"] = {"breaches": sorted(result["breaches"]),
                             **result["inbox"]}
        return {"results": results}

    def risk(state: ProjectState) -> dict:
        result = risk_tracking.run_cycle(conn, state["project_id"], _today(state), sonnet)
        results = dict(state.get("results", {}))
        results["risk"] = result
        return {"results": results}

    def slips(state: ProjectState) -> dict:
        slip_results = dependency_manager.detect_and_handle_slips(
            conn, state["project_id"]
        )
        # Enrich new slip_impact items with a plain-language summary — Sonnet
        # explains the diff, it never decides the dates (PRD 8.6 step 6).
        explained = 0
        for row in conn.execute(
            "SELECT item_id, payload FROM review_queue WHERE project_id = ?"
            " AND item_type = 'slip_impact' AND status IN ('pending','escalated')",
            (state["project_id"],),
        ).fetchall():
            payload = json.loads(row["payload"])
            if "explanation" in payload:
                continue
            try:
                explanation = explain_slip(payload, sonnet)
            except (LLMRefusalError, LLMValidationError, anthropic.APIError):
                # Enrichment is optional on top of a load-bearing item: the
                # slip_impact stands with its raw diff, NO second review item
                # is stacked on it, and the cycle continues — a transient
                # model hiccup must never block monitoring or duplicate the
                # reviewer's queue.
                continue
            annotate_item(conn, row["item_id"], "explanation", explanation)
            explained += 1
        conn.commit()
        results = dict(state.get("results", {}))
        results["slips"] = {"handled": len(slip_results), "explained": explained}
        return {"results": results}

    def reassign(state: ProjectState) -> dict:
        # Completed work frees capacity (remaining-effort weighting), so
        # previously-unassignable tasks get one retry per cycle. Existing
        # assignments are never reshuffled; still-stuck tasks raise nothing
        # (their flag + Tier 1 item already exist).
        result = assignment_engine.retry_unassigned(
            conn, state["project_id"], today=_today(state)
        )
        results = dict(state.get("results", {}))
        results["reassign"] = result
        return {"results": results}

    def escalations(state: ProjectState) -> dict:
        result = escalation.check_escalations(conn)
        results = dict(state.get("results", {}))
        results["escalations"] = result
        return {"results": results}

    def comms(state: ProjectState) -> dict:
        items = stakeholder_comms.run(conn, state["project_id"], _today(state), sonnet)
        results = dict(state.get("results", {}))
        results["comms"] = {"drafts": len(items)}
        return {"results": results}

    def log_cycle(state: ProjectState) -> dict:
        # OQ-4's simulation-date picker means testers re-run dates freely; a
        # re-run must be idempotent (the dedup_key mechanism keeps recurring
        # alerts from duplicating) AND visible — the audit entry says so.
        rerun = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log"
            " WHERE skill = 'orchestrator' AND action = 'monitoring_cycle'"
            "   AND project_id = ? AND input_summary LIKE ?",
            (state["project_id"], f'%"as_of": "{state["today"]}"%'),
        ).fetchone()["n"] > 0
        audit.log_action(
            conn, skill="orchestrator", action="monitoring_cycle",
            input_summary={"as_of": state["today"], "paused": state.get("paused", False),
                           "rerun": rerun},
            output_summary=state.get("results", {}),
            project_id=state["project_id"],
        )
        conn.commit()
        return {}

    graph = StateGraph(ProjectState)
    for name, fn in [
        ("pause_gate", pause_gate), ("status", status), ("risk", risk),
        ("slips", slips), ("reassign", reassign),
        ("escalations", escalations), ("comms", comms),
        ("log_cycle", log_cycle),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "pause_gate")
    # paused-work state: NOTHING runs except the escalation check (PRD s10)
    graph.add_conditional_edges(
        "pause_gate", lambda s: "paused" if s.get("paused") else "active",
        {"paused": "escalations", "active": "status"},
    )
    graph.add_edge("status", "risk")
    graph.add_edge("risk", "slips")
    graph.add_edge("slips", "reassign")
    graph.add_edge("reassign", "escalations")
    graph.add_conditional_edges(
        "escalations",
        lambda s: "comms" if (s.get("draft_comms") and not s.get("paused")) else "done",
        {"comms": "comms", "done": "log_cycle"},
    )
    graph.add_edge("comms", "log_cycle")
    graph.add_edge("log_cycle", END)
    return graph.compile()


def onboard_project(
    conn: sqlite3.Connection, project_id: int, today: date,
    sonnet: SonnetClient | None = None,
) -> ProjectState:
    graph = build_onboarding_graph(conn, sonnet)
    return graph.invoke({"project_id": project_id, "today": today.isoformat()})


def run_monitoring_cycle(
    conn: sqlite3.Connection, project_id: int, today: date,
    draft_comms: bool | None = None, sonnet: SonnetClient | None = None,
) -> ProjectState:
    """One monitoring cycle. draft_comms=None (the default) applies the
    comms_cadence gate; True forces an ad-hoc draft (PRD 8.8's 'ad hoc
    reviewer request' trigger); False suppresses it."""
    if draft_comms is None:
        draft_comms = comms_due(conn, project_id, today)
    graph = build_monitoring_graph(conn, sonnet)
    return graph.invoke({
        "project_id": project_id, "today": today.isoformat(),
        "draft_comms": draft_comms,
    })

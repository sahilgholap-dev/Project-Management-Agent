"""Shared LangGraph state (PRD section 2: skills as nodes, project_state as
shared state, conditional edges for tier routing and thresholds).

The sqlite connection and the Sonnet client are NOT part of the state — they
are bound into the node closures at graph-build time; the state carries only
plain data, so LangGraph can checkpoint it if that's ever needed.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ProjectState(TypedDict, total=False):
    project_id: int
    today: str            # ISO date the cycle runs "as of"
    draft_comms: bool     # comms cadence due this cycle (caller decides)
    halted: bool          # onboarding halted-and-surfaced (breakdown failure)
    paused: bool          # project is in the paused-work state
    results: dict[str, Any]

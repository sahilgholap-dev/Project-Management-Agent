"""Plain-language explanations of deterministic results (PRD 8.6 step 6).

The Dependency Manager computes the dates and never imports this module (the
no-LLM guardrail); the orchestrator calls explain_slip() to enrich the Tier 1
slip_impact payload with a human-readable summary. Sonnet 5 explains the
numbers — it never decides them.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.llm.sonnet_client import SonnetClient

_PROMPTS = Path(__file__).resolve().parent.parent.parent / "prompts"


def explain_slip(slip_payload: dict, sonnet: SonnetClient | None = None) -> str:
    sonnet = sonnet or SonnetClient()
    system = (_PROMPTS / "slip_explanation.md").read_text(encoding="utf-8")
    return sonnet.text(system, json.dumps(slip_payload, indent=2))

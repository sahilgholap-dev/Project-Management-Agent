"""Structural guardrail (plan section 1): the three deterministic skills and
the libraries they use must never import LLM machinery, so the PRD section 7
classification cannot erode silently. Checked on source text so it also
catches lazy/function-level imports."""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"

DETERMINISTIC_MODULES = [
    SRC / "skills" / "scheduler.py",
    SRC / "skills" / "assignment_engine.py",
    SRC / "skills" / "dependency_manager.py",
    SRC / "lib" / "allocation.py",
    SRC / "lib" / "calendar.py",
    SRC / "lib" / "task_graph.py",
    SRC / "governance" / "review_queue.py",
    SRC / "governance" / "tiers.py",
]

FORBIDDEN = re.compile(
    r"^\s*(from|import)\s+(src\.llm|anthropic|langchain|langgraph)", re.MULTILINE
)


@pytest.mark.parametrize("module", DETERMINISTIC_MODULES, ids=lambda p: p.name)
def test_no_llm_imports_in_deterministic_code(module):
    source = module.read_text(encoding="utf-8")
    match = FORBIDDEN.search(source)
    assert match is None, f"{module.name} imports LLM machinery: {match.group(0).strip()!r}"


def test_no_send_capability_exists_anywhere():
    """Stakeholder Comms is draft-only by design (PRD 8.8): no send/dispatch
    capability may exist anywhere in src/, so no implementation shortcut can
    ever wire drafting to sending. Sending is a human action outside this
    system."""
    forbidden = re.compile(
        r"^\s*(from|import)\s+(smtplib|email\.|sendgrid|mailgun|twilio|slack_sdk"
        r"|requests|httpx|urllib)",
        re.MULTILINE,
    )
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        match = forbidden.search(source)
        assert match is None, (
            f"{path} imports an outbound-capable client:"
            f" {match.group(0).strip()!r}"
        )
    comms = (SRC / "skills" / "stakeholder_comms.py").read_text(encoding="utf-8")
    assert not re.search(r"def\s+send", comms), "comms module defines a send function"


def test_review_queue_status_writers_are_exactly_two_modules():
    """Code-layer half of the no-auto-approval guarantee, held statically:
    approval/rejection has exactly ONE code path (resolve_item), and the only
    other module allowed to touch review_queue.status is escalation.py, whose
    writes are hard-coded 'escalated'/'paused' literals — rungs UP the ladder,
    never an approval. Any new writer anywhere in src/ fails this test."""
    allowed = {"review_queue.py", "escalation.py"}
    writers = {}
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        hits = re.findall(r"UPDATE\s+review_queue\s+SET[^\"]*", source, re.IGNORECASE)
        if hits:
            writers[path.name] = hits
    assert set(writers) <= allowed, f"unexpected review_queue writers: {writers}"

    # escalation.py may only write the two non-terminal ladder statuses
    for stmt in writers.get("escalation.py", []):
        assert "status = 'escalated'" in stmt or "status = 'paused'" in stmt, stmt
        assert "approved" not in stmt and "rejected" not in stmt, stmt

    # the terminal statuses appear in exactly one module
    for path in SRC.rglob("*.py"):
        if path.name in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        assert not re.search(
            r"review_queue\s+SET\s+status", source, re.IGNORECASE
        ), f"{path} writes review_queue.status"

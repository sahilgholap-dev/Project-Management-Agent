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

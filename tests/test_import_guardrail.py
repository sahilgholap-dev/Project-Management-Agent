"""Structural guardrail (plan section 1): the three deterministic skills and
the libraries they use must never import LLM machinery, so the PRD section 7
classification cannot erode silently. Checked on source text so it also
catches lazy/function-level imports."""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
API = Path(__file__).resolve().parent.parent / "api"

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


# The complete set of module roots src/ may import — an ALLOWLIST, mirroring
# how every other core invariant here is enforced (there is no forbidden way
# to send because there is no way to reach the network at all, except through
# the anthropic SDK, which can only talk to the model). Growing this list is a
# deliberate, CI-visible act. Notably absent by design: subprocess, os,
# socket, urllib, http, smtplib, requests, httpx, boto3, asyncio, ctypes.
ALLOWED_IMPORT_ROOTS = {
    # the ONE network-capable dependency: the model client
    "anthropic",
    # third-party, no I/O
    "jsonschema",
    "langgraph",
    # internal
    "src",
    # stdlib, no network / no process-spawning
    "__future__", "bisect", "dataclasses", "datetime", "functools",
    "graphlib", "json", "math", "pathlib", "re", "sqlite3", "types", "typing",
}


def _import_roots(path):
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_src_imports_are_allowlisted_no_send_capability():
    """Draft-only comms (PRD 8.8) enforced structurally, not by blocklist:
    the only network-capable import permitted anywhere in src/ is the
    anthropic SDK. subprocess / os.system / socket / urllib / boto3 / raw
    curl — anything that could dispatch a message — is absent because
    NOTHING outside this allowlist can be imported at all."""
    violations = {}
    for path in SRC.rglob("*.py"):
        bad = sorted(set(_import_roots(path)) - ALLOWED_IMPORT_ROOTS)
        if bad:
            violations[str(path.relative_to(SRC))] = bad
    assert not violations, f"imports outside the allowlist: {violations}"

    comms = (SRC / "skills" / "stakeholder_comms.py").read_text(encoding="utf-8")
    assert not re.search(r"def\s+send", comms), "comms module defines a send function"


# api/ allowlist (FRONTEND_IMPLEMENTATION_PLAN.md section 1): the src/ list
# plus INBOUND-serving frameworks and stdlib auth primitives. Outbound-capable
# modules stay forbidden — the API can receive HTTP, it cannot send anything.
# uvicorn is listed for completeness (the server is launched via
# `python -m uvicorn`, app code need not import it).
API_ALLOWED_IMPORT_ROOTS = ALLOWED_IMPORT_ROOTS | {
    "api", "fastapi", "pydantic", "starlette", "uvicorn",
    "secrets", "hashlib", "hmac", "contextlib", "sys",
}


def test_api_imports_are_allowlisted_no_send_capability():
    """The api/ layer must not reintroduce outbound-send capability: its
    allowlist adds only inbound-serving frameworks and stdlib auth. Any
    outbound client (requests/httpx/smtplib/boto3/subprocess/...) anywhere
    in api/ fails this test."""
    violations = {}
    for path in API.rglob("*.py"):
        bad = sorted(set(_import_roots(path)) - API_ALLOWED_IMPORT_ROOTS)
        if bad:
            violations[str(path.relative_to(API))] = bad
    assert not violations, f"api/ imports outside its allowlist: {violations}"


def test_allowlist_itself_contains_no_network_or_process_modules():
    """Guard the guard: nobody can quietly add an outbound-capable module to
    EITHER allowlist without this list also being edited."""
    forbidden = {
        "subprocess", "os", "socket", "ssl", "urllib", "http", "smtplib",
        "email", "ftplib", "telnetlib", "asyncio", "ctypes", "requests",
        "httpx", "aiohttp", "boto3", "botocore", "sendgrid", "twilio",
        "slack_sdk", "pika", "kafka",
    }
    for name, allowlist in [("src", ALLOWED_IMPORT_ROOTS),
                            ("api", API_ALLOWED_IMPORT_ROOTS)]:
        overlap = allowlist & forbidden
        assert not overlap, (
            f"network/process-capable modules in the {name} allowlist: {overlap}"
        )


def test_review_queue_status_writers_are_exactly_two_modules():
    """Code-layer half of the no-auto-approval guarantee, held statically:
    approval/rejection has exactly ONE code path (resolve_item), and the only
    other module allowed to touch review_queue.status is escalation.py, whose
    writes are hard-coded 'escalated'/'paused' literals — rungs UP the ladder,
    never an approval. Any new writer anywhere in src/ OR api/ fails this
    test — the API layer resolves items exclusively through resolve_item."""
    allowed = {"review_queue.py", "escalation.py"}
    writers = {}
    for root in (SRC, API):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            hits = re.findall(
                r"UPDATE\s+review_queue\s+SET[^\"]*", source, re.IGNORECASE
            )
            if hits:
                writers[path.name] = hits
    assert set(writers) <= allowed, f"unexpected review_queue writers: {writers}"

    # escalation.py may only write the two non-terminal ladder statuses
    for stmt in writers.get("escalation.py", []):
        assert "status = 'escalated'" in stmt or "status = 'paused'" in stmt, stmt
        assert "approved" not in stmt and "rejected" not in stmt, stmt

    # the terminal statuses appear in exactly one module
    for root in (SRC, API):
        for path in root.rglob("*.py"):
            if path.name in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            assert not re.search(
                r"review_queue\s+SET\s+status", source, re.IGNORECASE
            ), f"{path} writes review_queue.status"

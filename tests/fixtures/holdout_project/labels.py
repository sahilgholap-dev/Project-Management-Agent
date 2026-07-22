"""Hand labels for the holdout project — written BEFORE any eval ran, from a
human read of scope_document.md and transcript_kickoff.md. The eval scripts
score model output against these.

Read EVAL_NOTES.md for what this synthetic holdout does and does not prove.
"""

# ---- Task Breakdown expectations (scope_document.md) ------------------------

# POST-EVAL CALIBRATION CORRECTION (reviewed 2026-07-22): originally (3, 6),
# set before any eval ran. First real runs produced 7 phases and then 5-6 —
# the 7-phase decomposition was reviewed and judged coherent (Discovery ->
# Design -> Core Dev -> ERP -> Reporting -> Pilot -> Sign-off/Rollout), so the
# upper bound was a label miscalibration, not a model failure. Widened to
# (3, 8) based on reviewing actual output — NOT to make the test pass blindly.
# Run-to-run variance in decomposition granularity (7, then 5-6 phases on the
# same input) is a TRACKED CHARACTERISTIC of LLM decomposition, not a defect;
# see EVAL_NOTES.md.
PHASE_COUNT_RANGE = (3, 8)

# Genuine ambiguities planted in the scope. A correct run must FLAG (not
# resolve) at least these two — matched by keyword against the clarification
# payloads, case-insensitively.
MUST_FLAG_KEYWORDS = [
    ["erp"],                       # ERP product/version unknown, no API docs
    ["offline", "conflict"],       # conflict policy never resolved
]

# Work that must appear somewhere in the task list (keyword match against
# task titles+descriptions).
MUST_COVER_KEYWORDS = [
    ["work order"], ["offline"], ["sync"], ["schedul"], ["erp"],
    ["report"], ["auth"], ["signature"], ["pdf"], ["pilot"],
]

EFFORT_RANGE_HOURS = (2, 80)  # sanity bounds per task; prompt asks 4-40

# ---- Meeting Summary expectations (transcript_kickoff.md) -------------------

EXPECTED_DECISIONS = [
    # (keywords, decided_by contains)
    (["entra"], "dana"),
    (["pilot", "northeast"], "dana"),
]

EXPECTED_ACTION_ITEMS = [
    # (keywords, owner contains or None, implies_new_work)
    (["design doc"], "rob", None),          # new-work judgment call — not scored
    (["field list"], "dana", False),
    (["rugged", "device"], "yuki", True),   # explicitly "new work" in transcript
]

EXPECTED_BLOCKERS = [
    # (keywords, blocked contains, assigned_to contains or None)
    (["conflict"], "yuki", None),           # explicitly ownerless — must stay None
]

# Things that must NOT be extracted as decisions (discussed, not decided).
FORBIDDEN_DECISION_KEYWORDS = [["ios"]]

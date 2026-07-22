"""Hand labels for the holdout project — written BEFORE any eval ran, from a
human read of scope_document.md and transcript_kickoff.md. The eval scripts
score model output against these.

Read EVAL_NOTES.md for what this synthetic holdout does and does not prove.
"""

# ---- Task Breakdown expectations (scope_document.md) ------------------------

# Reasonable decompositions of this scope produce 3-6 phases (e.g. foundations/
# auth -> core work-order flow -> offline+integration -> pilot). Fewer than 3
# means the two-pass structure collapsed; more than 6 means over-fragmentation.
PHASE_COUNT_RANGE = (3, 6)

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

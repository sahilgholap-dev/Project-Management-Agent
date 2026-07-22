"""Task Breakdown eval against the holdout project (real Sonnet 5 calls).

Run explicitly (excluded from pytest):  python -m tests.eval_task_breakdown
Requires Anthropic credentials in the environment.

Read tests/fixtures/holdout_project/EVAL_NOTES.md before interpreting scores.
"""

import json
import sys

from src import db
from src.skills import task_breakdown
from tests.fixtures import holdout_project as ho
from tests.fixtures.holdout_project import labels


def keywords_in(text: str, keyword_group: list[str]) -> bool:
    text = text.lower()
    return all(k in text for k in keyword_group)


def main() -> int:
    conn = db.open_db(":memory:")
    ho.build(conn)

    result = task_breakdown.run(conn, ho.PROJECT_ID)  # real SonnetClient

    phases = conn.execute(
        "SELECT name, planned_start, planned_end, sequence_order FROM phases"
        " ORDER BY sequence_order"
    ).fetchall()
    tasks = conn.execute(
        "SELECT title, description, effort_hours, planned_start FROM tasks"
    ).fetchall()
    clar_payloads = " ".join(
        r["payload"] for r in conn.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ).lower()

    checks: list[tuple[str, bool, str]] = []

    lo, hi = labels.PHASE_COUNT_RANGE
    checks.append((
        "phase count in expected range", lo <= len(phases) <= hi,
        f"got {len(phases)}, expected {lo}-{hi}",
    ))
    checks.append((
        "phases-before-tasks: every phase dated (PRD s15)",
        all(p["planned_start"] and p["planned_end"] for p in phases),
        "",
    ))
    checks.append((
        "scheduler dated every task",
        bool(tasks) and all(t["planned_start"] for t in tasks),
        f"{sum(1 for t in tasks if not t['planned_start'])} undated of {len(tasks)}",
    ))
    for group in labels.MUST_FLAG_KEYWORDS:
        checks.append((
            f"ambiguity flagged, not guessed: {group}",
            keywords_in(clar_payloads, group),
            "no clarification item mentions it",
        ))
    task_text = " ".join(f"{t['title']} {t['description'] or ''}" for t in tasks).lower()
    for group in labels.MUST_COVER_KEYWORDS:
        checks.append((
            f"scope coverage: {group}", keywords_in(task_text, group), "",
        ))
    lo_e, hi_e = labels.EFFORT_RANGE_HOURS
    bad = [t["title"] for t in tasks if not (lo_e <= t["effort_hours"] <= hi_e)]
    checks.append((
        f"effort estimates within {lo_e}-{hi_e}h", not bad, f"outliers: {bad}",
    ))

    print(f"\nphases={len(phases)} tasks={len(tasks)}"
          f" deps={result['dependencies']} clarifications={len(result['clarifications'])}\n")
    for p in phases:
        print(f"  phase {p['sequence_order']}: {p['name']}"
              f"  {p['planned_start']}..{p['planned_end']}")
    print()

    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        failed += 0 if ok else 1
        print(f"[{mark}] {name}" + (f"  ({detail})" if detail and not ok else ""))

    print(f"\n{len(checks) - failed}/{len(checks)} checks passed."
          " See EVAL_NOTES.md for what this synthetic holdout does not prove.")
    print(json.dumps({"clarifications": result["clarifications"]}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Meeting Summary eval against the holdout transcript (real Sonnet 5 calls).

Run explicitly (excluded from pytest):  python -m tests.eval_meeting_summary
Requires Anthropic credentials in the environment.

Read tests/fixtures/holdout_project/EVAL_NOTES.md before interpreting scores.
"""

import json
import sys

from src import db
from src.skills import meeting_summary
from tests.fixtures import holdout_project as ho
from tests.fixtures.holdout_project import labels


def kw(text: str | None, group: list[str]) -> bool:
    return text is not None and all(k in text.lower() for k in group)


def main() -> int:
    conn = db.open_db(":memory:")
    ho.build(conn)
    conn.execute(
        "INSERT INTO phases (project_id, name, description, planned_start, planned_end,"
        " sequence_order) VALUES (?, 'Foundations', 'setup', '2026-09-07',"
        " '2026-10-02', 1)",
        (ho.PROJECT_ID,),
    )
    conn.commit()

    meeting_summary.run(
        conn, ho.PROJECT_ID, ho.TRANSCRIPT_KICKOFF,
        uploaded_by=1, meeting_date="2026-09-07",
    )

    decisions = json.loads(
        conn.execute("SELECT decisions FROM meetings").fetchone()["decisions"]
    )
    action_items = conn.execute(
        "SELECT a.description, a.due_date, a.converted_task_id, m.name AS owner_name"
        " FROM meeting_action_items a LEFT JOIN team_members m ON m.member_id = a.owner_id"
    ).fetchall()
    blockers = conn.execute(
        "SELECT b.description, b.assigned_to, bm.name AS blocked_name"
        " FROM blockers b LEFT JOIN team_members bm ON bm.member_id = b.blocked_member_id"
    ).fetchall()
    clar_payloads = " ".join(
        r["payload"] for r in conn.execute(
            "SELECT payload FROM review_queue WHERE item_type = 'clarification'"
        )
    ).lower()

    checks: list[tuple[str, bool, str]] = []
    hits = 0

    for keywords, decider in labels.EXPECTED_DECISIONS:
        match = next((d for d in decisions if kw(d.get("decision"), keywords)), None)
        ok = match is not None and kw(match.get("decided_by"), [decider])
        hits += 1 if ok else 0
        checks.append((f"decision recall: {keywords}", ok, json.dumps(match)))
    for keywords in labels.FORBIDDEN_DECISION_KEYWORDS:
        wrong = [d for d in decisions if kw(d.get("decision"), keywords)]
        checks.append((f"decision precision: {keywords} not a decision", not wrong,
                       json.dumps(wrong)))

    for keywords, owner, implies_new in labels.EXPECTED_ACTION_ITEMS:
        match = next((a for a in action_items if kw(a["description"], keywords)), None)
        ok = match is not None
        if ok and owner is not None:
            ok = kw(match["owner_name"], [owner])
        if ok and implies_new is True:
            ok = match["converted_task_id"] is not None
        if ok and implies_new is False:
            ok = match["converted_task_id"] is None
        checks.append((f"action item: {keywords}", ok,
                       json.dumps(dict(match) if match else None)))

    for keywords, blocked, assigned in labels.EXPECTED_BLOCKERS:
        match = next((b for b in blockers if kw(b["description"], keywords)), None)
        ok = match is not None and kw(match["blocked_name"], [blocked])
        if ok and assigned is None:
            # the load-bearing behavior: ownerless stays NULL and is flagged
            ok = match["assigned_to"] is None and "owner" in clar_payloads
        checks.append((f"blocker (ownerless stays unassigned): {keywords}", ok,
                       json.dumps(dict(match) if match else None)))

    print(f"\ndecisions={len(decisions)} action_items={len(action_items)}"
          f" blockers={len(blockers)}\n")
    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        failed += 0 if ok else 1
        print(f"[{mark}] {name}" + (f"  -> {detail}" if not ok else ""))

    print(f"\n{len(checks) - failed}/{len(checks)} checks passed."
          " See EVAL_NOTES.md for what this synthetic holdout does not prove.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

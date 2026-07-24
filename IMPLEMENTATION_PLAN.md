# NEXUS PM Agent — Implementation Plan (from PRD v5) — rev 3

Companion to `DATABASE_SCHEMA.md` (rev 2, updated). Rev 2 incorporated the reviewed
decisions on all 19 rev-1 Open Questions. Rev 3 records the answers to the five
follow-up questions (NEW-OQ 1–5) raised by the time-phased allocation redesign — **all
open questions are now resolved**; §6 records the decisions.

No implementation begins until this revision is confirmed.

Runtime stack per PRD §2: Python + LangGraph (skills as nodes, `project_state` as shared
state, conditional edges for tier routing/thresholds). Every runtime LLM call uses
**Claude Sonnet 5 (`claude-sonnet-5`)** — Fable 5 is the build-time tool only (§2, v4.1
correction). The three deterministic skills contain **zero** model calls (§7).
Database: **SQLite** (confirmed) — revisit only if the pilot shows write-lock contention
across a LangGraph cycle.

---

## 1. Repository Structure

One module per skill, matching §8's boundaries. `/prompts` is separate from `/modules`
so prompt iteration never touches skill logic (config-not-code doctrine, §3).

```
Project-Management-Agent/
├── schema/
│   ├── schema.sql                  # DDL from DATABASE_SCHEMA.md
│   └── migrations/                 # forward-only migration scripts
├── config/
│   ├── config_schema.json          # JSON Schema for client_config + allowed override keys
│   └── defaults.example.json       # documented example client config
├── src/
│   ├── db.py                       # connection, migrations runner, query helpers
│   ├── config_loader.py            # load + validate + RESOLVE (project override → client default)
│   ├── governance/
│   │   ├── review_queue.py         # raise_review_item(tier, type, payload) — the ONLY write path to review_queue
│   │   ├── escalation.py           # silence-escalation ladder: primary → backup → pause (§10)
│   │   └── tiers.py                # frozen skill/item_type → tier map (constant, NOT config — §10)
│   ├── llm/
│   │   └── sonnet_client.py        # single Anthropic client wrapper: claude-sonnet-5, structured-output validation, retries
│   ├── skills/
│   │   ├── task_breakdown.py       # 8.1  LLM
│   │   ├── scheduler.py            # 8.2  deterministic (CPM) — imports nothing from llm/
│   │   ├── assignment_engine.py    # 8.3  deterministic — imports nothing from llm/
│   │   ├── status_tracking.py      # 8.4  hybrid: evm.py math + LLM parse (reads status_reports inbox)
│   │   ├── risk_tracking.py        # 8.5  hybrid: rules.py + LLM pattern scan
│   │   ├── dependency_manager.py   # 8.6  deterministic — imports nothing from llm/
│   │   ├── meeting_summary.py      # 8.7  LLM
│   │   └── stakeholder_comms.py    # 8.8  LLM, draft-only
│   ├── lib/
│   │   ├── task_graph.py           # shared dependency graph + topo sort (used by 8.2 and 8.6)
│   │   ├── calendar.py             # working_calendar date math
│   │   ├── allocation.py           # TIME-PHASED capacity math: week bucketing, window-overlap
│   │   │                           # proration, per-week concurrent load across all active
│   │   │                           # projects (the ONLY capacity-check implementation —
│   │   │                           # assignment_engine and tests both call it)
│   │   ├── evm.py                  # PV/EV/AC, SV, CV — pure functions
│   │   └── audit.py                # audit_log writer, called by every skill
│   └── orchestrator/
│       ├── graph.py                # LangGraph wiring: nodes, conditional edges, tier routing
│       └── state.py                # project_state schema shared across nodes
├── prompts/
│   ├── task_breakdown_phases.md    # pass 1: scope → phases (reads client_config.project_definition to calibrate granularity)
│   ├── task_breakdown_tasks.md     # pass 2: phase → tasks
│   ├── status_parse.md
│   ├── risk_pattern_scan.md
│   ├── risk_duplicate_check.md
│   ├── slip_explanation.md         # 8.6 step 6 plain-language summary
│   ├── meeting_extract.md          # three buckets: decisions / action items / blockers
│   ├── comms_draft.md              # audience-conditional
│   └── retrospective.md            # §11 close path (confirmed): Sonnet 5, Tier 2 reviewed
└── tests/
    ├── fixtures/
    │   ├── known_answer_project/   # hand-built dataset with hand-computed CPM/assignment answers
    │   └── holdout_project/        # held-out sample project — NEVER opened during prompt development
    ├── test_config_loader.py
    ├── test_allocation.py          # NEW: week bucketing + proration unit tests (see §3)
    ├── test_scheduler.py
    ├── test_assignment_engine.py
    ├── test_cross_project_capacity.py   # the §9 two-projects-one-person test, time-phased (see §3)
    ├── test_dependency_manager.py
    ├── test_governance.py
    ├── eval_task_breakdown.py      # LLM evals, run against holdout
    ├── eval_meeting_summary.py
    └── test_orchestrator.py
```

Structural guardrail (unchanged, confirmed): `scheduler.py`, `assignment_engine.py`,
`dependency_manager.py` must not import `llm/` — enforced with an import-linter rule,
so the §7 classification can't erode silently.

---

## 2. Build Order (dependency-driven)

**Phase 0 — Schema + config loader** (everything depends on these)
1. `schema.sql` + migration runner + `db.py`.
2. `config_schema.json` + `config_loader.py` with the resolution rule:
   `resolve(project_id, key)` → project `config_overrides[key]` if present, else
   `client_config` value, else **hard error if the key is required** (§16: skill refuses
   to run, surfaced as a config defect — never a silent default).
   Cadence fields validate as the enum `daily | weekly | biweekly` (confirmed — no cron).
3. Config validation on every save (§13), including the two §16 edge cases:
   required field blank; reviewer unset at both levels.
4. `audit.py` — every later skill logs through it from day one.
   ✅ Gate: `test_config_loader.py` green before any skill is written.

**Phase 1 — Deterministic skills** (no external dependency; correctness-testable in isolation)
5. `lib/task_graph.py` + `lib/calendar.py` + **`lib/allocation.py`** (shared by 8.2/8.3/8.6).
   `allocation.py` carries the time-phased redesign, now fully specified
   [confirmed NEW-OQ 1/2/5]: given a member, a date window, and the working calendar,
   it returns per-week concurrent load across **every active project** —
   **ISO week buckets (Monday start)**; each open task's `effort_hours` spread
   **uniformly over the working days** (per `working_calendar`) of its planned window;
   effective weekly capacity **prorated down in holiday weeks** (same working-day basis
   as demand). Built and unit-tested (`test_allocation.py`) before the Assignment Engine
   that depends on it.
6. **Scheduler (8.2)** — CPM: topo sort, forward/backward pass, slack, critical path,
   working-calendar-aware. Infeasible plan → Tier 1 item (stub `raise_review_item`;
   full escalation ladder in Phase 4).
7. **Assignment Engine (8.3)** — greedy skills-and-capacity match, **time-phased**
   (confirmed correction): for each candidate task, identify every week bucket its
   planned window touches; a candidate member qualifies only if, in *each* of those
   weeks, their existing concurrent load (from `allocation.py`, across all active
   projects) plus the task's prorated contribution stays ≤ that week's effective
   capacity (weekly `capacity_hrs`, default 40, prorated down in holiday weeks —
   confirmed NEW-OQ 2). No flat backlog sums anywhere. A task with no planned dates
   cannot be capacity-checked → refused, flagged, Tier 1 clarification item raised
   [confirmed NEW-OQ 4] (Scheduler runs first per §8.3's trigger, so this is the
   exception path). No qualifying week-set →
   `unassignable` + Tier 1, never over-allocate. After each run, refresh the
   `team_members.allocated_hrs` display cache (current-week load) — the cache is never
   read for decisions.
8. **Dependency Manager (8.6)** — slip detection, forward walk, restricted re-schedule,
   date diff, Tier 1 on threshold breach. (Sonnet plain-language summary bolted on in
   Phase 2; the LLM never decides dates.) Note: a slip that moves task windows also
   moves allocation between weeks — after a re-schedule, affected members' capacity is
   re-checked and any new week-level overload is flagged as Tier 1, not silently kept.
   ✅ Gate: all three pass the known-answer fixture dataset.

**Phase 2 — LLM reasoning skills** (need `sonnet_client.py`)
9. `sonnet_client.py` — model `claude-sonnet-5`, JSON-schema-validated outputs, retry on
   malformed output, **halt-and-surface** on validation failure after retries (§8.1 step 4).
10. **Task Breakdown (8.1)** — strictly two-pass: phases first (validated + written),
    then per-phase tasks; reads `client_config.project_definition` (confirmed purpose:
    calibrates phase-decomposition granularity); effort-vs-timeline capacity check flags
    the reviewer; hands off to Scheduler.
11. **Meeting Summary (8.7)** — three-bucket extraction; per-project uploads only
    (confirmed — a `project_id` is supplied at upload; multi-project transcripts out of
    scope for v1); action items with `converted_task_id` linkage; blockers with
    `assigned_to` left NULL + flagged when ownership is unclear.
    ✅ Gate: both evaluated against the holdout project (see §3).

**Phase 3 — Hybrid skills** (need both halves from Phases 1–2)
12. **Status Tracking (8.4)** — self-reports arrive via the `status_reports` inbox table
    with manual entry (confirmed — no channel integration in v1; all external tool
    integrations deferred). Sonnet parses raw text → validated status enum
    (`todo/in_progress/blocked/done/cancelled`, confirmed; ambiguous → flag, never
    guess); then deterministic `evm.py` computes PV/EV/AC, SV = EV−PV, CV = EV−AC;
    threshold breach → Tier 1 + risks_issues entry.
13. **Risk & Issue Tracking (8.5)** — rule pass (no LLM) + Sonnet pattern pass →
    duplicate check against open risks → severity×likelihood score → insert tagged
    `rule_based`/`pattern_detected` → Tier 1 item.

**Phase 4 — Governance layer** (the skills that feed it now exist)
14. Full `review_queue.py` + `tiers.py` (frozen map) + reviewer approve/reject flow.
15. `escalation.py` — silence ladder: notify primary → after resolved escalation delay
    in **hours** (per-tier override if configured, else client default) notify backup →
    if backup silent (or unset, §16) set project `status='paused'` with banner reason.
16. **Change requests & sign-off packets** (confirmed v1 scope): reviewer/admin-initiated
    only, via a basic form → Tier 3 review routing. **No skill auto-creates them** — a
    skill detecting a scope/timeline/budget conflict raises its normal Tier 1 alert and
    stops; alert→CR auto-escalation is Upgrade-phase.
    ✅ Gate: `test_governance.py` proves no code path auto-approves Tier ≥ 1.

**Phase 5 — Stakeholder Comms (8.8)** — deliberately after governance, since its only
output *is* a Tier 2 review item. Draft written to review_queue; **no send function
exists anywhere in the module**. Approved text versioned in artifact_versions.

**Phase 6 — Orchestrator wiring** (every skill independently tested first)
17. LangGraph graph per §11's operating cycle: intake → breakdown → schedule → assign →
    monitor loop (status/risk/dependency/blockers) → review checkpoints → outputs;
    conditional edges for tier routing and threshold triggers. Project close path
    (confirmed): Sonnet 5 generates a retrospective, stored in `artifact_versions` as
    `retrospective`, reviewed at Tier 2, then the project is archived.
18. End-to-end test on the known-answer project, then the second-independent-project
    acceptance check (§15: zero project-specific code).

---

## 3. Testing Strategy per Skill (maps to §15 acceptance criteria)

| Skill | Type (§7) | Strategy |
|---|---|---|
| Allocation lib (new) | Deterministic | Pure-function tests for week bucketing and proration under the confirmed rules (uniform spread over working days, ISO Monday weeks, holiday-prorated capacity): single-week task, task spanning 3 weeks, partial-week boundary overlap, week containing a holiday (both demand and capacity sides), task exactly filling capacity. Hand-computed expected loads. |
| Scheduler | Deterministic | Hand-built fixture (~15 tasks, known CPM answer computed by hand): exact planned dates, slack values, critical path. Edge tests: weekend/holiday skipping, cycle in graph → loud failure, duration > timeline → Tier 1 item. |
| Assignment Engine | Deterministic | Same fixture with a hand-verified owner map under each `assignment_strategy`, with per-week expected loads. Edge tests: no skill overlap, all candidates at capacity **in the relevant week** → `unassignable` + Tier 1, inactive members excluded, dateless task refused. |
| Dependency Manager | Deterministic | Inject a known slip; assert exact downstream date diffs, breach > `slip_threshold_days` → Tier 1, unrelated tasks untouched. New: assert that a slip pushing a task into an already-loaded week re-flags capacity rather than silently keeping the assignment. |
| Task Breakdown | LLM | Eval against **holdout project** (never opened while writing prompts). Score: schema validity, phases-before-tasks ordering, every phase has valid dates before its tasks exist (§15), ambiguity → `needs_clarification` not invention. |
| Meeting Summary | LLM | Holdout transcripts with hand-labeled decisions/action-items/blockers; precision/recall; unclear blocker owner → NULL + reviewer flag. |
| Status Tracking | Hybrid | (a) `evm.py` pure-function tests with hand-computed PV/EV/AC/SV/CV; (b) LLM parse eval on held-out free-text replies incl. ambiguous ones that must flag, not guess; (c) inbox flow: unprocessed `status_reports` rows consumed exactly once. |
| Risk & Issue Tracking | Hybrid | (a) Rule pass unit tests — pure code; (b) pattern-scan + duplicate-check eval on holdout notes; assert `source` tag correctness. |
| Stakeholder Comms | LLM | Holdout data → drafts per audience_type; assert every run's terminal action is a Tier 2 review_queue row and nothing else. |

**Cross-project capacity test (time-phased — rev 2 redesign per review decision Q3):**
`test_cross_project_capacity.py` — one member, `capacity_hrs = 40`/week, shared by
Projects A and B. Booking scenarios now pin every task to explicit planned windows:

- **Variant 1 — overlapping week (contention):** Project A assigns 30 h of tasks whose
  planned windows all fall inside the week of **Mon 2026-08-03 → Fri 2026-08-07**.
  Project B then has 25 h of matching tasks planned in that **same week**. Assert: B
  assigns at most 10 h into that week; the remainder is flagged `unassignable` with a
  Tier 1 item; that week's recomputed concurrent load never exceeds 40; the
  `allocated_hrs` cache matches the recomputation for the current week.
- **Variant 2 — disjoint weeks (no contention):** same 30 h/25 h totals, but B's task
  windows fall entirely in the **following** week (2026-08-10 → 2026-08-14). Assert: B
  assigns all 25 h — under the retired flat-sum design this would have wrongly failed,
  so this variant is the regression test for the rev-1 → rev-2 correction.
- **Variant 3 — spanning task (proration, numbers now fixed by NEW-OQ 1/2/5):** B has
  one 20 h task spanning **both** weeks, planned Wed 2026-08-05 → Wed 2026-08-12
  (no holidays in the fixture). Working days: 3 in the week of Aug 3 (Wed–Fri) and 3 in
  the week of Aug 10 (Mon–Wed) → uniform spread contributes **10 h to each week**.
  Week-1 check: A's existing 30 h + 10 h = exactly 40 = capacity → assignable, at the
  boundary (also serves as the ≤-vs-< boundary test). Assert the 10/10 split and that
  neither week's recomputed load exceeds 40. A companion sub-case shifts A's booking to
  32 h so week 1 would hit 42 → assert refusal + `unassignable` + Tier 1, even though
  week 2 alone had room.
- **Variant 4 — order independence:** run A-then-B and B-then-A assignment; assert no
  ordering silently over-allocates any week.

**Governance tests** (unchanged, confirmed): for every item_type, programmatic approval
without `resolved_by` → DB CHECK rejects; silent primary → backup notified within the
resolved delay (hours); silent/unset backup → project paused, never approved.

**Config tests** (unchanged, plus): cadence values outside `daily|weekly|biweekly`
rejected; override resolution (project wins; client fallback; both-null required key →
skill refuses with config-defect surface).

---

## 4. Config-First Discipline (§3)

Unchanged from rev 1 (confirmed in review):

- Config JSON Schema + `config_loader.py` built and fully tested **before any skill**;
  every skill receives behavior parameters exclusively through `resolve(project_id, key)`;
  no behavioral constant hardcoded in a skill module.
- Validation runs on **every save** (§13), including direct file edits (§16).
- The one deliberate exception: the **tier map is code** (frozen constant), because §10
  says tiers are "not adjustable by a client to weaken oversight." Config that tried to
  set a tier is rejected by the validator.
- Acceptance check §15 (second independent project, zero project-specific code) is the
  final proof of the doctrine — an explicit Phase 6 test.

---

## 5. Human-in-the-Loop Call-Outs (§10, §14)

Unchanged from rev 1 (confirmed in review), with one addition (item 11):

1. **Tier 1** (risk alert, off-track alert, infeasible plan, unassignable task, slip
   impact, clarifications): single-tap approve/reject — item sits `pending` until a human
   resolves or the escalation ladder pauses the project.
2. **Tier 2** (status reports, comms drafts, retrospectives): full review before anything
   goes out.
3. **Tier 3** (change requests, sign-off packets): explicit sign-off by the configured
   `change_approver` / `signoff_approver`.
4. **No auto-approval at Tier ≥ 1, under any configuration** (§15): no `auto_approved`
   status exists in the schema CHECK; `approved` requires non-null human `resolved_by`
   (DB CHECK); `skill_depth` config is validated so no depth setting bypasses the queue
   (Stakeholder Comms explicitly never accepts a fully-automatic depth, §8.8).
5. **Stakeholder Comms is draft-only**: the module's terminal write is a Tier 2
   review_queue row. **No send/dispatch function, email client, or channel integration
   exists in the codebase at all** — sending is a human action outside the system.
6. **Silence never becomes consent**: primary silent → backup notified; backup silent or
   unset → project paused with visible banner (§10, §16). Pause, not proceed.
7. **LLM validation failures halt and surface** (§8.1 step 4, §8.4 step 4): never
   silently patched or guessed.
8. **Risk scores are reviewer-adjustable** (§8.5 step 4).
9. **Blocker with unclear owner** → surfaced to reviewer, not guessed (§8.7 step 6).
10. **Tier 0** (internal documentation & archiving) is the *only* fully automatic class
    (§10), and it is audit-logged.
11. **Change requests and sign-off packets are human-initiated in v1** (confirmed Q17):
    no skill creates a Tier 3 item; skills raise Tier 1 alerts and stop. Auto-escalation
    from alert to formal change request is Upgrade-phase.

---

## 6. Open Questions — none remaining

All 19 rev-1 questions and all five rev-2 follow-ups (NEW-OQ 1–5) are resolved.
Decision record for the five follow-ups (confirmed in review, 2026-07-22):

1. **NEW-OQ 1 — Uniform effort spread.** A task's `effort_hours` is split across the
   weeks its planned window touches in proportion to that window's share in each week.
   Front-loaded rejected (arbitrary without behavioral data); worst-case rejected (would
   quietly reintroduce the flat-sum over-pessimism the redesign exists to fix).
2. **NEW-OQ 2 — Working-day proration, holiday-prorated capacity.** Overlap fractions
   count working days per `working_calendar` (weekends/holidays get no effort), and
   effective weekly capacity is prorated down in holiday weeks — demand and supply on
   the same basis. Consequence: the authoritative capacity math lives in
   `lib/allocation.py`; the SQL query in DATABASE_SCHEMA.md is an approximate
   test-time cross-check only.
3. **NEW-OQ 3 — `allocated_hrs` = current-week load, display-only.** Refreshed each
   Assignment Engine run; never read for decisions (those always derive from `tasks` at
   check time). `member_weekly_load` table rejected as v1 over-engineering.
4. **NEW-OQ 4 — Refuse-and-flag on dateless tasks.** A task with no planned window is
   refused, flagged, and raised as a Tier 1 clarification item — never guessed at,
   consistent with the build's standing never-silently-proceed principle.
5. **NEW-OQ 5 — ISO weeks, Monday start**, aligned with the Mon–Fri working calendar.

### Known limitations — tracked fast-follows

**FF-1 — Capacity math vs `percent_complete`: ✅ IMPLEMENTED (Phase 1, second commit).**
Remaining-effort weighting (`effort_hours × (1 − COALESCE(percent_complete, 0)/100)`)
landed in `lib/allocation.py::remaining_effort()` immediately after the allocation
library, while the module was still open, as planned. Confirmed semantics: NULL
`percent_complete` = 0% complete (full effort — no signal means nothing is confirmed
done); a task reported 100% but not statused `done` contributes nothing; the candidate
task being assigned always counts at full effort. Dedicated tests in
`tests/test_allocation.py` cover NULL, partial, 100%-not-done, and
capacity-freeing-as-work-completes.

Nothing blocks Phase 0. Implementation starts on your explicit go-ahead.

### E2E-audit follow-ons (2026-07-23, non-blocking — tracked, not scheduled)

From the first full end-to-end run's DB audit. The four confirmed fixes from that
audit (phase-date write-back, `cost_data_complete` covering unestimated tasks,
queue-level dedup for persistent breaches, cycle idempotency per `as_of`) are
IMPLEMENTED (migration `003_review_dedup.sql`); slack re-anchoring is next. These
remain open:

- **FO-1 — Converted-task phase heuristic.** A meeting action item converted to a
  task lands in the *earliest open phase* (all phases `planned` → phase 1), which can
  be semantically wrong (a build task filed under Discovery). Largely cosmetic now
  that the unestimated task trips `cost_data_complete`. Better heuristic: latest
  in-progress phase, else earliest not-done phase.
- **FO-2 — Phase status lifecycle.** `phases.status` never leaves `planned` — task
  progress and project archive don't roll up. Harmless to math (nothing reads it for
  decisions), misleading in views and the retrospective ("all phases remain planned").
- **FO-3 — No re-parse path for resolved-ambiguous status reports.** Once a report is
  flagged ambiguous its signal is dead even after the clarification is resolved;
  the member must submit a new report. Candidate: reviewer supplies the structured
  status on the clarification item, applied on approval.

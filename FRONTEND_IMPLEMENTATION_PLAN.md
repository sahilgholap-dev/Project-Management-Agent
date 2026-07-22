# NEXUS PM Agent — Frontend Implementation Plan (v1, for review)

Scope: a Next.js testing/review frontend over the completed Phase 0-6 backend
(schema, skills, governance, orchestrator — all in `src/`, 168 tests). One
client, one reviewer, internal use. Nothing here is built until this plan is
approved.

Companion docs: `NEXUS_PM_Agent_PRD_v5.docx`, `DATABASE_SCHEMA.md`,
`IMPLEMENTATION_PLAN.md`.

---

## 1. API Layer

### Decision: FastAPI, as a thin wrapper in a new top-level `api/` directory

Justification, in order of weight:

1. **Zero reimplementation.** The backend is Python; FastAPI imports
   `src.db`, `src.config_loader`, `src.governance.*`, `src.skills.*`, and
   `src.orchestrator.*` directly and calls the exact functions the 168 tests
   already cover. Any non-Python API layer (Next.js API routes talking to
   SQLite directly, a Node sidecar) would force reimplementing config
   resolution, the resolver-gated review flow, or worse — the capacity math.
   That is the one unacceptable outcome.
2. **Typed contract for free.** FastAPI's Pydantic models generate an OpenAPI
   schema; `openapi-typescript` turns that into the frontend's request/
   response types. The Python side stays the single source of truth.
3. **Same process as the DB.** SQLite + one uvicorn worker is exactly the
   single-writer shape the backend was built for (the SQLite decision's
   "revisit on write-lock contention" signal stays observable here).

**Thin-wrapper rule (hard):** an endpoint may (a) call an existing `src/`
function, or (b) do plain single-table CRUD for rows that have no business
logic (clients, users, team_members, stakeholders, reading logs). It may
never contain scheduling, capacity, EVM, tier, or resolution logic. Every
"verb" endpoint below names the `src/` function it wraps.

### Guardrail compliance (extension, not bypass)

The two static guardrails currently scan `src/` only. Both are **extended to
`api/`** as part of this work — test changes are additive assertions, never
relaxations, and no `src/` code changes:

- **Status-writer test:** the scan adds `api/` to its sweep. `api/` contains
  zero `UPDATE review_queue` statements — resolution goes through
  `resolve_item`, raising goes through the skills. The two-writer property
  (review_queue.py + escalation.py) must still hold with the wider scan.
- **No-send allowlist:** `api/` gets its **own allowlist** (a second constant
  in the same test file): the `src/` allowlist **plus** `fastapi`,
  `pydantic`, `starlette`, `uvicorn`, and stdlib `secrets`/`hashlib`/`hmac`
  (auth). These are *inbound-serving* additions; every outbound-capable
  module (`requests`, `httpx`*, `smtplib`, `boto3`, `subprocess`, `socket`,
  …) stays forbidden, and the guard-the-guard test covers the new list too.
  The API can receive HTTP; it cannot send anything anywhere.

  *Note: `httpx` is a FastAPI *test-client* dependency. It will appear in
  `api/tests/` only, never in `api/` app code; the allowlist scan covers app
  code, and a separate assertion pins `api/tests/` usage to `TestClient`.

### Auth (the one flagged near-exception — decision needed)

`users` has no credential storage (verified against the live schema). The
API needs login. Proposal, chosen to keep existing tables untouched:

- **New table `auth_credentials`** (`user_id` FK, `password_hash`,
  `created_at`) via **`schema/migrations/002_auth.sql`** — the forward-only
  migration runner built in Phase 0 exists for exactly this. No existing
  table, column, or `src/` module is modified; `src/` never reads this table.
- Session = signed HTTP-only cookie (stdlib `hmac`, server-side secret), no
  external auth library. Role checks in one FastAPI dependency reading
  `users.role`.
- **Bootstrap:** `users.client_id` is NOT NULL, so the first `platform_admin`
  needs a row to hang off. Proposal: a small `api/bootstrap.py` CLI seeds a
  "platform" client row + the first platform_admin and prints its
  credentials once. (Alternative if you prefer zero semantic stretching of
  `clients`: make `users.client_id` nullable — but that touches an existing
  table, so I'd rather not.)

Per the ground rules this is flagged, not assumed: **OQ-1 below asks you to
approve the migration + bootstrap approach before anything is built.**

### Endpoint list, grouped by what each wraps

**Auth & session** (new `api/auth.py`, no `src/` counterpart — flagged above)
| Endpoint | Wraps |
|---|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | `auth_credentials` + `users` lookup |

**Admin portal** (plain CRUD — PRD §4 steps 1-2 have no `src/` functions; they are row inserts)
| Endpoint | Wraps |
|---|---|
| `POST /admin/clients` | `INSERT INTO clients` (refused if one exists — single-client v1) |
| `POST /admin/users` | `INSERT INTO users` + `auth_credentials`; **returns the generated password in the response exactly once, for on-screen display** |

> **"Send invite" constraint (explicit, by design, not an oversight):** the
> backend has zero outbound-send capability and the allowlist test enforces
> that this stays true for `api/` as well. Invite = generate credentials →
> display on-screen → manual handoff (the admin reads them to the client
> over whatever channel they already use). No email, no link generation that
> implies delivery, ever. The button label in the UI is "Generate
> credentials", not "Send invite", so the UI cannot even *suggest* sending.

**Config** (PRD §5)
| Endpoint | Wraps |
|---|---|
| `GET /config` / `PUT /config` | `config_loader.load_client_config` / `save_client_config` (validate-on-every-save comes free; 422 with the full defect list) |
| `PUT /projects/{id}/overrides` | `config_loader.save_project_overrides` |
| `GET /projects/{id}/config` | `config_loader.resolve` per key — shows the *resolved* config so override behavior is visible during testing |

**Team & stakeholders** (plain CRUD; `allocated_hrs` is read-only display per NEW-OQ 3)
| Endpoint | Wraps |
|---|---|
| `GET/POST/PATCH /team-members` | `team_members` rows |
| `GET/POST/DELETE /stakeholders` | `stakeholders` rows |

**Projects & orchestrator triggers** (PRD §4 step 3-4, §11)
| Endpoint | Wraps |
|---|---|
| `GET/POST /projects`, `GET /projects/{id}` | project rows + phases/tasks/deps join (incl. `slack_days`, `on_critical_path`, `unassignable`, `needs_clarification`) |
| `POST /projects/{id}/onboard` | `orchestrator.graph.onboard_project` |
| `POST /projects/{id}/cycle` | `orchestrator.graph.run_monitoring_cycle` (body: `as_of` date, optional `draft_comms` tri-state) |
| `POST /projects/{id}/close` | `orchestrator.lifecycle.generate_retrospective` |
| `POST /projects/{id}/archive` | `orchestrator.lifecycle.archive_project` (backend refuses until the retrospective is approved — the UI surfaces the refusal, never works around it) |
| `POST /projects/{id}/resume` | `escalation.resume_project` |

**Review queue** (PRD §10 — the core testing surface)
| Endpoint | Wraps |
|---|---|
| `GET /review-queue?project&status&tier` | read of `review_queue` (+ escalation stages per item for ladder visibility) |
| `POST /review-queue/{id}/resolve` | `review_queue.resolve_item(decision, notes, final_text)` — the ONLY resolution path; no raw status writes exist in `api/` |
| `POST /escalations/check` | `escalation.check_escalations` (manual trigger for testing; also runs inside every monitoring cycle) |

**Inputs to skills**
| Endpoint | Wraps |
|---|---|
| `POST /status-reports` | `INSERT INTO status_reports` (the confirmed Q7 manual inbox; parsing happens in the next cycle, not at POST time) |
| `POST /projects/{id}/meetings` | `skills.meeting_summary.run` (paste/upload transcript) |

**Registers & logs**
| Endpoint | Wraps |
|---|---|
| `GET /projects/{id}/risks` | `risks_issues` read |
| `PATCH /risks/{id}/score` | severity/likelihood update — PRD 8.5 step 4 "always reviewer-adjustable"; **OQ-6 flags that no `src/` function exists for this yet** |
| `GET /projects/{id}/blockers` | `blockers` read (raised_by / assigned_to / blocked_member joined to names) |
| `PATCH /blockers/{id}` | assign owner / resolve — same OQ-6 flag |
| `GET /projects/{id}/escalation-log`, `GET /projects/{id}/audit-log` | read-only |
| `GET /projects/{id}/artifacts` | `artifact_versions` read |
| `POST /projects/{id}/change-requests`, `POST /projects/{id}/signoff-packets` | `governance.forms.create_change_request` / `create_signoff_packet` |

---

## 2. Next.js Structure

App Router, TypeScript, Tailwind (utility styling only — no component
library commitment for a testing UI). New top-level `frontend/` directory.

```
frontend/src/
├── middleware.ts               # session cookie -> role; routes gated by users.role
├── lib/api.ts                  # typed fetch client (types generated from FastAPI OpenAPI)
├── app/
│   ├── login/page.tsx
│   ├── (admin)/admin/          # platform_admin only
│   │   ├── page.tsx            # client + client_admin creation status
│   │   └── users/page.tsx      # create user -> credentials shown ONCE on screen
│   └── (client)/               # client_admin / member
│       ├── layout.tsx          # nav + paused-project banner (PRD s10 visible banner)
│       ├── page.tsx            # project list + "new project" form
│       ├── config/page.tsx     # client_config editor (defect list rendered on 422)
│       ├── team/page.tsx       # team members CRUD; allocated_hrs read-only
│       ├── review-queue/page.tsx           # cross-project queue, tier-grouped
│       └── projects/[id]/
│           ├── page.tsx        # dashboard: phases/tasks table, critical path, owners
│           ├── settings/page.tsx           # config_overrides + resolved view
│           ├── status/page.tsx # manual status-report entry + inbox state
│           ├── meetings/page.tsx           # transcript paste + extraction results
│           ├── risks/page.tsx  # register: sort by score, filter by status
│           ├── blockers/page.tsx           # raised_by vs assigned_to; NULL-owner surfaced
│           ├── logs/page.tsx   # escalation log + audit log (read-only tabs)
│           └── close/page.tsx  # retrospective trigger -> Tier 2 review -> archive
```

Role model: `platform_admin` sees `(admin)` only; `client_admin` sees all of
`(client)`; `member` sees `(client)` read-mostly (can submit status reports
and meetings; cannot edit config/team or resolve review items). Enforced in
`middleware.ts` AND per-endpoint in FastAPI (the API is the real boundary;
the middleware is UX).

### Review queue rendering (the part that must not encourage rubber-stamping)

One `ItemCard` per `item_type` family, tier decides the interaction:

- **Tier 1** (risk_alert, off_track_alert, infeasible_plan,
  unassignable_task, slip_impact, clarification): compact card — payload
  summary (e.g. slip_impact shows the plain-language `explanation` plus a
  collapsible raw diff) with single-tap **Approve / Reject** and an optional
  notes field. Nothing pre-selected; both buttons equal visual weight.
- **Tier 2** (comms_draft, status_report, retrospective): full-content view.
  The draft renders in an **editable textarea seeded with the draft text**;
  if the reviewer edits, the edited text is sent as `final_text` (this is
  exactly what `resolve_item`'s parameter exists for, and approval versions
  it in `artifact_versions`). The data basis (`data_basis` payload) renders
  alongside so claims can be traced. Approve is a distinct click *after*
  scrolling the content (button below the content, not floating).
- **Tier 3** (change_request, signoff_packet): formal packet view — full
  payload, linked form row, and sign-off requires a **typed confirmation**
  (retype the packet title) before the Approve button enables. Deliberate
  friction, matching "formal packet, explicit sign-off".
- Every card shows its escalation ladder state (primary notified / backup
  notified / paused) from `escalation_log`, so silence-escalation behavior
  is verifiable during testing.
- Nothing is ever auto-selected, pre-approved, batch-approved, or
  keyboard-shortcut-approved. No "approve all" exists at any tier.

---

## 3. Build Order

Sequenced so the review queue and dashboard are usable as early as possible
— they're what exercises the backend end-to-end.

- **F0 — API skeleton + auth** (blocks everything): FastAPI app, `002_auth`
  migration, bootstrap CLI, login/session, role dependency, guardrail-test
  extensions to `api/`. Gate: API tests green, both extended guardrails green.
- **F1 — Core wrappers + typed client**: projects/phases/tasks read,
  onboard/cycle triggers, review-queue read + resolve, config read.
  OpenAPI → TS types. Gate: curl-level walkthrough of onboard → queue →
  resolve against a seeded DB.
- **F2 — The two core screens**: review queue (all tiers, all 11 item_types)
  and project dashboard (+ project creation form + onboard button). At the
  end of F2 the full loop is exercisable from a browser: create project →
  onboard → see plan → resolve items.
- **F3 — Skill inputs**: status-report entry, meeting upload, "run cycle"
  control (with `as_of` date picker — see OQ-4), paused-project banner +
  resume.
- **F4 — Config, team, registers**: config editor with defect rendering,
  overrides editor with resolved view, team CRUD, risks register (sort/
  filter + score adjust), blockers view (NULL-owner surfaced at top).
- **F5 — Close path + logs + polish**: retrospective flow (trigger → Tier 2
  edit-approve → archive with backend-refusal surfaced), escalation/audit
  log views, admin portal, critical-path Gantt-ish rendering upgrade (a
  positioned-div timeline; no charting library unless it stays trivial).

  F5 follow-ons (noted, not blocking): the session signing secret
  (`.session_secret`) has no rotation path — regenerating it logs everyone
  out; fine for a single-tester tool, revisit before any wider use.

---

## 4. Data Fetching / State

**Server Components for reads + Server Actions for mutations, no client
cache library.** Reasoning rather than default:

- Every page's data is one or two API reads rendered as tables/cards.
  Server Components fetch from FastAPI at request time; there is no client
  state worth caching for a single-user testing tool, so React Query/SWR
  would add an invalidation layer with nothing to pay for it.
- Mutations (resolve, create, trigger cycle) are Server Actions that call
  the typed client then `revalidatePath` — the re-render shows the
  post-mutation truth from SQLite, which is precisely what a testing UI
  must show (no optimistic UI anywhere: an "approved" that could roll back
  visually is the opposite of what governance testing needs).
- One deliberate exception: the review-queue page gets a manual **Refresh**
  button rather than polling (OQ-5 asks whether you want auto-polling; with
  a single tester, polling hides the cause-effect timeline).
- Types come from the OpenAPI schema (`openapi-typescript`) so the Python
  Pydantic models remain the single source of truth; no hand-maintained
  duplicate types.

---

## 5. Additivity Confirmation

Nothing in this plan touches `src/` skill logic, existing schema tables, or
relaxes any guardrail test:

- New code lives in `api/` and `frontend/` only.
- Schema change is one **additive** migration (`002_auth.sql`, new table
  only) through the existing forward-only runner — pending your OQ-1
  approval. No existing table/column is altered.
- Guardrail tests are **extended** (wider scan + second allowlist +
  guard-the-guard coverage of the new list). The existing assertions are
  untouched and must keep passing unchanged.
- Two places the UI *wants* a small backend addition (risk score adjust,
  blocker assignment — OQ-6): flagged as decisions, not made as part of
  frontend work. If approved they'd be new small functions with their own
  tests, not edits to existing tested functions.

---

## 6. Open Questions

**OQ-1 — Auth approach. ✅ APPROVED as proposed** (additive `002_auth.sql`
+ signed-cookie sessions + `api/bootstrap.py`). The bootstrap seeds a
"platform" client row for the first platform_admin; a code comment will note
that platform_admin's client_id scoping is a v1 simplification to revisit if
multi-tenant is ever built.

**OQ-2 — EVM detail in Tier 1 off_track_alert cards. ✅ APPROVED with one
addition**: breached metric vs threshold inline; PV/EV/AC behind one expand
click; **but `cost_data_complete=false` always renders as a visible inline
badge regardless of alert type or expand state** — it is the flag built to
stop a falsely-reassuring CV going unnoticed, so it can never sit behind a
click a reviewer might not open.

**OQ-3 — clarification-item volume. ✅ APPROVED as recommended** (grouped by skill+run, per-item resolution, no batch resolve).

Original question:  Task Breakdown on a real scope can
raise 20+ clarifications at once (observed in the eval). Group them into one
collapsible "clarifications from this run" cluster with per-item resolve, or
render flat? Proposal: grouped by `created_by_skill` + run, still resolved
individually (no batch resolve, per the rubber-stamping rule).

**OQ-4 — `as_of` date control. ✅ APPROVED**: the "Run cycle" control
includes the `as_of` simulation-date picker, defaulting to today, labeled
"simulation date — testing only".

**OQ-5 — Queue refresh. ✅ APPROVED as recommended** (manual refresh button + last-refreshed timestamp, no polling).

Original question:  Manual refresh button (proposed) vs. 10s polling
on the review-queue page?

**OQ-6 — Two small backend additions. ✅ APPROVED as option (b)**: new
`src/` functions (`risk_tracking.adjust_score`, a blockers assign/resolve
helper), each writing through audit_log with a real human actor recorded,
each with its own tests. Neither becomes a new review_queue.item_type —
they are actions taken while reviewing an existing Tier 1 item, not new
tiered decisions. No raw `api/`-level updates.

**OQ-7 — Member-role permissions. ✅ APPROVED as recommended** (members: full read visibility, submit status reports + meetings, no writes/resolutions).

Original question:  Proposal above: `member` can submit
status reports + meetings, read everything, resolve nothing, edit nothing.
The PRD doesn't specify member visibility of e.g. audit logs — any
restrictions you want beyond "can't write"?

**OQ-8 — Retrospective/comms markdown. ✅ APPROVED as recommended** (plain preformatted text; approved bytes = versioned bytes).

Original question:  Sonnet drafts may contain markdown.
Render as markdown (needs a renderer dependency in `frontend/` only) or
display as plain text? Proposal: plain `<pre>`-style text for v1 — what the
reviewer approves is exactly the bytes that get versioned.

---

Stopping here. No scaffolding, no code, until this plan is reviewed.

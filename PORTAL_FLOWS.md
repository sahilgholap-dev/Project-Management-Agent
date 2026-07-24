# NEXUS PM Agent — Portal User Flows & Agent Flowcharts

This document maps (1) the user flows through the two portals built on top of
the FastAPI backend, and (2) how the agent — the orchestrated skill graph in
`src/` — actually runs. Sources of truth: `api/` routes, `frontend/src/app/`
pages, `src/orchestrator/graph.py`, `src/governance/`.

---

## 1. Roles & entry

Three roles, one login page, three mutually exclusive portals:

| Role | Portal | Can do |
|---|---|---|
| `platform_admin` | **Admin portal** (`/admin/*`) | Manage companies, users, and any company's config. No access to client project data (API returns 403). |
| `client_admin` | **Client portal** (`/`) | Everything: config, projects, team (incl. linking logins to roster rows), review queue, registers, close path. |
| `member` | **My Work portal** (`/my`) | Their own tasks/timelines/blockers (via the `team_members.user_id` login link) and self-only status updates. No management surface — every other endpoint returns 403. |

```mermaid
flowchart TD
    L[/"/login"/] -->|POST /auth/login| S{Session cookie set.<br/>What role?}
    S -->|platform_admin| A["/admin/companies"]
    S -->|client_admin| C["/ (client portal)"]
    S -->|member| M["/my (My Work portal)"]
    S -->|bad credentials| L
    A -.->|tries another portal| A2[redirected back]
    C -.->|tries another portal| C2[redirected back]
    M -.->|tries another portal| M2[redirected back]
```

### 1b. My Work portal (`member`) — flow

```mermaid
flowchart TD
    LI([Member logs in → /my]) --> LK{Login linked to a<br/>team_members row?}
    LK -->|no| ES["Empty state: 'ask your admin' —<br/>client_admin links it on /team"]
    LK -->|yes| W["My tasks per active project:<br/>dates, critical-path flags, status<br/>+ my timeline (Gantt w/ deadline)<br/>+ blockers involving me"]
    W --> U["Quick update on a task:<br/>Mark done (hours) / Update progress (%) / Blocked"]
    U --> SR["Files a STATUS REPORT (self-only,<br/>enforced server-side) — never a<br/>direct task write"]
    SR --> PC["Task shows 'update pending' until the<br/>next monitoring cycle parses it —<br/>ambiguity flagged, hours feed EVM"]
```

Notes:
- First successful login flips a user from `invited` → `active`.
- A `disabled` user's session is rejected at the API (401) — the admin
  disable action takes effect immediately.
- The Next.js middleware only checks cookie presence; **the API is the real
  permission boundary** (`require_role` on every endpoint).

---

## 2. Admin portal user flow (`platform_admin`)

The platform admin's job is onboarding: create the company, create its users,
hand credentials over manually, optionally pre-fill the company's config.

```mermaid
flowchart TD
    B([Bootstrap seeds the first<br/>platform_admin account]) --> LI[Login → /admin/companies]

    subgraph Companies ["/admin/companies"]
        LI --> CL[Company table:<br/>name · user count · project count]
        CL --> CC[Create company]
        CL --> OPEN[Open a company]
    end

    subgraph Detail ["/admin/companies/[id]"]
        OPEN --> REN[Rename]
        OPEN --> DEL{Delete?}
        DEL -->|company is empty| GONE[Deleted]
        DEL -->|has users or projects| REFUSED[409 refused —<br/>history is never deleted]
        OPEN --> CU[Create user in this company<br/>role: client_admin or member]
        CU --> CRED[/Credentials generated &<br/>SHOWN EXACTLY ONCE/]
        CRED --> HAND[Manual handoff — the system<br/>has no send capability, by design]
        OPEN --> CFG[Edit company config<br/>same validate-on-every-save<br/>contract as the client portal]
    end

    subgraph Users ["/admin/users (all companies)"]
        LI --> UL[User table:<br/>user · company · role · status]
        UL --> ED[Edit name / role]
        UL --> DIS[Disable / enable<br/>disable blocks login instantly]
        UL --> RP[Reset password]
        RP --> CRED2[/New password<br/>SHOWN EXACTLY ONCE/]
        UL --> CU2[Create user — company<br/>picked from a dropdown]
    end
```

Guarantees enforced by the backend (and tested):
- Plaintext passwords exist **only** in the one HTTP response — never stored,
  never audited, never sent anywhere.
- `platform_admin` accounts cannot be created, edited, or reset through the
  portal — bootstrap only.
- Users are never hard-deleted; companies only while empty. Audit history
  survives everything.

---

## 3. Client portal user flow (`client_admin` / `member`)

The full loop from an empty account to an archived project:

```mermaid
flowchart TD
    LI([Login → /]) --> CFG["/config — client_admin saves the<br/>operational config (cadences, skill depths,<br/>reviewers, approvers, calendar, thresholds).<br/>Backend validates on EVERY save;<br/>defects come back as a 422 list."]
    CFG --> TEAM["/team — add team members<br/>(skills, roles) and stakeholders"]
    TEAM --> NEW["/ — create project<br/>(scope document, timeline, budget)"]
    NEW --> ONB[Onboard project →<br/>agent runs the onboarding graph]
    ONB -->|clarification needed| Q1[clarification items land<br/>in the review queue]
    ONB -->|plan built| PROJ["/projects/[id] — phases, tasks,<br/>critical path, Gantt timeline"]

    PROJ --> INPUTS[Ongoing inputs]
    INPUTS --> ST["/projects/[id]/status —<br/>submit status reports"]
    INPUTS --> MT["/projects/[id]/meetings —<br/>upload transcripts"]
    INPUTS --> CYC[Run monitoring cycle<br/>as-of a chosen date]

    CYC --> RQ["/review-queue — every agent output<br/>that needs a human lands here,<br/>grouped by tier"]
    RQ --> T1["Tier 1 — approve/reject<br/>(alerts, slips, clarifications)"]
    RQ --> T2["Tier 2 — edit then approve<br/>(comms drafts, status reports, retros)"]
    RQ --> T3["Tier 3 — formal sign-off with retype gate<br/>(change requests, sign-off packets)"]

    PROJ --> REG[Registers]
    REG --> RISKS["/projects/[id]/risks"]
    REG --> BLK["/projects/[id]/blockers"]
    REG --> LOGS["/projects/[id]/logs —<br/>escalations + audit trail"]

    PROJ --> CLOSE["/projects/[id]/close"]
    CLOSE --> RETRO[Trigger retrospective → Tier 2 item]
    RETRO --> APPR[Reviewer edits & approves it]
    APPR --> ARCH{Archive}
    ARCH -->|retro approved| DONE([Project archived])
    ARCH -->|retro missing/unapproved| REF[409 — backend refuses,<br/>refusal shown verbatim]
```

Deliberate UX properties: no auto-polling (manual Refresh keeps cause→effect
visible), no optimistic UI (every render is post-mutation truth from SQLite),
no batch approve (each item is resolved individually).

---

## 4. How the agent works

"The agent" is not one loop — it is two LangGraph state graphs over
deterministic skills, with Sonnet used only where language understanding is
required (extraction, explanation, drafting). **Sonnet never decides dates,
assignments, or approvals** — those are code (`src/lib/` scheduling, EVM,
task-graph math) or humans (the review queue).

### 4.1 Onboarding graph — runs once per project

```mermaid
flowchart LR
    START([POST /projects/id/onboard]) --> TB["task_breakdown<br/>scope doc → phases → tasks<br/>(Sonnet proposes, code validates)"]
    TB -->|halted: scope too ambiguous| HALT([Halt — clarification items<br/>queued for the reviewer])
    TB -->|plan ok| AS["assignment_engine<br/>skill-match / balanced-workload<br/>(pure code, no LLM)"]
    AS -->|unassignable tasks| UQ[unassignable_task items → queue]
    AS --> END([Project live: phases, tasks,<br/>schedule, critical path])
```

### 4.2 Monitoring cycle — runs on demand (or per cadence)

```mermaid
flowchart TD
    START([Run cycle as-of a date]) --> PG{pause_gate:<br/>is the project paused?}
    PG -->|paused| ESC
    PG -->|active| ST

    ST["status_tracking<br/>parse status reports (Sonnet),<br/>detect off-track vs thresholds (code)"] --> RK
    RK["risk_tracking<br/>rule-based scans + Sonnet pattern scan,<br/>duplicate-check before queueing"] --> SL
    SL["dependency_manager<br/>detect slips, recompute schedule (code);<br/>Sonnet only explains the diff"] --> ESC
    ESC["escalation check<br/>(see ladder below)"] --> CD{comms due<br/>per cadence?}
    CD -->|yes| CM["stakeholder_comms<br/>draft update (Sonnet) → Tier 2 item.<br/>NEVER autonomous, by config schema"]
    CD -->|no| LOG
    CM --> LOG["audit log: one entry per cycle<br/>with every skill's summary"]
    LOG --> END([Cycle done — outputs are<br/>review-queue items, not actions])
```

Key invariant: **when a project is paused, nothing runs except the
escalation check** — the agent never quietly keeps working on paused work.

### 4.3 Governance: tiers and the escalation ladder

Every skill output that needs a human becomes a `review_queue` item. The
item's tier is **frozen to its type** (not configurable — the one deliberate
exception to config-not-code):

| Tier | Resolution | Item types |
|---|---|---|
| 1 | Approve / reject | `risk_alert`, `off_track_alert`, `infeasible_plan`, `unassignable_task`, `slip_impact`, `clarification` |
| 2 | Edit, then approve | `comms_draft`, `status_report`, `retrospective` |
| 3 | Formal packet + explicit sign-off | `change_request`, `signoff_packet` |

Unresolved items climb a ladder; the terminal state is a **paused project**,
never a silent auto-approval:

```mermaid
flowchart TD
    NEW[Item created → pending] --> P[primary reviewer notified]
    P -->|resolved in time| OK([Resolved — outcome audited])
    P -->|escalation delay elapses| B{backup reviewer<br/>configured?}
    B -->|yes| BN[backup notified]
    B -->|no| PAUSE
    BN -->|resolved| OK
    BN -->|delay elapses again| PAUSE["WORK PAUSED<br/>project status = paused,<br/>banner shown, only the escalation<br/>check keeps running"]
    PAUSE -->|human resolves the item| RESUME([Resume via /projects/id])
```

### 4.4 Agent catalog — every skill and what it does

All nine skills plus the governance layer, grouped by what kind of "brain"
each one has. Solid arrows are data flow; every human-facing output funnels
through the review queue — no skill acts on its own output.

```mermaid
flowchart TB
    subgraph IN [Inputs]
        SCOPE[Scope document]
        SRPT[Status reports<br/>free-text, manual entry]
        TRANS[Meeting transcripts]
        DB[(Project data:<br/>tasks, dates, capacity)]
    end

    subgraph LLM ["LLM reasoning (Claude Sonnet)"]
        TB2["task_breakdown (8.1)<br/>scope → phases → tasks, two passes;<br/>ambiguity halts & raises clarifications"]
        MS["meeting_summary (8.7)<br/>transcript → decisions / action items / blockers;<br/>action items become linked tasks"]
        SC["stakeholder_comms (8.8)<br/>drafts updates — DRAFT-ONLY,<br/>never autonomous, a human sends"]
        EXPL["llm/explainers<br/>plain-language summary of slip diffs —<br/>explains numbers, never decides them"]
    end

    subgraph HYB ["Hybrid (Sonnet parses/scans, code decides)"]
        ST2["status_tracking (8.4)<br/>Sonnet parses free text → structured status;<br/>EVM variance & threshold math is pure code;<br/>unclear replies flagged ambiguous, never guessed"]
        RT["risk_tracking (8.5)<br/>rule pass: EVM breaches, over-allocation;<br/>Sonnet pass: pattern scan of notes;<br/>duplicate-check before inserting"]
    end

    subgraph CODE ["Deterministic — plain code, NO LLM (guardrail-tested)"]
        SCH["scheduler (8.2)<br/>Critical Path Method on the working<br/>calendar; slack, critical path;<br/>infeasible plan → Tier 1"]
        AE["assignment_engine (8.3)<br/>greedy skill-and-capacity match,<br/>time-phased across ALL projects;<br/>never over-allocates"]
        DM["dependency_manager (8.6)<br/>slip detected → re-walk graph,<br/>re-schedule affected tasks, diff dates"]
        BLK2["blockers (OQ-6)<br/>assign resolution owner / resolve —<br/>human actions, audited"]
    end

    subgraph GOV ["Governance (code, no LLM)"]
        RQ2["review_queue<br/>the ONLY write path for items;<br/>tier frozen by item type;<br/>resolution requires a live human"]
        ESC2["escalation<br/>primary → backup → WORK PAUSED;<br/>silence never approves anything"]
        FRM["forms<br/>Tier 3 change requests & sign-off packets —<br/>human-initiated only, no skill creates them"]
        AUD["audit log<br/>every action, human or agent,<br/>with input/output summaries"]
    end

    SCOPE --> TB2 --> SCH --> AE
    TRANS --> MS --> TB2
    MS --> RT
    SRPT --> ST2 --> RT
    DB --> SCH & AE & DM
    DM --> EXPL
    ST2 & RT & DM & TB2 & AE & SCH -->|Tier 1 items| RQ2
    MS -.->|blockers register| BLK2
    SC -->|Tier 2 drafts| RQ2
    FRM -->|Tier 3 packets| RQ2
    RQ2 --> ESC2
    RQ2 & BLK2 & ESC2 --> AUD
```

| Agent / module | PRD § | Brain | Functionality | Raises |
|---|---|---|---|---|
| `task_breakdown` | 8.1 | Sonnet | Scope → phases, then phase → tasks (strictly two passes). Validation failure or model refusal **halts** — nothing silently patched. | Tier 1 `clarification`, halt |
| `scheduler` | 8.2 | Code | Critical Path Method in working-day math on the client calendar; writes planned dates, slack, critical path. | Tier 1 `infeasible_plan` |
| `assignment_engine` | 8.3 | Code | Greedy skills+capacity match, time-phased and cross-project; refuses tasks with no window or no qualifying candidate. | Tier 1 `unassignable_task` |
| `status_tracking` | 8.4 | Hybrid | Sonnet parses free-text reports into structured status; EVM variance vs thresholds is pure code. | Tier 1 `off_track_alert`, ambiguous flags |
| `risk_tracking` | 8.5 | Hybrid | Rule pass (EVM breach, over-allocation) + Sonnet pattern scan of meeting/status text; dedup before insert. | Tier 1 `risk_alert` |
| `dependency_manager` | 8.6 | Code | On a slip: re-walk the dependency graph, re-run scheduling for affected tasks, diff the dates. Sonnet only *explains* the diff (`explainers`). | Tier 1 `slip_impact` |
| `meeting_summary` | 8.7 | Sonnet | Transcript → decisions, action items, blockers; work-implying action items become linked tasks (effort left NULL for a human). | Register rows, downstream flags |
| `stakeholder_comms` | 8.8 | Sonnet | Drafts stakeholder updates per cadence/voice config. Draft-only: no send capability exists in the codebase. | Tier 2 `comms_draft` |
| `blockers` | OQ-6 | Code | Assign a resolution owner / resolve a blocker — human actions taken from the queue, audited with a real actor. | — |
| `governance/review_queue` | 10 | Code | Sole write path for review items; tier frozen by type; only a human resolves. | — |
| `governance/escalation` | 10, 16 | Code | Silence ladder: primary → backup → pause project. Never auto-approves. | `escalation_log`, pause |
| `governance/forms` | 10 | Code | Change requests & sign-off packets, human-initiated only. | Tier 3 items |

Cross-cutting rules the flowcharts rely on:
- **Everything is audited** (`audit_log`): who did it, input and output
  summaries — including every admin-portal action, with the human as actor.
- **No outbound send exists anywhere** — enforced by an import allowlist and
  tests; "sending" a comms draft means a human copies the approved text.
- **Skill depth** (`manual` / `assisted` / `autonomous`) is per-skill config,
  except `stakeholder_comms`, which can never be `autonomous`.

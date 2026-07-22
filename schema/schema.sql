-- NEXUS PM Agent — initial schema (DATABASE_SCHEMA.md rev 2, approved 2026-07-22)
-- SQLite. Applied by src/db.py as migration version 1; later changes go in
-- schema/migrations/NNN_*.sql (forward-only).
--
-- Single-client build (PRD §1): exactly one clients row in v1. client_id FKs are
-- kept on client-scoped tables so multi-tenant can be added later (PRD §14).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 1. Identity & onboarding (PRD §4)
-- ---------------------------------------------------------------------------

CREATE TABLE clients (
    client_id       INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE users (
    user_id         INTEGER PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(client_id),
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('platform_admin','client_admin','member')),
    invite_status   TEXT NOT NULL DEFAULT 'invited'
                    CHECK (invite_status IN ('invited','active','disabled')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- 2. Configuration (PRD §5)
-- ---------------------------------------------------------------------------

CREATE TABLE client_config (
    client_id                 INTEGER PRIMARY KEY REFERENCES clients(client_id),

    about_client              TEXT,
    project_definition        TEXT,
    reporting_cadence         TEXT NOT NULL
                              CHECK (reporting_cadence IN ('daily','weekly','biweekly')),
    comms_cadence             TEXT
                              CHECK (comms_cadence IN ('daily','weekly','biweekly')),
    skill_depth               TEXT NOT NULL,   -- JSON: skill name -> depth; stakeholder_comms may never be 'autonomous' (validator-enforced)
    tools_channels            TEXT,            -- JSON; informational in v1 (no integrations)
    primary_reviewer_id       INTEGER NOT NULL REFERENCES users(user_id),
    backup_reviewer_id        INTEGER REFERENCES users(user_id),
    escalation_delay_hours    REAL NOT NULL,
    escalation_delay_by_tier  TEXT,            -- JSON: {"1": hours, "2": hours, "3": hours}, optional
    change_approver_id        INTEGER NOT NULL REFERENCES users(user_id),
    signoff_approver_id       INTEGER NOT NULL REFERENCES users(user_id),
    voice_style               TEXT,
    working_calendar          TEXT NOT NULL,   -- JSON: {"workdays":[1..5],"holidays":[...],"hours_per_day":8}
    assignment_strategy       TEXT NOT NULL
                              CHECK (assignment_strategy IN ('best_skill_match','balanced_workload')),
    slip_threshold_days       REAL NOT NULL,

    updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE projects (
    project_id        INTEGER PRIMARY KEY,
    client_id         INTEGER NOT NULL REFERENCES clients(client_id),
    name              TEXT NOT NULL,
    scope_summary     TEXT,
    scope_document    TEXT,            -- plain text for v1 (confirmed Q15)
    budget_total      REAL,
    timeline_start    TEXT,
    timeline_end      TEXT,
    status            TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('intake','active','paused','closed','archived')),
    paused_reason     TEXT,
    config_overrides  TEXT NOT NULL DEFAULT '{}',  -- JSON; resolution: project override first, client default otherwise
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- 3. Core PM data (PRD §6, §8, §9)
-- ---------------------------------------------------------------------------

CREATE TABLE phases (
    phase_id        INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(project_id),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    planned_start   TEXT NOT NULL,
    planned_end     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned','in_progress','done','on_hold')),
    sequence_order  INTEGER NOT NULL,
    needs_clarification TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, sequence_order)
);

CREATE TABLE team_members (
    member_id        INTEGER PRIMARY KEY,
    client_id        INTEGER NOT NULL REFERENCES clients(client_id),  -- §9: one shared roster per client, never per project
    user_id          INTEGER REFERENCES users(user_id),
    name             TEXT NOT NULL,
    role             TEXT NOT NULL,
    skill_tags       TEXT NOT NULL DEFAULT '[]',  -- JSON array
    capacity_hrs     REAL NOT NULL DEFAULT 40,    -- weekly; prorated down in holiday weeks by lib/allocation.py
    allocated_hrs    REAL NOT NULL DEFAULT 0,     -- current-ISO-week concurrent load, DISPLAY CACHE ONLY (never a decision input)
    is_active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE tasks (
    task_id          INTEGER PRIMARY KEY,
    phase_id         INTEGER NOT NULL REFERENCES phases(phase_id),
    project_id       INTEGER NOT NULL REFERENCES projects(project_id),  -- denormalized for the cross-project capacity query (confirmed Q14)
    title            TEXT NOT NULL,
    description      TEXT,
    effort_hours     REAL,                        -- NULL = no confirmed estimate (e.g. converted from a meeting
                                                  -- action item): Scheduler/Assignment Engine refuse-and-flag,
                                                  -- same treatment as a NULL planned window (NEW-OQ 4 principle)
    skill_tags       TEXT NOT NULL DEFAULT '[]',  -- JSON array
    owner_id         INTEGER REFERENCES team_members(member_id),
    planned_start    TEXT,                        -- dateless task: Assignment Engine refuses + flags (confirmed NEW-OQ 4)
    planned_end      TEXT,
    actual_start     TEXT,
    actual_end       TEXT,
    status           TEXT NOT NULL DEFAULT 'todo'
                     CHECK (status IN ('todo','in_progress','blocked','done','cancelled')),
    percent_complete REAL CHECK (percent_complete BETWEEN 0 AND 100),
    slack_days       REAL,
    on_critical_path INTEGER NOT NULL DEFAULT 0,
    unassignable     INTEGER NOT NULL DEFAULT 0,
    needs_clarification TEXT,
    source_action_item_id INTEGER REFERENCES meeting_action_items(action_item_id),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_tasks_owner_window ON tasks (owner_id, planned_start, planned_end);

CREATE TABLE task_dependencies (
    predecessor_task_id INTEGER NOT NULL REFERENCES tasks(task_id),
    successor_task_id   INTEGER NOT NULL REFERENCES tasks(task_id),
    PRIMARY KEY (predecessor_task_id, successor_task_id),
    CHECK (predecessor_task_id <> successor_task_id)
) WITHOUT ROWID;

CREATE TABLE status_reports (
    report_id       INTEGER PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(task_id),
    member_id       INTEGER NOT NULL REFERENCES team_members(member_id),
    raw_text        TEXT NOT NULL,
    parsed_status   TEXT CHECK (parsed_status IN ('todo','in_progress','blocked','done','cancelled')),
    parsed_percent_complete REAL CHECK (parsed_percent_complete BETWEEN 0 AND 100),
    parsed_hours_spent REAL,                     -- feeds EVM Actual Cost: reported hours, never fabricated accrual
    is_ambiguous    INTEGER NOT NULL DEFAULT 0,
    received_at     TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at    TEXT
);

CREATE TABLE risks_issues (
    risk_id        INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(project_id),
    kind           TEXT NOT NULL CHECK (kind IN ('risk','issue')),
    title          TEXT NOT NULL,
    description    TEXT,
    severity       INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5),
    likelihood     INTEGER NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
    score          INTEGER GENERATED ALWAYS AS (severity * likelihood) STORED,
    status         TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','mitigating','closed')),
    source         TEXT NOT NULL CHECK (source IN ('rule_based','pattern_detected')),
    related_task_id INTEGER REFERENCES tasks(task_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE meetings (
    meeting_id    INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(project_id),  -- per-project uploads only (confirmed Q19)
    meeting_date  TEXT,
    raw_transcript TEXT NOT NULL,
    decisions     TEXT NOT NULL DEFAULT '[]',  -- JSON: [{"decision":..., "decided_by":...}]
    uploaded_by   INTEGER REFERENCES users(user_id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE meeting_action_items (
    action_item_id    INTEGER PRIMARY KEY,
    meeting_id        INTEGER NOT NULL REFERENCES meetings(meeting_id),
    description       TEXT NOT NULL,
    owner_id          INTEGER REFERENCES team_members(member_id),
    due_date          TEXT,
    converted_task_id INTEGER REFERENCES tasks(task_id),
    status            TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','done','converted')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE blockers (
    blocker_id    INTEGER PRIMARY KEY,
    project_id    INTEGER NOT NULL REFERENCES projects(project_id),
    description   TEXT NOT NULL,
    raised_by     INTEGER REFERENCES team_members(member_id),
    assigned_to   INTEGER REFERENCES team_members(member_id),   -- distinct from raised_by (§9); NULL + reviewer flag if unclear
    blocked_member_id INTEGER REFERENCES team_members(member_id),
    task_id       INTEGER REFERENCES tasks(task_id),
    meeting_id    INTEGER REFERENCES meetings(meeting_id),
    status        TEXT NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open','resolved')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at   TEXT
);

CREATE TABLE stakeholders (
    stakeholder_id INTEGER PRIMARY KEY,
    client_id      INTEGER NOT NULL REFERENCES clients(client_id),
    project_id     INTEGER REFERENCES projects(project_id),   -- NULL = client-wide (confirmed Q13)
    name           TEXT NOT NULL,
    email          TEXT,
    audience_type  TEXT NOT NULL
                   CHECK (audience_type IN ('team','exec','client','investor'))
);

-- ---------------------------------------------------------------------------
-- 4. Governance & audit (PRD §10, §13)
-- ---------------------------------------------------------------------------

-- Structural enforcement of "nothing auto-approved at Tier >= 1" (PRD §10/§15):
--   * only tiers 1-3 exist here; Tier 0 actions go straight to audit_log
--   * no 'auto_approved' status exists in the enum
--   * approved/rejected requires a non-null human resolved_by (CHECK below)
CREATE TABLE review_queue (
    item_id        INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(project_id),
    tier           INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    item_type      TEXT NOT NULL CHECK (item_type IN (
                       'risk_alert',
                       'off_track_alert',
                       'infeasible_plan',
                       'unassignable_task',
                       'slip_impact',
                       'clarification',
                       'comms_draft',
                       'status_report',
                       'retrospective',
                       'change_request',
                       'signoff_packet'
                   )),
    payload        TEXT NOT NULL,   -- JSON
    created_by_skill TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','approved','rejected','escalated','paused')),
    resolved_by    INTEGER REFERENCES users(user_id),
    resolved_at    TEXT,
    reviewer_notes TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),

    CHECK (status NOT IN ('approved','rejected') OR resolved_by IS NOT NULL)
);

CREATE TABLE escalation_log (
    escalation_id  INTEGER PRIMARY KEY,
    item_id        INTEGER NOT NULL REFERENCES review_queue(item_id),
    stage          TEXT NOT NULL CHECK (stage IN ('primary_notified','backup_notified','work_paused')),
    reason         TEXT NOT NULL,
    outcome        TEXT,
    occurred_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE change_requests (
    change_request_id INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(project_id),
    title          TEXT NOT NULL,
    description    TEXT,
    requested_by   INTEGER NOT NULL REFERENCES users(user_id),  -- always human-initiated in v1 (confirmed Q17)
    status         TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft','pending_approval','approved','rejected')),
    review_item_id INTEGER REFERENCES review_queue(item_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE signoff_packets (
    packet_id      INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(project_id),
    title          TEXT NOT NULL,
    content        TEXT,
    status         TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft','pending_signoff','signed_off','rejected')),
    review_item_id INTEGER REFERENCES review_queue(item_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE artifact_versions (
    version_id     INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(project_id),
    artifact_type  TEXT NOT NULL CHECK (artifact_type IN
                       ('status_report','risk_register','signoff_packet','comms_message','retrospective')),
    artifact_ref   INTEGER,
    version_number INTEGER NOT NULL,
    content        TEXT NOT NULL,
    created_by     INTEGER REFERENCES users(user_id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (artifact_type, artifact_ref, version_number)
);

CREATE TABLE audit_log (
    audit_id       INTEGER PRIMARY KEY,
    project_id     INTEGER REFERENCES projects(project_id),
    skill          TEXT NOT NULL,
    action         TEXT NOT NULL,
    input_summary  TEXT,   -- JSON summary + artifact references, never full bodies (confirmed Q16)
    output_summary TEXT,   -- JSON
    actor          TEXT NOT NULL DEFAULT 'agent',
    occurred_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

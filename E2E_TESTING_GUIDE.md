# NEXUS PM Agent — End-to-End Testing Guide

A complete manual walkthrough: bootstrap → admin portal → client config →
team → project onboarding → monitoring cycles → review queue (all 3 tiers) →
escalation/pause → close path → archive. All sample data (config values,
scope document, status reports, meeting transcript) is included — copy/paste
as you go.

> **LLM calls are real.** Onboarding, status parsing, risk scans, meeting
> extraction, comms drafts, and the retrospective call Claude Sonnet. Set
> `ANTHROPIC_API_KEY` in the backend's environment before starting. Skills
> marked "no LLM" (scheduler, assignment, slips, escalation) work without it,
> but the walkthrough assumes the key is set.

---

## 0. Setup & start (three terminals)

Start from a clean slate (optional but recommended for a full test):

```powershell
cd "D:\SAHIL GHOLAP\NEXUS\Project-Management-Agent"
Remove-Item nexus.db -ErrorAction SilentlyContinue
```

**Terminal 1 — bootstrap once, then run the API:**

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # your key
python -m api.bootstrap                  # prints platform-admin credentials ONCE — copy them!
python -m uvicorn api.main:app --port 8000
```

Bootstrap prints something like:
`email: platform-admin@nexus.local  password: xxxxxxxxxxxx`
This is shown exactly once (only the hash is stored). If you lose it, delete
`nexus.db` and re-bootstrap.

**Terminal 2 — frontend:**

```powershell
cd "D:\SAHIL GHOLAP\NEXUS\Project-Management-Agent\frontend"
npm install    # first time only
npm run dev    # http://localhost:3000
```

Open **http://localhost:3000** — you'll land on `/login`.

---

## 1. Admin portal — company & users

Log in with the bootstrap credentials → you land on **/admin/companies**.

1. **Create company**: `Acme Digital` → it appears in the table (0 users,
   0 projects). *(Multi-company check: create a second company `Beta Corp`
   too, and try creating `acme digital` — expect a duplicate-name error.)*
2. Open **Acme Digital** → **create two users**:
   - `priya@acme.test` / `Priya Sharma` / role `client_admin`
   - `rohan@acme.test` / `Rohan Mehta` / role `member`

   Each creation shows generated credentials **once** — copy both passwords
   now. (By design nothing is emailed; you are the manual handoff.)
3. **User management checks** (on `/admin/users`):
   - Edit Rohan's display name → saves.
   - **Disable** Rohan → try logging in as Rohan in a private window → 401.
     **Enable** him again → login works.
   - **Reset password** on Rohan → new password shown once; the old one no
     longer works.
4. **Safe-delete check**: try deleting Acme Digital → button is blocked/409
   (it has users). Delete the empty `Beta Corp` → succeeds.

Log out.

---

## 2. Client config (as Priya, client_admin)

Log in as `priya@acme.test` → client portal. Go to **Config** and enter:

| Field | Value |
|---|---|
| About client | `Acme Digital — a 15-person product studio building client-facing web tools.` |
| Project definition | `A project is a fixed-scope engagement with a signed scope document, a timeline under 3 months, and a named stakeholder.` |
| Reporting cadence | `weekly` |
| Comms cadence | `weekly` |
| Primary reviewer | `Priya Sharma (client_admin)` |
| Backup reviewer | `— none —` *(deliberate: tests the PRD §16 straight-to-pause path later)* |
| Change approver (Tier 3) | `Priya Sharma` |
| Sign-off approver (Tier 3) | `Priya Sharma` |
| Escalation delay (hours) | `0.1` *(= 6 minutes — deliberately tiny so you can watch the escalation ladder without waiting a day)* |
| Slip threshold (days) | `1` |
| Assignment strategy | `best_skill_match` |
| Voice / style | `Concise, plain English, no hype. Address the stakeholder by first name.` |
| Working calendar | Mon–Fri checked, Hours/day `8`, Holidays `2026-08-14` |
| Skill depth | leave defaults *(note stakeholder_comms has no "autonomous" option — by design)* |

**Validation check first**: try saving with Primary reviewer on "choose…" →
the save is rejected with a defect list rendered under the form. Fix it and
save → "✓ saved (validated)".

*(Also verify the admin side: log in as platform admin, open
`/admin/companies/[Acme]` → Configuration shows the same saved values and is
editable with the same validation.)*

---

## 3. Team (as Priya)

Go to **Team** and add members:

| Name | Role | Skills | Capacity hrs/wk |
|---|---|---|---|
| Dev A — Arjun | `eng` | `backend` | 40 |
| Dev B — Sneha | `eng` | `backend, frontend` | 40 |
| Design — Kavya | `design` | `design` | 20 |
| QA — Vikram | `qa` | `qa` | 30 |

Add one stakeholder: `Anil Kapoor` / `anil@client.test` / `Sponsor`.

---

## 4. Create & onboard the project

On the **Projects** page create:

- **Name**: `Customer Feedback Portal`
- **Timeline**: start `2026-07-27`, end `2026-08-28`
- **Budget**: `12000`
- **Scope document** (paste all of it):

```
Customer Feedback Portal — Scope Document

Goal: a small web portal where Acme's end-customers submit product feedback,
and Acme staff triage it.

In scope:
1. Feedback submission: a public form (title, category, description,
   optional screenshot upload) with spam protection. Submissions are stored
   with a unique reference number shown to the customer.
2. Triage dashboard: staff log in, see a filterable list of submissions
   (by category, status, date), and can change status
   (new / in-review / resolved / declined) and leave internal notes.
3. Email-free notifications: customers can check their submission status
   by reference number on a public status page (no accounts, no email).
4. Design: a lightweight brand-consistent UI for both the public form and
   the staff dashboard. Mobile-friendly for the public pages.
5. Quality: automated tests for submission and status-change flows, plus a
   pre-launch QA pass on the five most common browsers.

Out of scope: SSO, analytics dashboards, multi-language support.

Constraints: staff dashboard must sit behind the existing Acme auth proxy.
Deployment lands on Acme's existing VPS; no new infrastructure.
```

Click **Onboard** with as-of date `2026-07-27`.

**What to verify** (this exercises task_breakdown → scheduler → assignment):
- The project page shows phases (typically design / build / test-ish) with
  tasks, planned dates, owners, slack, and the critical path highlighted in
  the timeline. Dates skip weekends and the `2026-08-14` holiday.
- The **Review queue** may contain Tier 1 items already:
  - `clarification` — if the model flagged ambiguity in the scope,
  - `unassignable_task` — if some task's skills matched nobody (e.g. a
    devops-ish deploy task with no `devops` member — expected with this
    roster: it proves the never-over-allocate rule),
  - `infeasible_plan` — if the computed finish exceeded 2026-08-28.
- Resolve each Tier 1 item (approve or reject, one at a time — there is
  deliberately no batch approve).

---

## 5. Status reports → monitoring cycle #1

On **Projects → Customer Feedback Portal → Status**, submit three reports
against three different tasks (pick real tasks from the dropdowns; the member
is whoever owns the task):

1. *Clear, on-track*:
   `Finished the form layout and validation yesterday, everything is on plan. I'd say the task is fully done.`
2. *Clear, behind* (pick a task on the critical path):
   `Rough week — the spam-protection integration keeps failing in testing. I'm maybe 30% done and I originally planned to be finished by now.`
3. *Ambiguous* (should get flagged, never guessed):
   `Some progress, hard to say. Waiting on a couple of things.`

Then on the project page run **Cycle** with as-of `2026-08-03`.

**Verify**:
- The status inbox shows report 1 & 2 parsed and processed, report 3 flagged
  `ambiguous`.
- The queue gains Tier 1 `off_track_alert` (from report 2's variance breach)
  and possibly `risk_alert` items (rule pass on EVM; pattern pass on the
  free text).
- **Risks** register shows entries with source `rule_based` / `pattern`
  (duplicate-checked — run the cycle twice with the same date and confirm no
  duplicates appear).

---

## 6. Meeting upload → blockers

On **Meetings**, upload with date `2026-08-04`:

```
Weekly sync — Acme / portal team, Aug 4

Priya: Quick status. Form work slipped because of the spam-protection issue.
Arjun: Yes, the third-party captcha's API changed. I need a decision on
whether we buy the paid tier or build a honeypot ourselves.
Priya: Decision: we go with the honeypot approach, no new vendor spend.
Sneha: I'll take building the honeypot module, should be two days.
Kavya: Design review of the status page is done, no changes needed.
Vikram: I'm blocked on QA for the dashboard — I don't have access to the
Acme auth proxy staging environment, and nobody seems to own getting me in.
Priya: Noted, we need to sort that out.
Anil (sponsor): Please make sure the reference-number lookup is on the
launch checklist.
```

**Verify** (meeting_summary's three buckets):
- Decisions list includes the honeypot decision.
- An **action item** ("Sneha builds honeypot module") became a linked task
  with **no effort estimate** — scheduler/assignment refuse-and-flag it
  (Tier 1) until a reviewer supplies effort. That's by design.
- The proxy-access problem landed in **Blockers** with **no resolution
  owner** → a Tier 1 item asks for one. On the Blockers page, assign it to
  a member, later resolve it.

Run **Cycle** as-of `2026-08-05` again — dependency_manager picks up any
slipped critical-path task (from your "behind" report / late actual_end) and
raises a Tier 1 `slip_impact` with a plain-language explanation attached.

---

## 7. Escalation ladder → pause → resume

You set the escalation delay to 0.1h (6 min) with **no backup reviewer**:

1. Make sure at least one Tier 1 item sits unresolved in the queue.
2. Wait ~7 minutes, then run a **Cycle** (any date) — or hit the manual
   trigger: the escalation check runs inside every cycle.
3. First pass: the item logs `primary_notified`. After another 6+ minutes,
   cycle again: with no backup configured it goes **straight to work-paused**
   (PRD §16) — the project banner shows paused + reason, and its queue item
   shows status `paused`.
4. While paused, run a cycle and check the audit log: **nothing ran except
   the escalation check** (the pause gate).
5. Resolve the paused item, then click **Resume** on the project page.
   (Resume before resolving → 409, surfaced verbatim.)

---

## 8. Tier 2 & Tier 3

**Tier 2 (edit-then-approve)** — on the project page run **Cycle** as-of
`2026-08-10` with **draft comms** enabled (or wait for the weekly cadence
gate). A `comms_draft` lands in the queue: open it, **edit the draft text**,
approve — your edited text (not the draft) is what gets versioned as the
approved artifact. Nothing is ever sent; a human copies the approved text.

**Tier 3 (formal sign-off)** — on the project page create a **Change
request**: title `Add CSV export to triage dashboard`, description
`Sponsor requested a CSV export of filtered submissions; adds ~2 days QA+dev.`
It appears in the queue as a Tier 3 packet — approving requires the explicit
retype confirmation gate. Test **reject** on it (or a second one) too.

---

## 9. Close path → archive

1. On **Close**, trigger the retrospective with as-of `2026-08-28` → a
   Tier 2 `retrospective` item is generated from the project's actual history.
2. **Try Archive first** → 409 "archive refused: the retrospective has not
   been approved", shown verbatim. This is the governance gate working.
3. Open the retro in the queue, edit if you like, approve.
4. **Archive** again → project status `archived`; the approved retro is in
   **Artifacts**.

---

## 10. Cross-checks at the end

- **Audit log** (project → Logs): every step above has an entry — cycles
  with per-skill summaries, admin actions with a human actor, resolutions
  with `resolved_by`. No plaintext password appears anywhere.
- **Escalation log** shows the full ladder history from step 7.
- **Role checks**: log in as Rohan (member) — config is read-only, no
  create/approve buttons, but status-report submission works. Platform admin
  hitting `/` bounces to `/admin`; Priya hitting `/admin` bounces to `/`.
- **Per-project override** (Settings): set `{"slip_threshold_days": 3}` as a
  project override and check the resolved-config view shows it as
  "project override" while everything else stays "client default".

## Quick reset

```powershell
# stop the API first
Remove-Item nexus.db
python -m api.bootstrap
# restart uvicorn, log in with the freshly printed credentials
```

"use client";

// client_config editor (PRD section 5). The backend validates on EVERY save
// and returns the full defect list on 422 — rendered verbatim below the form
// (PRD section 16: defects are surfaced, never silently accepted).
// stakeholder_comms deliberately offers no "autonomous" option, mirroring
// the config schema (PRD 8.8: never a fully-automatic depth).

import { useRouter } from "next/navigation";
import { useState } from "react";

const SKILLS = [
  "task_breakdown", "scheduler", "assignment_engine", "status_tracking",
  "risk_tracking", "dependency_manager", "meeting_summary", "stakeholder_comms",
] as const;

const DEPTHS = ["manual", "assisted", "autonomous"] as const;
const CADENCES = ["daily", "weekly", "biweekly"] as const;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type UserRow = { user_id: number; display_name: string; role: string };

export type ConfigValue = Record<string, unknown> & {
  skill_depth?: Record<string, string>;
  working_calendar?: { workdays: number[]; holidays: string[]; hours_per_day: number };
  escalation_delay_by_tier?: Record<string, number> | null;
};

const DEFAULTS: ConfigValue = {
  about_client: "", project_definition: "", reporting_cadence: "weekly",
  comms_cadence: "biweekly",
  skill_depth: {
    task_breakdown: "assisted", scheduler: "autonomous",
    assignment_engine: "autonomous", status_tracking: "assisted",
    risk_tracking: "assisted", dependency_manager: "autonomous",
    meeting_summary: "assisted", stakeholder_comms: "assisted",
  },
  tools_channels: null, primary_reviewer_id: 0, backup_reviewer_id: null,
  escalation_delay_hours: 24, escalation_delay_by_tier: null,
  change_approver_id: 0, signoff_approver_id: 0, voice_style: "",
  working_calendar: { workdays: [1, 2, 3, 4, 5], holidays: [], hours_per_day: 8 },
  assignment_strategy: "best_skill_match", slip_threshold_days: 2,
};

export function ConfigForm({ initial, users }: {
  initial: ConfigValue | null;
  users: UserRow[];
}) {
  const router = useRouter();
  const [config, setConfig] = useState<ConfigValue>(initial ?? DEFAULTS);
  const [defects, setDefects] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function set(key: string, value: unknown) {
    setConfig((c) => ({ ...c, [key]: value }));
  }
  const calendar = config.working_calendar ?? DEFAULTS.working_calendar!;

  async function save() {
    setBusy(true);
    setDefects([]);
    setMessage(null);
    const body = { ...config };
    for (const key of ["about_client", "project_definition", "voice_style"]) {
      if (body[key] === "") body[key] = null;
    }
    const response = await fetch("/api/config", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!response.ok) {
      const detail = (await response.json().catch(() => null))?.detail;
      setDefects(detail?.defects ?? [typeof detail === "string" ? detail : "save failed"]);
      return;
    }
    setMessage("✓ saved (validated)");
    router.refresh();
  }

  const userSelect = (key: string, nullable: boolean) => (
    <select
      value={String(config[key] ?? "")}
      onChange={(e) => set(key, e.target.value === "" ? null : Number(e.target.value))}
      className="w-full rounded border px-2 py-1.5"
    >
      {nullable ? <option value="">— none —</option> : <option value="">choose…</option>}
      {users.map((u) => (
        <option key={u.user_id} value={u.user_id}>
          {u.display_name} ({u.role})
        </option>
      ))}
    </select>
  );

  const label = "block text-xs text-slate-500";
  const input = "w-full rounded border px-2 py-1.5";

  return (
    <div className="space-y-5 text-sm">
      <div className="grid grid-cols-2 gap-4">
        <label className={label}>About client
          <input className={input} value={String(config.about_client ?? "")}
                 onChange={(e) => set("about_client", e.target.value)} />
        </label>
        <label className={label}>Project definition (calibrates breakdown granularity)
          <input className={input} value={String(config.project_definition ?? "")}
                 onChange={(e) => set("project_definition", e.target.value)} />
        </label>
        <label className={label}>Reporting cadence
          <select className={input} value={String(config.reporting_cadence)}
                  onChange={(e) => set("reporting_cadence", e.target.value)}>
            {CADENCES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className={label}>Comms cadence (empty = ad-hoc only)
          <select className={input} value={String(config.comms_cadence ?? "")}
                  onChange={(e) => set("comms_cadence", e.target.value || null)}>
            <option value="">— none —</option>
            {CADENCES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label className={label}>Primary reviewer{userSelect("primary_reviewer_id", false)}</label>
        <label className={label}>Backup reviewer (PRD s16 covers unset){userSelect("backup_reviewer_id", true)}</label>
        <label className={label}>Change approver (Tier 3){userSelect("change_approver_id", false)}</label>
        <label className={label}>Sign-off approver (Tier 3){userSelect("signoff_approver_id", false)}</label>
        <label className={label}>Escalation delay (hours)
          <input type="number" min="0.1" step="0.5" className={input}
                 value={Number(config.escalation_delay_hours)}
                 onChange={(e) => set("escalation_delay_hours", Number(e.target.value))} />
        </label>
        <label className={label}>Slip threshold (days)
          <input type="number" min="0.1" step="0.5" className={input}
                 value={Number(config.slip_threshold_days)}
                 onChange={(e) => set("slip_threshold_days", Number(e.target.value))} />
        </label>
        <label className={label}>Assignment strategy
          <select className={input} value={String(config.assignment_strategy)}
                  onChange={(e) => set("assignment_strategy", e.target.value)}>
            <option>best_skill_match</option>
            <option>balanced_workload</option>
          </select>
        </label>
        <label className={label}>Voice / style (comms drafting)
          <input className={input} value={String(config.voice_style ?? "")}
                 onChange={(e) => set("voice_style", e.target.value)} />
        </label>
      </div>

      <fieldset className="rounded border p-3">
        <legend className="px-1 text-xs font-semibold text-slate-600">
          Per-tier escalation delay override (hours; blank = client default)
        </legend>
        <div className="flex gap-4">
          {[1, 2, 3].map((tier) => (
            <label key={tier} className={label}>Tier {tier}
              <input type="number" min="0.1" step="0.5" className={input}
                     value={config.escalation_delay_by_tier?.[String(tier)] ?? ""}
                     onChange={(e) => {
                       const byTier = { ...(config.escalation_delay_by_tier ?? {}) };
                       if (e.target.value === "") delete byTier[String(tier)];
                       else byTier[String(tier)] = Number(e.target.value);
                       set("escalation_delay_by_tier",
                           Object.keys(byTier).length ? byTier : null);
                     }} />
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="rounded border p-3">
        <legend className="px-1 text-xs font-semibold text-slate-600">Working calendar</legend>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex gap-2">
            {WEEKDAYS.map((day, i) => (
              <label key={day} className="text-xs">
                <input type="checkbox"
                       checked={calendar.workdays.includes(i + 1)}
                       onChange={(e) => {
                         const workdays = e.target.checked
                           ? [...calendar.workdays, i + 1].sort()
                           : calendar.workdays.filter((d) => d !== i + 1);
                         set("working_calendar", { ...calendar, workdays });
                       }} /> {day}
              </label>
            ))}
          </div>
          <label className={label}>Hours/day
            <input type="number" min="1" max="24" className={input}
                   value={calendar.hours_per_day}
                   onChange={(e) => set("working_calendar",
                     { ...calendar, hours_per_day: Number(e.target.value) })} />
          </label>
          <label className={`${label} flex-1`}>Holidays (comma-separated YYYY-MM-DD)
            <input className={input}
                   value={calendar.holidays.join(", ")}
                   onChange={(e) => set("working_calendar", {
                     ...calendar,
                     holidays: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                   })} />
          </label>
        </div>
      </fieldset>

      <fieldset className="rounded border p-3">
        <legend className="px-1 text-xs font-semibold text-slate-600">
          Skill depth (stakeholder_comms can never be autonomous — by design)
        </legend>
        <div className="grid grid-cols-4 gap-3">
          {SKILLS.map((skill) => (
            <label key={skill} className={label}>{skill}
              <select className={input}
                      value={config.skill_depth?.[skill] ?? "assisted"}
                      onChange={(e) => set("skill_depth",
                        { ...config.skill_depth, [skill]: e.target.value })}>
                {(skill === "stakeholder_comms"
                  ? DEPTHS.filter((d) => d !== "autonomous") : DEPTHS
                ).map((d) => <option key={d}>{d}</option>)}
              </select>
            </label>
          ))}
        </div>
      </fieldset>

      {defects.length > 0 && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-xs text-red-800">
          <p className="font-semibold">Config rejected — {defects.length} defect(s):</p>
          <ul className="list-disc pl-5">
            {defects.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy}
                className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "Validating…" : "Save (validates on every save)"}
        </button>
        {message && <span className="text-xs text-emerald-700">{message}</span>}
      </div>
    </div>
  );
}

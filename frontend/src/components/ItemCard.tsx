"use client";

// One card per review item, tier decides the interaction (plan section 2).
// Anti-rubber-stamping rules implemented here:
//  - nothing pre-selected; Approve and Reject carry equal visual weight
//  - Tier 2 approval sits BELOW the full content; edits become final_text
//    (resolve_item versions exactly what was approved)
//  - Tier 3 requires retyping the packet title before Approve enables
//  - no batch approve exists anywhere
//  - cost_data_complete=false renders as an ALWAYS-VISIBLE badge (OQ-2),
//    never behind the expand

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ReviewItem } from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  primary_notified: "primary notified",
  backup_notified: "backup notified",
  work_paused: "WORK PAUSED",
};

function Payload({ payload }: { payload: Record<string, unknown> }) {
  return (
    <pre className="max-h-64 overflow-auto rounded bg-slate-50 p-2 text-[11px] leading-4">
      {JSON.stringify(payload, null, 2)}
    </pre>
  );
}

function Tier1Summary({ item }: { item: ReviewItem }) {
  const p = item.payload as Record<string, any>;
  switch (item.item_type) {
    case "off_track_alert":
      return (
        <p>
          <strong>{String(p.metric).replace("_", " ")}</strong>{" "}
          {p.value_hours}h against a −{p.threshold_hours}h threshold
        </p>
      );
    case "slip_impact":
      return (
        <div className="space-y-1">
          {p.explanation ? (
            <p>{p.explanation}</p>
          ) : (
            <p>
              <strong>{p.slipped_task_title}</strong> slipped {p.slip_days} working
              day(s); project end moved {p.project_end_shift_days} day(s).
            </p>
          )}
        </div>
      );
    case "risk_alert":
      return (
        <p>
          <strong>{p.title}</strong> — severity {p.severity} × likelihood{" "}
          {p.likelihood} ({p.source}); scores are reviewer-adjustable in the
          risk register.
        </p>
      );
    case "unassignable_task":
      return <p><strong>{p.title}</strong>: {p.reason}</p>;
    case "infeasible_plan":
      return (
        <p>
          Computed finish <strong>{p.computed_finish}</strong> overruns the
          timeline ({p.timeline_end}) by {p.overrun_working_days} working day(s).
        </p>
      );
    default:
      return <p>{p.reason ?? item.item_type}</p>;
  }
}

export function ItemCard({ item, canResolve }: {
  item: ReviewItem;
  canResolve: boolean;
}) {
  const router = useRouter();
  const p = item.payload as Record<string, any>;
  const draft = typeof p.draft === "string" ? p.draft : null;
  const [notes, setNotes] = useState("");
  const [text, setText] = useState(draft ?? "");
  const [confirmTitle, setConfirmTitle] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = item.status === "pending" || item.status === "escalated"
    || item.status === "paused";
  const tier3Title: string = p.title ?? "";
  const tier3Unlocked = item.tier !== 3 || confirmTitle === tier3Title;

  async function resolve(decision: "approved" | "rejected") {
    setBusy(decision);
    setError(null);
    const body: Record<string, unknown> = { decision, notes: notes || null };
    if (item.tier === 2 && draft !== null && text !== draft) {
      body.final_text = text; // reviewer's edit — versioned on approval
    }
    const response = await fetch(`/api/review-queue/${item.item_id}/resolve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    setBusy(null);
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return;
    }
    router.refresh();
  }

  const decisionButtons = canResolve && open && (
    <div className="flex items-center gap-2 pt-2">
      {item.tier === 3 && (
        <input
          value={confirmTitle}
          onChange={(e) => setConfirmTitle(e.target.value)}
          placeholder={`Retype "${tier3Title}" to sign off`}
          className="w-64 rounded border px-2 py-1.5 text-xs"
        />
      )}
      <button
        onClick={() => resolve("approved")}
        disabled={busy !== null || !tier3Unlocked}
        className="rounded border border-slate-400 px-4 py-1.5 text-xs font-medium hover:bg-slate-100 disabled:opacity-40"
      >
        {busy === "approved" ? "…" : item.tier === 3 ? "Sign off" : "Approve"}
      </button>
      <button
        onClick={() => resolve("rejected")}
        disabled={busy !== null}
        className="rounded border border-slate-400 px-4 py-1.5 text-xs font-medium hover:bg-slate-100 disabled:opacity-40"
      >
        {busy === "rejected" ? "…" : "Reject"}
      </button>
      <input
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="notes (optional)"
        className="flex-1 rounded border px-2 py-1.5 text-xs"
      />
    </div>
  );

  return (
    <article className="rounded border bg-white p-4 text-sm">
      <header className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-slate-800 px-2 py-0.5 text-white">
          T{item.tier} · {item.item_type}
        </span>
        <span className="text-slate-400">
          #{item.item_id} · {item.created_by_skill} · {item.created_at}
        </span>
        <span className={`rounded px-2 py-0.5 ${
          item.status === "approved" ? "bg-emerald-100 text-emerald-800"
          : item.status === "rejected" ? "bg-slate-200 text-slate-600"
          : item.status === "paused" ? "bg-red-100 text-red-800"
          : "bg-amber-100 text-amber-800"
        }`}>
          {item.status}
        </span>
        {/* OQ-2: ALWAYS visible when cost data is incomplete — never behind a click */}
        {p.cost_data_complete === false && (
          <span className="rounded bg-red-600 px-2 py-0.5 font-semibold text-white">
            COST DATA INCOMPLETE — CV understated
          </span>
        )}
        {item.escalation_stages.map((s) => (
          <span key={s.stage}
                title={s.reason}
                className={`rounded border px-1.5 py-0.5 ${
                  s.stage === "work_paused"
                    ? "border-red-300 text-red-700" : "text-slate-500"
                }`}>
            {STAGE_LABELS[s.stage] ?? s.stage}
          </span>
        ))}
      </header>

      {item.tier === 2 && draft !== null ? (
        <div className="space-y-2">
          {/* OQ-8: plain preformatted text — approved bytes are versioned bytes */}
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={Math.min(16, Math.max(6, text.split("\n").length + 1))}
            readOnly={!canResolve || !open}
            className="w-full rounded border p-2 font-mono text-xs"
          />
          {text !== draft && (
            <p className="text-xs text-amber-700">
              Edited — approving sends your edited text as the final version.
            </p>
          )}
          {p.data_basis != null && (
            <details>
              <summary className="cursor-pointer text-xs text-slate-500">
                Data basis (trace every claim)
              </summary>
              <Payload payload={p.data_basis as Record<string, unknown>} />
            </details>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <Tier1Summary item={item} />
          <details>
            <summary className="cursor-pointer text-xs text-slate-500">
              {item.item_type === "off_track_alert"
                ? "Full EVM snapshot (PV / EV / AC)"
                : "Raw payload"}
            </summary>
            <Payload payload={item.payload} />
          </details>
        </div>
      )}

      {error && <p className="pt-2 text-xs text-red-600">{error}</p>}
      {decisionButtons}
      {!open && item.reviewer_notes && (
        <p className="pt-2 text-xs text-slate-500">notes: {item.reviewer_notes}</p>
      )}
    </article>
  );
}

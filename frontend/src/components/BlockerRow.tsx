"use client";

// Assign/resolve go through the audited OQ-6 endpoints
// (PATCH /blockers/{id} -> blockers.assign_blocker / resolve_blocker,
// human actor recorded). Unowned blockers render highlighted.

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Blocker } from "@/app/(client)/projects/[id]/blockers/page";

export function BlockerRow({ blocker, members, canEdit }: {
  blocker: Blocker;
  members: { id: number; name: string }[];
  canEdit: boolean;
}) {
  const router = useRouter();
  const [assignee, setAssignee] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const unowned = blocker.assigned_to === null && blocker.status === "open";

  async function patch(body: Record<string, unknown>) {
    setError(null);
    const response = await fetch(`/api/blockers/${blocker.blocker_id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return;
    }
    router.refresh();
  }

  return (
    <tr className={`border-b align-top last:border-0 ${unowned ? "bg-amber-50" : ""}`}>
      <td className="max-w-md px-4 py-2">
        {blocker.description}
        {error && <p className="text-red-600">{error}</p>}
      </td>
      <td className="px-2 py-2">{blocker.blocked_member_name ?? "—"}</td>
      <td className="px-2 py-2">{blocker.raised_by_name ?? "—"}</td>
      <td className="px-2 py-2">
        {blocker.assigned_to_name ?? (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
            unassigned
          </span>
        )}
      </td>
      <td className="px-2 py-2">
        {blocker.status}
        {blocker.resolved_at && (
          <span className="text-slate-400"> · {blocker.resolved_at}</span>
        )}
      </td>
      <td className="px-2 py-2">
        {canEdit && blocker.status === "open" && (
          <div className="flex items-center gap-1">
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}
                    className="rounded border px-1 py-0.5">
              <option value="">owner…</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            <button disabled={!assignee}
                    className="rounded border px-2 py-0.5 hover:bg-slate-100 disabled:opacity-40"
                    onClick={() => patch({ assigned_to: Number(assignee) })}>
              assign
            </button>
            <button className="rounded border px-2 py-0.5 hover:bg-slate-100"
                    onClick={() => patch({ resolve: true })}>
              resolve
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

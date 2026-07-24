"use client";

// Assign/resolve go through the audited OQ-6 endpoints
// (PATCH /blockers/{id} -> blockers.assign_blocker / resolve_blocker,
// human actor recorded). Unowned blockers render highlighted.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Td } from "@/components/ui";
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
    <tr className={`align-top ${unowned ? "bg-amber-50" : ""}`}>
      <Td className="max-w-md align-top text-slate-900">
        {blocker.description}
        {error && <p className="text-red-600">{error}</p>}
      </Td>
      <Td className="align-top text-slate-700">{blocker.blocked_member_name ?? "—"}</Td>
      <Td className="align-top text-slate-700">{blocker.raised_by_name ?? "—"}</Td>
      <Td className="align-top">
        {blocker.assigned_to_name ?? <Badge tone="warning">unassigned</Badge>}
      </Td>
      <Td className="align-top text-slate-700">
        {blocker.status}
        {blocker.resolved_at && (
          <span className="text-slate-400"> · {blocker.resolved_at}</span>
        )}
      </Td>
      <Td className="align-top">
        {canEdit && blocker.status === "open" && (
          <div className="flex items-center gap-1">
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}
                    className="rounded-md border border-slate-300 bg-white px-1.5 py-0.5 text-xs text-slate-900 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200">
              <option value="">owner…</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
            <Button variant="secondary" small disabled={!assignee}
                    onClick={() => patch({ assigned_to: Number(assignee) })}>
              assign
            </Button>
            <Button variant="secondary" small
                    onClick={() => patch({ resolve: true })}>
              resolve
            </Button>
          </div>
        )}
      </Td>
    </tr>
  );
}

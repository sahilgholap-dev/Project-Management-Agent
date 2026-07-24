"use client";

// Close path (PRD section 11): generate retrospective (Tier 2) -> a human
// reviews/edits/approves it in the queue -> only then does archive succeed.
// The archive button surfaces the backend's 409 refusal verbatim — the UI
// never works around it.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui";

export function CloseActions({ projectId, status, retroPending }: {
  projectId: number;
  status: string;
  retroPending: boolean;
}) {
  const router = useRouter();
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function post(label: string, path: string, body?: unknown) {
    setBusy(label);
    setMessage(null);
    const response = await fetch(`/api${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    setBusy(null);
    if (!response.ok) {
      const detail = data?.detail;
      setMessage(`✖ ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    } else if (label === "generate") {
      setMessage(`✓ retrospective drafted — review item #${data.review_item_id}` +
                 " is waiting in the queue (Tier 2)");
    } else {
      setMessage("✓ archived");
    }
    router.refresh();
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {status !== "closed" && status !== "archived" && (
          <>
            <label className="text-xs font-medium text-slate-600">
              as-of{" "}
              <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
                     className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" />
              <span className="ml-1 italic text-slate-500">(simulation date — testing only)</span>
            </label>
            <Button variant="primary" small disabled={busy !== null}
                    onClick={() => post("generate", `/projects/${projectId}/close`,
                                        { as_of: asOf })}>
              {busy === "generate" ? "Drafting…" : "Generate retrospective & close"}
            </Button>
          </>
        )}
        {status !== "archived" && (
          <Button variant="secondary" small disabled={busy !== null}
                  title={retroPending
                    ? "will be refused: the retrospective is not approved yet"
                    : undefined}
                  onClick={() => post("archive", `/projects/${projectId}/archive`)}>
            {busy === "archive" ? "Archiving…" : "Archive project"}
          </Button>
        )}
      </div>
      {message && <p className="text-xs text-slate-600">{message}</p>}
    </div>
  );
}

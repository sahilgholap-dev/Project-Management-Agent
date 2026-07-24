"use client";

// Orchestrator triggers. The as_of date picker is the approved OQ-4 control:
// backend functions take explicit dates, so slips/escalations are testable
// without waiting for wall-clock time. Clearly labeled simulation-only.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui";

async function post(path: string, body?: unknown): Promise<string | null> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return null;
}

export function ProjectActions({ projectId, status, hasPlan }: {
  projectId: number;
  status: string;
  hasPlan: boolean;
}) {
  const router = useRouter();
  const [asOf, setAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function run(label: string, path: string, body?: unknown) {
    setBusy(label);
    setMessage(null);
    const error = await post(path, body);
    setBusy(null);
    setMessage(error ? `✖ ${label}: ${error}` : `✓ ${label} done`);
    router.refresh();
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-slate-600">
          as-of{" "}
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
                 className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200" />
          <span className="ml-1 italic text-slate-500">(simulation date — testing only)</span>
        </label>
        {!hasPlan && (
          <Button variant="secondary" small disabled={busy !== null}
                  onClick={() => run("Onboard", `/projects/${projectId}/onboard`,
                                     { as_of: asOf })}>
            {busy === "Onboard" ? "Onboarding…" : "Onboard (breakdown → schedule → assign)"}
          </Button>
        )}
        <Button variant="secondary" small disabled={busy !== null}
                onClick={() => run("Cycle", `/projects/${projectId}/cycle`,
                                   { as_of: asOf, draft_comms: null })}>
          {busy === "Cycle" ? "Running…" : "Run monitoring cycle"}
        </Button>
        <Button variant="secondary" small disabled={busy !== null}
                onClick={() => run("Cycle+comms", `/projects/${projectId}/cycle`,
                                   { as_of: asOf, draft_comms: true })}>
          Cycle + ad-hoc comms draft
        </Button>
        {status === "paused" && (
          <Button variant="danger" small disabled={busy !== null}
                  onClick={() => run("Resume", `/projects/${projectId}/resume`)}>
            Resume project
          </Button>
        )}
      </div>
      {message && <p className="text-xs text-slate-600">{message}</p>}
    </div>
  );
}

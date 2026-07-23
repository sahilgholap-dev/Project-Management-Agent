"use client";

// Orchestrator triggers. The as_of date picker is the approved OQ-4 control:
// backend functions take explicit dates, so slips/escalations are testable
// without waiting for wall-clock time. Clearly labeled simulation-only.

import { useRouter } from "next/navigation";
import { useState } from "react";

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

  const button =
    "rounded border px-3 py-1.5 text-xs hover:bg-slate-100 disabled:opacity-50";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-slate-500">
          as-of{" "}
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
                 className="rounded border px-2 py-1 text-xs" />
          <span className="ml-1 italic">(simulation date — testing only)</span>
        </label>
        {!hasPlan && (
          <button className={button} disabled={busy !== null}
                  onClick={() => run("Onboard", `/projects/${projectId}/onboard`,
                                     { as_of: asOf })}>
            {busy === "Onboard" ? "Onboarding…" : "Onboard (breakdown → schedule → assign)"}
          </button>
        )}
        <button className={button} disabled={busy !== null}
                onClick={() => run("Cycle", `/projects/${projectId}/cycle`,
                                   { as_of: asOf, draft_comms: null })}>
          {busy === "Cycle" ? "Running…" : "Run monitoring cycle"}
        </button>
        <button className={button} disabled={busy !== null}
                onClick={() => run("Cycle+comms", `/projects/${projectId}/cycle`,
                                   { as_of: asOf, draft_comms: true })}>
          Cycle + ad-hoc comms draft
        </button>
        {status === "paused" && (
          <button className={`${button} border-red-300 text-red-700`}
                  disabled={busy !== null}
                  onClick={() => run("Resume", `/projects/${projectId}/resume`)}>
            Resume project
          </button>
        )}
      </div>
      {message && <p className="text-xs text-slate-600">{message}</p>}
    </div>
  );
}

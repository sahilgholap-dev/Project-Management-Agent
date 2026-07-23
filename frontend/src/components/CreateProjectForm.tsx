"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function CreateProjectForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setError(null);
    const response = await fetch("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: formData.get("name"),
        scope_document: formData.get("scope_document"),
        budget_total: formData.get("budget_total")
          ? Number(formData.get("budget_total")) : null,
        timeline_start: formData.get("timeline_start"),
        timeline_end: formData.get("timeline_end"),
      }),
    });
    setBusy(false);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      setError(JSON.stringify(body?.detail ?? response.status));
      return;
    }
    const { project_id } = await response.json();
    router.push(`/projects/${project_id}`);
    router.refresh();
  }

  return (
    <form action={submit} className="space-y-3 text-sm">
      <input name="name" required placeholder="Project name"
             className="w-full rounded border px-3 py-2" />
      <textarea name="scope_document" required rows={6}
                placeholder="Scope document (plain text, v1)"
                className="w-full rounded border px-3 py-2 font-mono text-xs" />
      <div className="flex gap-3">
        <label className="flex-1 text-xs text-slate-500">
          Timeline start
          <input name="timeline_start" type="date" required
                 className="mt-1 w-full rounded border px-2 py-1.5 text-sm text-slate-900" />
        </label>
        <label className="flex-1 text-xs text-slate-500">
          Timeline end
          <input name="timeline_end" type="date" required
                 className="mt-1 w-full rounded border px-2 py-1.5 text-sm text-slate-900" />
        </label>
        <label className="flex-1 text-xs text-slate-500">
          Budget (optional)
          <input name="budget_total" type="number" min="0"
                 className="mt-1 w-full rounded border px-2 py-1.5 text-sm text-slate-900" />
        </label>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <button disabled={busy}
              className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50">
        {busy ? "Creating…" : "Create project"}
      </button>
    </form>
  );
}

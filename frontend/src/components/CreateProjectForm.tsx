"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Field, inputCls } from "@/components/ui";

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
    <form action={submit} className="space-y-4 text-sm">
      <Field label="Project name">
        <input name="name" required placeholder="Project name" className={inputCls} />
      </Field>
      <Field label="Scope document">
        <textarea name="scope_document" required rows={6}
                  placeholder="Scope document (plain text, v1)"
                  className={`${inputCls} font-mono text-xs`} />
      </Field>
      <div className="flex gap-3">
        <Field label="Timeline start" className="flex-1">
          <input name="timeline_start" type="date" required className={inputCls} />
        </Field>
        <Field label="Timeline end" className="flex-1">
          <input name="timeline_end" type="date" required className={inputCls} />
        </Field>
        <Field label="Budget (optional)" className="flex-1">
          <input name="budget_total" type="number" min="0" className={inputCls} />
        </Field>
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
      <Button disabled={busy}>
        {busy ? "Creating…" : "Create project"}
      </Button>
    </form>
  );
}

"use client";

// PRD 8.7 trigger: a transcript or notes uploaded per project (confirmed
// Q19). Extraction runs immediately (Sonnet 5); a halted extraction is
// surfaced as the backend's 409, never hidden.

import { useRouter } from "next/navigation";
import { useState } from "react";

export function MeetingUploadForm({ projectId }: { projectId: number }) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage(null);
    const response = await fetch(`/api/projects/${projectId}/meetings`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        raw_text: formData.get("raw_text"),
        meeting_date: formData.get("meeting_date") || null,
      }),
    });
    setBusy(false);
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      setMessage(`✖ ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
      return;
    }
    setMessage(
      `✓ extracted: ${body.decisions} decision(s), ${body.action_items} action` +
      ` item(s) (${body.converted_tasks} converted to tasks), ${body.blockers}` +
      " blocker(s) — clarifications, if any, are in the review queue",
    );
    router.refresh();
  }

  return (
    <form action={submit} className="space-y-2 text-sm">
      <textarea name="raw_text" required rows={10}
                placeholder="Paste the transcript or meeting notes…"
                className="w-full rounded border px-3 py-2 font-mono text-xs" />
      <div className="flex items-center gap-3">
        <label className="text-xs text-slate-500">
          Meeting date{" "}
          <input name="meeting_date" type="date"
                 className="rounded border px-2 py-1.5 text-sm text-slate-900" />
        </label>
        <button disabled={busy}
                className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "Extracting…" : "Upload & extract"}
        </button>
      </div>
      {message && <p className="text-xs text-slate-600">{message}</p>}
    </form>
  );
}

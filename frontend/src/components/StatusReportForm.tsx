"use client";

// Manual status entry — the confirmed-Q7 inbox standing in for a real
// channel. The reply is parsed by Status Tracking on the NEXT monitoring
// cycle, not at submit time; the inbox table below shows that lifecycle.

import { useRouter } from "next/navigation";
import { useState } from "react";

type Option = { id: number; label: string };

export function StatusReportForm({ tasks, members }: {
  tasks: Option[];
  members: Option[];
}) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(formData: FormData) {
    setBusy(true);
    setMessage(null);
    const response = await fetch("/api/status-reports", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        task_id: Number(formData.get("task_id")),
        member_id: Number(formData.get("member_id")),
        raw_text: formData.get("raw_text"),
      }),
    });
    setBusy(false);
    if (!response.ok) {
      const detail = (await response.json().catch(() => null))?.detail;
      setMessage(`✖ ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
      return;
    }
    setMessage("✓ queued — it will be parsed on the next monitoring cycle");
    router.refresh();
  }

  return (
    <form action={submit} className="space-y-2 text-sm">
      <div className="flex gap-2">
        <select name="task_id" required className="flex-1 rounded border px-2 py-2">
          <option value="">Task…</option>
          {tasks.map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
        <select name="member_id" required className="w-48 rounded border px-2 py-2">
          <option value="">Reporting member…</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
      </div>
      <textarea name="raw_text" required rows={3}
                placeholder='Free-text reply, e.g. "about half done, 12h in so far"'
                className="w-full rounded border px-3 py-2" />
      <div className="flex items-center gap-3">
        <button disabled={busy}
                className="rounded bg-slate-800 px-4 py-2 text-white disabled:opacity-50">
          {busy ? "Submitting…" : "Submit status reply"}
        </button>
        {message && <span className="text-xs text-slate-600">{message}</span>}
      </div>
    </form>
  );
}

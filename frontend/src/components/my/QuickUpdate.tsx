"use client";

// The member's "update this task" affordance. Deliberately NOT a direct task
// write: every action here composes a plain-language status report and files
// it through POST /status-reports, so the same parse -> validate -> EVM
// pipeline (and its ambiguity flagging + hours capture) applies no matter
// where an update comes from. Reports are parsed on the next monitoring
// cycle — until then the task shows "update pending".

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, inputCls } from "@/components/ui";
import { apiFetch } from "@/lib/client";

export function QuickUpdate({ taskId, memberId }: {
  taskId: number;
  memberId: number;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"done" | "progress" | "blocked" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(text: string) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/status-reports", {
        method: "POST",
        body: { task_id: taskId, member_id: memberId, raw_text: text },
      });
      setMode(null);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (mode === "done") {
    return (
      <form
        className="flex flex-wrap items-center gap-2"
        action={(fd) => submit(
          `Task complete. Total time spent: ${fd.get("hours")} hours.` +
          `${fd.get("note") ? ` ${fd.get("note")}` : ""}`,
        )}
      >
        <input name="hours" type="number" min="0" step="0.5" required
               placeholder="hours spent" className={`${inputCls} w-28`} autoFocus />
        <input name="note" placeholder="note (optional)" className={`${inputCls} w-44`} />
        <Button small disabled={busy}>Submit</Button>
        <Button small type="button" variant="ghost" onClick={() => setMode(null)}>
          Cancel
        </Button>
      </form>
    );
  }
  if (mode === "progress") {
    return (
      <form
        className="flex flex-wrap items-center gap-2"
        action={(fd) => submit(
          `In progress, about ${fd.get("percent")}% done.` +
          ` Roughly ${fd.get("hours")} hours spent so far.` +
          `${fd.get("note") ? ` ${fd.get("note")}` : ""}`,
        )}
      >
        <input name="percent" type="number" min="1" max="99" required
               placeholder="% done" className={`${inputCls} w-24`} autoFocus />
        <input name="hours" type="number" min="0" step="0.5" required
               placeholder="hours so far" className={`${inputCls} w-28`} />
        <input name="note" placeholder="note (optional)" className={`${inputCls} w-40`} />
        <Button small disabled={busy}>Submit</Button>
        <Button small type="button" variant="ghost" onClick={() => setMode(null)}>
          Cancel
        </Button>
      </form>
    );
  }
  if (mode === "blocked") {
    return (
      <form
        className="flex flex-wrap items-center gap-2"
        action={(fd) => submit(`Blocked: ${fd.get("reason")}`)}
      >
        <input name="reason" required placeholder="what is blocking you?"
               className={`${inputCls} w-72`} autoFocus />
        <Button small disabled={busy}>Submit</Button>
        <Button small type="button" variant="ghost" onClick={() => setMode(null)}>
          Cancel
        </Button>
      </form>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Button small variant="secondary" onClick={() => setMode("done")}>
        Mark done
      </Button>
      <Button small variant="secondary" onClick={() => setMode("progress")}>
        Update progress
      </Button>
      <Button small variant="danger" onClick={() => setMode("blocked")}>
        Blocked
      </Button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

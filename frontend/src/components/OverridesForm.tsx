"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, inputCls } from "@/components/ui";

export function OverridesForm({ projectId, initial }: {
  projectId: number;
  initial: Record<string, unknown>;
}) {
  const router = useRouter();
  const [text, setText] = useState(JSON.stringify(initial, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setBusy(false);
      setError("not valid JSON");
      return;
    }
    const response = await fetch(`/api/projects/${projectId}/overrides`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(parsed),
    });
    setBusy(false);
    if (!response.ok) {
      const detail = (await response.json().catch(() => null))?.detail;
      setError(JSON.stringify(detail?.defects ?? detail));
      return;
    }
    setMessage("✓ overrides saved (validated)");
    router.refresh();
  }

  return (
    <div className="space-y-2 text-sm">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8}
                className={`${inputCls} font-mono text-xs`} />
      <p className="text-xs text-slate-500">
        Any client_config key is overridable. Remove a key to fall back to the
        client default (null overrides are rejected as ambiguous).
      </p>
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save overrides"}
        </Button>
        {message && <span className="text-xs text-emerald-700">{message}</span>}
      </div>
    </div>
  );
}

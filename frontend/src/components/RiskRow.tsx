"use client";

// Reviewer score adjustment goes through the audited OQ-6 endpoint
// (PATCH /risks/{id}/score -> risk_tracking.adjust_score, human actor
// recorded). Never a raw update.

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Risk } from "@/app/(client)/projects/[id]/risks/page";

const SCALE = [1, 2, 3, 4, 5];

export function RiskRow({ risk, canAdjust }: { risk: Risk; canAdjust: boolean }) {
  const router = useRouter();
  const [severity, setSeverity] = useState(risk.severity);
  const [likelihood, setLikelihood] = useState(risk.likelihood);
  const [error, setError] = useState<string | null>(null);
  const dirty = severity !== risk.severity || likelihood !== risk.likelihood;

  async function save() {
    setError(null);
    const response = await fetch(`/api/risks/${risk.risk_id}/score`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ severity, likelihood }),
    });
    if (!response.ok) {
      setError(JSON.stringify((await response.json().catch(() => null))?.detail));
      return;
    }
    router.refresh();
  }

  const select = (value: number, set: (n: number) => void) => (
    <select value={value} disabled={!canAdjust}
            onChange={(e) => set(Number(e.target.value))}
            className="rounded border px-1 py-0.5">
      {SCALE.map((n) => <option key={n}>{n}</option>)}
    </select>
  );

  return (
    <tr className="border-b align-top last:border-0">
      <td className="max-w-md px-4 py-2">
        <span className="font-medium">{risk.title}</span>
        {risk.description && (
          <p className="text-slate-500">{risk.description}</p>
        )}
        {error && <p className="text-red-600">{error}</p>}
      </td>
      <td className="px-2 py-2">{risk.kind}</td>
      <td className="px-2 py-2">
        <span className={`rounded px-1.5 py-0.5 ${
          risk.source === "rule_based"
            ? "bg-slate-100" : "bg-violet-100 text-violet-800"
        }`}>
          {risk.source}
        </span>
      </td>
      <td className="px-2 py-2">{select(severity, setSeverity)}</td>
      <td className="px-2 py-2">{select(likelihood, setLikelihood)}</td>
      <td className="px-2 py-2 font-semibold">{risk.score}</td>
      <td className="px-2 py-2">{risk.status}</td>
      <td className="px-2 py-2">
        {dirty && (
          <button onClick={save}
                  className="rounded border px-2 py-0.5 hover:bg-slate-100">
            save scores
          </button>
        )}
      </td>
    </tr>
  );
}

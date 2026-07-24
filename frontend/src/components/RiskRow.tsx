"use client";

// Reviewer score adjustment goes through the audited OQ-6 endpoint
// (PATCH /risks/{id}/score -> risk_tracking.adjust_score, human actor
// recorded). Never a raw update.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Td, statusTone } from "@/components/ui";
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
            className="rounded-md border border-slate-300 bg-white px-1.5 py-0.5 text-xs text-slate-900 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200 disabled:bg-slate-50">
      {SCALE.map((n) => <option key={n}>{n}</option>)}
    </select>
  );

  return (
    <tr className="align-top">
      <Td className="max-w-md align-top">
        <span className="font-medium text-slate-900">{risk.title}</span>
        {risk.description && (
          <p className="text-slate-500">{risk.description}</p>
        )}
        {error && <p className="text-red-600">{error}</p>}
      </Td>
      <Td className="align-top text-slate-700">{risk.kind}</Td>
      <Td className="align-top">
        <Badge tone={risk.source === "rule_based" ? "neutral" : "info"}>
          {risk.source}
        </Badge>
      </Td>
      <Td className="align-top">{select(severity, setSeverity)}</Td>
      <Td className="align-top">{select(likelihood, setLikelihood)}</Td>
      <Td className="align-top font-semibold text-slate-900">{risk.score}</Td>
      <Td className="align-top">
        <Badge tone={statusTone(risk.status)}>{risk.status}</Badge>
      </Td>
      <Td className="align-top">
        {dirty && (
          <Button variant="secondary" small onClick={save}>
            save scores
          </Button>
        )}
      </Td>
    </tr>
  );
}

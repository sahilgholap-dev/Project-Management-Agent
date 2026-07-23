import Link from "next/link";
import { notFound } from "next/navigation";
import { RiskRow } from "@/components/RiskRow";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

export type Risk = {
  risk_id: number;
  kind: string;
  title: string;
  description: string | null;
  severity: number;
  likelihood: number;
  score: number;
  status: string;
  source: string;
  created_at: string;
};

const STATUSES = ["open", "mitigating", "closed"];

export default async function RisksPage({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ status?: string }>;
}) {
  const { id } = await params;
  const { status } = await searchParams;
  const me = await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const query = status ? `?status=${status}` : "";
  const risks = await serverApi<Risk[]>(`/projects/${id}/risks${query}`);

  return (
    <main className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Risk register — {project.name}</h1>
          <p className="text-xs text-slate-500">
            Sorted by score. Scores are reviewer-adjustable (PRD 8.5 step 4).{" "}
            <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
          </p>
        </div>
        <nav className="flex gap-1 text-xs">
          <Link href={`/projects/${id}/risks`}
                className={`rounded border px-2 py-1 ${!status ? "bg-slate-800 text-white" : ""}`}>
            all
          </Link>
          {STATUSES.map((s) => (
            <Link key={s} href={`/projects/${id}/risks?status=${s}`}
                  className={`rounded border px-2 py-1 ${status === s ? "bg-slate-800 text-white" : ""}`}>
              {s}
            </Link>
          ))}
        </nav>
      </header>

      <table className="w-full rounded border bg-white text-left text-xs">
        <thead className="text-slate-500">
          <tr className="border-b bg-slate-50">
            <th className="px-4 py-2">Risk / issue</th>
            <th className="px-2 py-2">Kind</th>
            <th className="px-2 py-2">Source</th>
            <th className="px-2 py-2">Severity</th>
            <th className="px-2 py-2">Likelihood</th>
            <th className="px-2 py-2">Score</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {risks.map((r) => (
            <RiskRow key={r.risk_id} risk={r} canAdjust={me.role === "client_admin"} />
          ))}
        </tbody>
      </table>
      {risks.length === 0 && (
        <p className="rounded border bg-white p-4 text-sm text-slate-500">
          No {status ?? ""} risks on the register.
        </p>
      )}
    </main>
  );
}

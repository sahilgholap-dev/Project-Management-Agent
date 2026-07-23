import Link from "next/link";
import { notFound } from "next/navigation";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

type EscalationEntry = {
  escalation_id: number;
  item_id: number;
  stage: string;
  reason: string;
  outcome: string | null;
  occurred_at: string;
};

type AuditEntry = {
  audit_id: number;
  skill: string;
  action: string;
  input_summary: string | null;
  output_summary: string | null;
  actor: string;
  occurred_at: string;
};

export default async function LogsPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const [escalations, audit] = await Promise.all([
    serverApi<EscalationEntry[]>(`/projects/${id}/escalation-log`),
    serverApi<AuditEntry[]>(`/projects/${id}/audit-log`),
  ]);

  return (
    <main className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">Logs — {project.name}</h1>
        <p className="text-xs text-slate-500">
          Read-only, for verifying system behavior during testing (PRD s13).{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      <section className="rounded border bg-white">
        <h2 className="border-b bg-slate-50 px-4 py-2 text-sm font-semibold">
          Escalation log ({escalations.length})
        </h2>
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr className="border-b">
              <th className="px-4 py-2">When</th>
              <th className="px-2 py-2">Item</th>
              <th className="px-2 py-2">Stage</th>
              <th className="px-2 py-2">Reason</th>
              <th className="px-2 py-2">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {escalations.map((e) => (
              <tr key={e.escalation_id}
                  className={`border-b last:border-0 ${
                    e.stage === "work_paused" ? "bg-red-50" : ""
                  }`}>
                <td className="whitespace-nowrap px-4 py-1.5">{e.occurred_at}</td>
                <td className="px-2 py-1.5">#{e.item_id}</td>
                <td className="px-2 py-1.5 font-medium">{e.stage}</td>
                <td className="px-2 py-1.5">{e.reason}</td>
                <td className="px-2 py-1.5">{e.outcome ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {escalations.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No escalations recorded.</p>
        )}
      </section>

      <section className="rounded border bg-white">
        <h2 className="border-b bg-slate-50 px-4 py-2 text-sm font-semibold">
          Audit log (latest {audit.length})
        </h2>
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr className="border-b">
              <th className="px-4 py-2">When</th>
              <th className="px-2 py-2">Skill</th>
              <th className="px-2 py-2">Action</th>
              <th className="px-2 py-2">Actor</th>
              <th className="px-2 py-2">Summary</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.audit_id} className="border-b align-top last:border-0">
                <td className="whitespace-nowrap px-4 py-1.5">{a.occurred_at}</td>
                <td className="px-2 py-1.5">{a.skill}</td>
                <td className="px-2 py-1.5">{a.action}</td>
                <td className="px-2 py-1.5">
                  {a.actor === "agent" ? (
                    <span className="text-slate-400">agent</span>
                  ) : (
                    <span className="font-medium">user {a.actor}</span>
                  )}
                </td>
                <td className="max-w-md px-2 py-1.5 font-mono text-[10px]">
                  {a.input_summary && <div>in: {a.input_summary}</div>}
                  {a.output_summary && <div>out: {a.output_summary}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}

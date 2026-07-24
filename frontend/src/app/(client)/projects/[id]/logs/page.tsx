import Link from "next/link";
import { notFound } from "next/navigation";
import { EmptyState, PageHeader, Table, Td } from "@/components/ui";
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
    <div className="space-y-6">
      <PageHeader
        title={`Logs — ${project.name}`}
        description={
          <>
            Read-only, for verifying system behavior during testing (PRD s13).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Escalation log ({escalations.length})
        </h2>
        {escalations.length === 0 ? (
          <EmptyState>No escalations recorded.</EmptyState>
        ) : (
          <Table headers={["When", "Item", "Stage", "Reason", "Outcome"]}>
            {escalations.map((e) => (
              <tr key={e.escalation_id}
                  className={e.stage === "work_paused" ? "bg-red-50" : ""}>
                <Td className="whitespace-nowrap text-slate-500">{e.occurred_at}</Td>
                <Td>#{e.item_id}</Td>
                <Td className="font-medium text-slate-900">{e.stage}</Td>
                <Td className="text-slate-700">{e.reason}</Td>
                <Td className="text-slate-700">{e.outcome ?? "—"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Audit log (latest {audit.length})
        </h2>
        <Table headers={["When", "Skill", "Action", "Actor", "Summary"]}>
          {audit.map((a) => (
            <tr key={a.audit_id} className="align-top">
              <Td className="whitespace-nowrap align-top text-slate-500">{a.occurred_at}</Td>
              <Td className="align-top">{a.skill}</Td>
              <Td className="align-top">{a.action}</Td>
              <Td className="align-top">
                {a.actor === "agent" ? (
                  <span className="text-slate-400">agent</span>
                ) : (
                  <span className="font-medium">user {a.actor}</span>
                )}
              </Td>
              <Td className="max-w-md align-top font-mono text-[10px] text-slate-600">
                {a.input_summary && <div>in: {a.input_summary}</div>}
                {a.output_summary && <div>out: {a.output_summary}</div>}
              </Td>
            </tr>
          ))}
        </Table>
      </section>
    </div>
  );
}

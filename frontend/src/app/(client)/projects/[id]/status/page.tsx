import Link from "next/link";
import { notFound } from "next/navigation";
import { StatusReportForm } from "@/components/StatusReportForm";
import { Badge, Card, EmptyState, PageHeader, Table, Td } from "@/components/ui";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

type Report = {
  report_id: number;
  task_id: number;
  task_title: string;
  member_id: number;
  raw_text: string;
  parsed_status: string | null;
  parsed_percent_complete: number | null;
  parsed_hours_spent: number | null;
  is_ambiguous: number;
  received_at: string;
  processed_at: string | null;
};

type Member = { member_id: number; name: string; is_active: number };

export default async function StatusPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const [reports, members] = await Promise.all([
    serverApi<Report[]>(`/projects/${id}/status-reports`),
    serverApi<Member[]>("/team-members"),
  ]);

  const openTasks = project.tasks.filter(
    (t) => t.status !== "done" && t.status !== "cancelled",
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Status reports — ${project.name}`}
        description={
          <>
            Manual inbox (v1 has no channel integrations by design).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      <Card title="New status reply">
        {openTasks.length === 0 ? (
          <p className="text-sm text-slate-500">No open tasks to report on.</p>
        ) : (
          <StatusReportForm
            tasks={openTasks.map((t) => ({
              id: t.task_id,
              label: `${t.title} (${t.status}${t.owner_name ? ` · ${t.owner_name}` : ""})`,
            }))}
            members={members
              .filter((m) => m.is_active)
              .map((m) => ({ id: m.member_id, label: m.name }))}
          />
        )}
      </Card>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Inbox ({reports.length})
        </h2>
        {reports.length === 0 ? (
          <EmptyState>No reports yet.</EmptyState>
        ) : (
          <Table headers={["Task", "Reply", "Parsed", "Received", "State"]}>
            {reports.map((r) => (
              <tr key={r.report_id} className="align-top">
                <Td className="align-top">{r.task_title}</Td>
                <Td className="max-w-md align-top text-slate-700">{r.raw_text}</Td>
                <Td className="align-top text-slate-700">
                  {r.parsed_status ?? "—"}
                  {r.parsed_percent_complete != null && ` · ${r.parsed_percent_complete}%`}
                  {r.parsed_hours_spent != null && ` · ${r.parsed_hours_spent}h spent`}
                </Td>
                <Td className="whitespace-nowrap align-top text-slate-500">
                  {r.received_at}
                </Td>
                <Td className="align-top">
                  {r.is_ambiguous ? (
                    <Badge tone="warning">ambiguous — flagged</Badge>
                  ) : r.processed_at ? (
                    <Badge tone="success">processed {r.processed_at}</Badge>
                  ) : (
                    <Badge tone="neutral">queued for next cycle</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </section>
    </div>
  );
}

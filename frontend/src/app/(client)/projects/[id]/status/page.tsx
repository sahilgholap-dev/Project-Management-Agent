import Link from "next/link";
import { notFound } from "next/navigation";
import { StatusReportForm } from "@/components/StatusReportForm";
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
    <main className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">
          Status reports — {project.name}
        </h1>
        <p className="text-xs text-slate-500">
          Manual inbox (v1 has no channel integrations by design).{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">New status reply</h2>
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
      </section>

      <section className="rounded border bg-white">
        <h2 className="border-b bg-slate-50 px-4 py-2 text-sm font-semibold">
          Inbox ({reports.length})
        </h2>
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr className="border-b">
              <th className="px-4 py-2">Task</th>
              <th className="px-2 py-2">Reply</th>
              <th className="px-2 py-2">Parsed</th>
              <th className="px-2 py-2">Received</th>
              <th className="px-2 py-2">State</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.report_id} className="border-b align-top last:border-0">
                <td className="px-4 py-2">{r.task_title}</td>
                <td className="max-w-md px-2 py-2">{r.raw_text}</td>
                <td className="px-2 py-2">
                  {r.parsed_status ?? "—"}
                  {r.parsed_percent_complete != null && ` · ${r.parsed_percent_complete}%`}
                  {r.parsed_hours_spent != null && ` · ${r.parsed_hours_spent}h spent`}
                </td>
                <td className="whitespace-nowrap px-2 py-2">{r.received_at}</td>
                <td className="px-2 py-2">
                  {r.is_ambiguous ? (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                      ambiguous — flagged
                    </span>
                  ) : r.processed_at ? (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                      processed {r.processed_at}
                    </span>
                  ) : (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5">
                      queued for next cycle
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {reports.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No reports yet.</p>
        )}
      </section>
    </main>
  );
}

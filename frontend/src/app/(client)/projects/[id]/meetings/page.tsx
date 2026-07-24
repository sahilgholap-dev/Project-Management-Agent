import Link from "next/link";
import { notFound } from "next/navigation";
import { MeetingUploadForm } from "@/components/MeetingUploadForm";
import { Alert, Card, EmptyState, PageHeader } from "@/components/ui";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

type Meeting = {
  meeting_id: number;
  meeting_date: string | null;
  decisions: { decision: string; decided_by: string | null }[];
  created_at: string;
};

type Blocker = {
  blocker_id: number;
  description: string;
  status: string;
  raised_by_name: string | null;
  assigned_to: number | null;
  assigned_to_name: string | null;
  blocked_member_name: string | null;
};

export default async function MeetingsPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const [meetings, blockers] = await Promise.all([
    serverApi<Meeting[]>(`/projects/${id}/meetings`),
    serverApi<Blocker[]>(`/projects/${id}/blockers`),
  ]);
  const unowned = blockers.filter((b) => b.assigned_to === null && b.status === "open");

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Meetings — ${project.name}`}
        description={
          <>
            Per-project upload (multi-project transcripts are out of scope in v1).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      <Card title="Upload transcript / notes">
        <MeetingUploadForm projectId={project.project_id} />
      </Card>

      {unowned.length > 0 && (
        <Alert tone="warning"
               title={`${unowned.length} blocker(s) with no resolution owner`}>
          <ul className="list-disc pl-5">
            {unowned.map((b) => (
              <li key={b.blocker_id}>
                {b.description}
                {b.blocked_member_name && ` (blocking ${b.blocked_member_name})`}
              </li>
            ))}
          </ul>
          <p className="mt-1">
            Each is flagged in the review queue; assign owners from the blockers
            view (F4) or via the API until then.
          </p>
        </Alert>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">
          Uploaded meetings ({meetings.length})
        </h2>
        {meetings.map((m) => (
          <article key={m.meeting_id}
                   className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <header className="mb-2 text-xs text-slate-500">
              #{m.meeting_id} · {m.meeting_date ?? "no date"} · uploaded {m.created_at}
            </header>
            {m.decisions.length === 0 ? (
              <p className="text-xs text-slate-500">No decisions extracted.</p>
            ) : (
              <ul className="list-disc pl-5 text-slate-700">
                {m.decisions.map((d, i) => (
                  <li key={i}>
                    {d.decision}
                    {d.decided_by && (
                      <span className="text-slate-500"> — {d.decided_by}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
        {meetings.length === 0 && (
          <EmptyState>No meetings uploaded yet.</EmptyState>
        )}
      </section>
    </div>
  );
}

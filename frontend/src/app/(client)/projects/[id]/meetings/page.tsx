import Link from "next/link";
import { notFound } from "next/navigation";
import { MeetingUploadForm } from "@/components/MeetingUploadForm";
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
    <main className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">Meetings — {project.name}</h1>
        <p className="text-xs text-slate-500">
          Per-project upload (multi-project transcripts are out of scope in v1).{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold">Upload transcript / notes</h2>
        <MeetingUploadForm projectId={project.project_id} />
      </section>

      {unowned.length > 0 && (
        <section className="rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          <h2 className="mb-1 font-semibold text-amber-900">
            {unowned.length} blocker(s) with no resolution owner
          </h2>
          <ul className="list-disc pl-5 text-amber-900">
            {unowned.map((b) => (
              <li key={b.blocker_id}>
                {b.description}
                {b.blocked_member_name && ` (blocking ${b.blocked_member_name})`}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-amber-800">
            Each is flagged in the review queue; assign owners from the blockers
            view (F4) or via the API until then.
          </p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-600">
          Uploaded meetings ({meetings.length})
        </h2>
        {meetings.map((m) => (
          <article key={m.meeting_id} className="rounded border bg-white p-4 text-sm">
            <header className="mb-2 text-xs text-slate-500">
              #{m.meeting_id} · {m.meeting_date ?? "no date"} · uploaded {m.created_at}
            </header>
            {m.decisions.length === 0 ? (
              <p className="text-xs text-slate-500">No decisions extracted.</p>
            ) : (
              <ul className="list-disc pl-5">
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
          <p className="rounded border bg-white p-4 text-sm text-slate-500">
            No meetings uploaded yet.
          </p>
        )}
      </section>
    </main>
  );
}

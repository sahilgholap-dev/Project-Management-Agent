import Link from "next/link";
import { notFound } from "next/navigation";
import { CloseActions } from "@/components/CloseActions";
import {
  ProjectDetail, ReviewItem, requireClientUser, serverApi, serverApiOrNull,
} from "@/lib/api";

type Artifact = {
  version_id: number;
  artifact_type: string;
  artifact_ref: number | null;
  version_number: number;
  content: string;
  created_by: number | null;
  created_at: string;
};

export default async function ClosePage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const [items, artifacts] = await Promise.all([
    serverApi<ReviewItem[]>(`/review-queue?project_id=${id}`),
    serverApi<Artifact[]>(`/projects/${id}/artifacts`),
  ]);
  const retros = items.filter((i) => i.item_type === "retrospective");
  const retroPending = retros.some((i) => i.status !== "approved");
  const retroApproved = retros.some((i) => i.status === "approved");

  return (
    <main className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">Close project — {project.name}</h1>
        <p className="text-xs text-slate-500">
          Generate retrospective (Tier 2) → review &amp; approve it in the queue →
          archive. Archive is refused by the backend until the retrospective is
          explicitly approved.{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      {me.role === "client_admin" && (
        <section className="rounded border bg-white p-4">
          <CloseActions projectId={project.project_id} status={project.status}
                        retroPending={retroPending && !retroApproved} />
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Retrospective review items
        </h2>
        {retros.length === 0 ? (
          <p className="rounded border bg-white p-4 text-sm text-slate-500">
            None yet — generating one closes the project and queues it at Tier 2.
          </p>
        ) : (
          retros.map((r) => (
            <div key={r.item_id}
                 className="flex items-center justify-between rounded border bg-white px-4 py-3 text-sm">
              <span>
                item #{r.item_id} · {r.created_at}
                <span className={`ml-2 rounded px-2 py-0.5 text-xs ${
                  r.status === "approved" ? "bg-emerald-100 text-emerald-800"
                  : r.status === "rejected" ? "bg-slate-200 text-slate-600"
                  : "bg-amber-100 text-amber-800"
                }`}>
                  {r.status}
                </span>
              </span>
              {(r.status === "pending" || r.status === "escalated") && (
                <Link href={`/review-queue?project_id=${id}`}
                      className="rounded border px-3 py-1.5 text-xs hover:bg-slate-100">
                  Review it in the queue
                </Link>
              )}
            </div>
          ))
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Versioned artifacts ({artifacts.length})
        </h2>
        {artifacts.map((a) => (
          <details key={a.version_id} className="rounded border bg-white">
            <summary className="cursor-pointer px-4 py-2 text-sm">
              {a.artifact_type} v{a.version_number}
              <span className="ml-2 text-xs text-slate-500">
                ref #{a.artifact_ref} · {a.created_at} · approved by user {a.created_by}
              </span>
            </summary>
            {/* OQ-8: the exact approved bytes, preformatted */}
            <pre className="overflow-auto border-t bg-slate-50 p-3 text-xs whitespace-pre-wrap">
              {a.content}
            </pre>
          </details>
        ))}
        {artifacts.length === 0 && (
          <p className="rounded border bg-white p-4 text-sm text-slate-500">
            No versioned artifacts yet — approving a comms draft, status report,
            or retrospective creates one.
          </p>
        )}
      </section>
    </main>
  );
}

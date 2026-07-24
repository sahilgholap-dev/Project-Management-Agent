import Link from "next/link";
import { notFound } from "next/navigation";
import { CloseActions } from "@/components/CloseActions";
import { Badge, Card, EmptyState, PageHeader, buttonCls, statusTone } from "@/components/ui";
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
    <div className="space-y-6">
      <PageHeader
        title={`Close project — ${project.name}`}
        description={
          <>
            Generate retrospective (Tier 2) → review &amp; approve it in the queue →
            archive. Archive is refused by the backend until the retrospective is
            explicitly approved.{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      {me.role === "client_admin" && (
        <Card>
          <CloseActions projectId={project.project_id} status={project.status}
                        retroPending={retroPending && !retroApproved} />
        </Card>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-600">
          Retrospective review items
        </h2>
        {retros.length === 0 ? (
          <EmptyState>
            None yet — generating one closes the project and queues it at Tier 2.
          </EmptyState>
        ) : (
          retros.map((r) => (
            <div key={r.item_id}
                 className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
              <span className="text-slate-700">
                item #{r.item_id} · {r.created_at}
                <span className="ml-2">
                  <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                </span>
              </span>
              {(r.status === "pending" || r.status === "escalated") && (
                <Link href={`/review-queue?project_id=${id}`}
                      className={buttonCls("secondary", true)}>
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
          <details key={a.version_id}
                   className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-slate-900 hover:bg-slate-50">
              {a.artifact_type} v{a.version_number}
              <span className="ml-2 text-xs font-normal text-slate-500">
                ref #{a.artifact_ref} · {a.created_at} · approved by user {a.created_by}
              </span>
            </summary>
            {/* OQ-8: the exact approved bytes, preformatted */}
            <pre className="overflow-auto border-t border-slate-200 bg-slate-50 p-3 text-xs whitespace-pre-wrap text-slate-700">
              {a.content}
            </pre>
          </details>
        ))}
        {artifacts.length === 0 && (
          <EmptyState>
            No versioned artifacts yet — approving a comms draft, status report,
            or retrospective creates one.
          </EmptyState>
        )}
      </section>
    </div>
  );
}

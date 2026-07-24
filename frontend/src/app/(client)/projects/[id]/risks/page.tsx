import Link from "next/link";
import { notFound } from "next/navigation";
import { RiskRow } from "@/components/RiskRow";
import { EmptyState, PageHeader, Table } from "@/components/ui";
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

function filterCls(active: boolean) {
  return active
    ? "rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white"
    : "rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50";
}

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
    <div className="space-y-4">
      <PageHeader
        title={`Risk register — ${project.name}`}
        description={
          <>
            Sorted by score. Scores are reviewer-adjustable (PRD 8.5 step 4).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
        actions={
          <nav className="flex gap-1">
            <Link href={`/projects/${id}/risks`} className={filterCls(!status)}>
              all
            </Link>
            {STATUSES.map((s) => (
              <Link key={s} href={`/projects/${id}/risks?status=${s}`}
                    className={filterCls(status === s)}>
                {s}
              </Link>
            ))}
          </nav>
        }
      />

      {risks.length === 0 ? (
        <EmptyState>No {status ?? ""} risks on the register.</EmptyState>
      ) : (
        <Table headers={[
          "Risk / issue", "Kind", "Source", "Severity", "Likelihood", "Score",
          "Status", "",
        ]}>
          {risks.map((r) => (
            <RiskRow key={r.risk_id} risk={r} canAdjust={me.role === "client_admin"} />
          ))}
        </Table>
      )}
    </div>
  );
}

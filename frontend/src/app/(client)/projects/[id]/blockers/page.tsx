import Link from "next/link";
import { notFound } from "next/navigation";
import { BlockerRow } from "@/components/BlockerRow";
import { Alert, EmptyState, PageHeader, Table } from "@/components/ui";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

export type Blocker = {
  blocker_id: number;
  description: string;
  status: string;
  raised_by: number | null;
  raised_by_name: string | null;
  assigned_to: number | null;
  assigned_to_name: string | null;
  blocked_member_name: string | null;
  created_at: string;
  resolved_at: string | null;
};

type Member = { member_id: number; name: string; is_active: number };

export default async function BlockersPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const [blockers, members] = await Promise.all([
    serverApi<Blocker[]>(`/projects/${id}/blockers`),
    serverApi<Member[]>("/team-members"),
  ]);
  const unowned = blockers.filter((b) => b.assigned_to === null && b.status === "open");

  return (
    <div className="space-y-4">
      <PageHeader
        title={`Blockers — ${project.name}`}
        description={
          <>
            raised_by and assigned_to are distinct people by design (PRD section 9).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      {unowned.length > 0 && (
        <Alert tone="warning">
          {unowned.length} open blocker(s) have <strong>no resolution owner</strong> —
          they sort first below and each carries a Tier 1 flag in the review queue.
        </Alert>
      )}

      {blockers.length === 0 ? (
        <EmptyState>No blockers recorded.</EmptyState>
      ) : (
        <Table headers={[
          "Blocker", "Blocked", "Raised by", "Assigned to (resolver)", "Status", "",
        ]}>
          {blockers.map((b) => (
            <BlockerRow key={b.blocker_id} blocker={b}
                        members={members.filter((m) => m.is_active)
                          .map((m) => ({ id: m.member_id, name: m.name }))}
                        canEdit={me.role === "client_admin"} />
          ))}
        </Table>
      )}
    </div>
  );
}

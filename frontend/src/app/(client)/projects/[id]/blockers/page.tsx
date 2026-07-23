import Link from "next/link";
import { notFound } from "next/navigation";
import { BlockerRow } from "@/components/BlockerRow";
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
    <main className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Blockers — {project.name}</h1>
        <p className="text-xs text-slate-500">
          raised_by and assigned_to are distinct people by design (PRD section 9).{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      {unowned.length > 0 && (
        <p className="rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          {unowned.length} open blocker(s) have <strong>no resolution owner</strong> —
          they sort first below and each carries a Tier 1 flag in the review queue.
        </p>
      )}

      <table className="w-full rounded border bg-white text-left text-xs">
        <thead className="text-slate-500">
          <tr className="border-b bg-slate-50">
            <th className="px-4 py-2">Blocker</th>
            <th className="px-2 py-2">Blocked</th>
            <th className="px-2 py-2">Raised by</th>
            <th className="px-2 py-2">Assigned to (resolver)</th>
            <th className="px-2 py-2">Status</th>
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {blockers.map((b) => (
            <BlockerRow key={b.blocker_id} blocker={b}
                        members={members.filter((m) => m.is_active)
                          .map((m) => ({ id: m.member_id, name: m.name }))}
                        canEdit={me.role === "client_admin"} />
          ))}
        </tbody>
      </table>
      {blockers.length === 0 && (
        <p className="rounded border bg-white p-4 text-sm text-slate-500">
          No blockers recorded.
        </p>
      )}
    </main>
  );
}

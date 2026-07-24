import { ItemCard } from "@/components/ItemCard";
import { RefreshBar } from "@/components/RefreshBar";
import { EmptyState, PageHeader } from "@/components/ui";
import { ReviewItem, requireClientUser, serverApi } from "@/lib/api";

const TIER_LABELS: Record<number, string> = {
  1: "Tier 1 — single-tap approve / reject",
  2: "Tier 2 — full review before it goes out",
  3: "Tier 3 — formal packet, explicit sign-off",
};

export default async function ReviewQueuePage({ searchParams }: {
  searchParams: Promise<{ project_id?: string; status?: string }>;
}) {
  const me = await requireClientUser(); // gate BEFORE data (403-race guard)
  const params = await searchParams;
  const status = params.status ?? "pending";
  const query = new URLSearchParams({ status });
  if (params.project_id) query.set("project_id", params.project_id);

  const items = await serverApi<ReviewItem[]>(`/review-queue?${query}`);
  const canResolve = me.role === "client_admin";

  // OQ-3 (approved): clarifications cluster by producing skill — visual
  // grouping only; every item keeps its own individual resolve controls.
  const byTier = new Map<number, ReviewItem[]>([[1, []], [2, []], [3, []]]);
  for (const item of items) byTier.get(item.tier)?.push(item);

  return (
    <>
      <PageHeader
        title="Review queue"
        description={
          <>
            {items.length} {status} item{items.length === 1 ? "" : "s"}
            {params.project_id ? ` · project ${params.project_id}` : " · all projects"}
          </>
        }
        actions={<RefreshBar />}
      />
      <div className="space-y-6">
        {([1, 2, 3] as const).map((tier) => {
          const tierItems = byTier.get(tier) ?? [];
          if (tierItems.length === 0) return null;

          const clarifications = tier === 1
            ? tierItems.filter((i) => i.item_type === "clarification")
            : [];
          const rest = tierItems.filter((i) => !clarifications.includes(i));
          const clusters = new Map<string, ReviewItem[]>();
          for (const c of clarifications) {
            const list = clusters.get(c.created_by_skill) ?? [];
            list.push(c);
            clusters.set(c.created_by_skill, list);
          }

          return (
            <section key={tier} className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {TIER_LABELS[tier]}
              </h2>
              {rest.map((item) => (
                <ItemCard key={item.item_id} item={item} canResolve={canResolve} />
              ))}
              {[...clusters.entries()].map(([skill, group]) => (
                <details key={skill}
                         className="rounded-lg border border-slate-200 bg-white shadow-sm">
                  <summary className="cursor-pointer px-5 py-3 text-sm text-slate-700 hover:bg-slate-50">
                    {group.length} clarification{group.length === 1 ? "" : "s"} from{" "}
                    <code className="rounded bg-slate-100 px-1">{skill}</code>
                    <span className="ml-2 text-xs text-slate-500">
                      (resolved individually — there is no batch approve)
                    </span>
                  </summary>
                  <div className="space-y-3 border-t border-slate-100 p-4">
                    {group.map((item) => (
                      <ItemCard key={item.item_id} item={item} canResolve={canResolve} />
                    ))}
                  </div>
                </details>
              ))}
            </section>
          );
        })}

        {items.length === 0 && (
          <EmptyState>
            Nothing {status}. Trigger a monitoring cycle or onboard a project to
            exercise the skills.
          </EmptyState>
        )}
      </div>
    </>
  );
}

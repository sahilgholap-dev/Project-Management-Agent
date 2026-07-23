import { ItemCard } from "@/components/ItemCard";
import { RefreshBar } from "@/components/RefreshBar";
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
    <main className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">
          Review queue
          <span className="ml-2 text-sm font-normal text-slate-500">
            {items.length} {status} item{items.length === 1 ? "" : "s"}
            {params.project_id ? ` · project ${params.project_id}` : " · all projects"}
          </span>
        </h1>
        <RefreshBar />
      </header>

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
            <h2 className="text-sm font-semibold text-slate-600">
              {TIER_LABELS[tier]}
            </h2>
            {rest.map((item) => (
              <ItemCard key={item.item_id} item={item} canResolve={canResolve} />
            ))}
            {[...clusters.entries()].map(([skill, group]) => (
              <details key={skill} className="rounded border bg-white">
                <summary className="cursor-pointer px-4 py-2 text-sm">
                  {group.length} clarification{group.length === 1 ? "" : "s"} from{" "}
                  <code className="rounded bg-slate-100 px-1">{skill}</code>
                  <span className="ml-2 text-xs text-slate-500">
                    (resolved individually — there is no batch approve)
                  </span>
                </summary>
                <div className="space-y-2 border-t p-3">
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
        <p className="rounded border bg-white p-6 text-sm text-slate-500">
          Nothing {status}. Trigger a monitoring cycle or onboard a project to
          exercise the skills.
        </p>
      )}
    </main>
  );
}

import Link from "next/link";
import { notFound } from "next/navigation";
import { OverridesForm } from "@/components/OverridesForm";
import { Badge, Card, PageHeader } from "@/components/ui";
import { ProjectDetail, requireClientUser, serverApi, serverApiOrNull } from "@/lib/api";

export default async function ProjectSettingsPage({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireClientUser();
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();
  const resolved = await serverApi<Record<string, unknown>>(`/projects/${id}/config`);

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Settings — ${project.name}`}
        description={
          <>
            Per-project config overrides (PRD section 5).{" "}
            <Link href={`/projects/${id}`}
                  className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline">
              back to dashboard
            </Link>
          </>
        }
      />

      {me.role === "client_admin" && (
        <Card title="config_overrides (JSON)">
          <OverridesForm projectId={project.project_id}
                         initial={project.config_overrides} />
        </Card>
      )}

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <h2 className="border-b border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-semibold text-slate-900">
          Resolved config (project override first, client default otherwise)
        </h2>
        <table className="w-full text-left text-xs">
          <tbody className="divide-y divide-slate-100">
            {Object.entries(resolved).map(([key, value]) => {
              const overridden = key in project.config_overrides;
              return (
                <tr key={key}>
                  <td className="w-56 px-4 py-2 font-mono text-slate-900">{key}</td>
                  <td className="px-2 py-2 font-mono text-slate-700">
                    {JSON.stringify(value)}
                  </td>
                  <td className="w-32 px-2 py-2">
                    {overridden ? (
                      <Badge tone="info">project override</Badge>
                    ) : (
                      <span className="text-slate-400">client default</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}

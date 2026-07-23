import Link from "next/link";
import { notFound } from "next/navigation";
import { OverridesForm } from "@/components/OverridesForm";
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
    <main className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold">Settings — {project.name}</h1>
        <p className="text-xs text-slate-500">
          Per-project config overrides (PRD section 5).{" "}
          <Link href={`/projects/${id}`} className="underline">back to dashboard</Link>
        </p>
      </header>

      {me.role === "client_admin" && (
        <section className="rounded border bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold">config_overrides (JSON)</h2>
          <OverridesForm projectId={project.project_id}
                         initial={project.config_overrides} />
        </section>
      )}

      <section className="rounded border bg-white">
        <h2 className="border-b bg-slate-50 px-4 py-2 text-sm font-semibold">
          Resolved config (project override first, client default otherwise)
        </h2>
        <table className="w-full text-left text-xs">
          <tbody>
            {Object.entries(resolved).map(([key, value]) => {
              const overridden = key in project.config_overrides;
              return (
                <tr key={key} className="border-b last:border-0">
                  <td className="w-56 px-4 py-1.5 font-mono">{key}</td>
                  <td className="px-2 py-1.5 font-mono">
                    {JSON.stringify(value)}
                  </td>
                  <td className="w-32 px-2 py-1.5">
                    {overridden ? (
                      <span className="rounded bg-sky-100 px-1.5 py-0.5 text-sky-800">
                        project override
                      </span>
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
    </main>
  );
}

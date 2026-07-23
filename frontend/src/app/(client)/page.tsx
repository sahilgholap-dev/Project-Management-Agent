import Link from "next/link";
import { CreateProjectForm } from "@/components/CreateProjectForm";
import { ProjectSummary, requireClientUser, serverApi } from "@/lib/api";

export default async function ProjectListPage() {
  const me = await requireClientUser(); // gate BEFORE data (403-race guard)
  const projects = await serverApi<ProjectSummary[]>("/projects");

  return (
    <main className="space-y-8">
      <section>
        <h1 className="mb-3 text-lg font-semibold">Projects</h1>
        {projects.length === 0 && (
          <p className="text-sm text-slate-500">No projects yet.</p>
        )}
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.project_id}
                className="flex items-center justify-between rounded border bg-white px-4 py-3">
              <div>
                <Link href={`/projects/${p.project_id}`}
                      className="font-medium hover:underline">
                  {p.name}
                </Link>
                <span className="ml-3 text-xs text-slate-500">
                  {p.timeline_start} → {p.timeline_end}
                </span>
              </div>
              <span className={`rounded px-2 py-0.5 text-xs ${
                p.status === "paused"
                  ? "bg-red-100 text-red-800"
                  : p.status === "archived"
                    ? "bg-slate-200 text-slate-600"
                    : "bg-emerald-100 text-emerald-800"
              }`}>
                {p.status}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {me.role === "client_admin" && (
        <section className="rounded border bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">New project</h2>
          <CreateProjectForm />
        </section>
      )}
    </main>
  );
}

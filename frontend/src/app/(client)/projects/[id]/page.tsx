import Link from "next/link";
import { notFound } from "next/navigation";
import { ProjectActions } from "@/components/ProjectActions";
import { Me, ProjectDetail, serverApi, serverApiOrNull } from "@/lib/api";

export default async function ProjectDashboard({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [project, me] = await Promise.all([
    serverApiOrNull<ProjectDetail>(`/projects/${id}`),
    serverApi<Me>("/auth/me"),
  ]);
  if (!project) notFound();

  const tasksByPhase = new Map<number, ProjectDetail["tasks"]>();
  for (const task of project.tasks) {
    const list = tasksByPhase.get(task.phase_id) ?? [];
    list.push(task);
    tasksByPhase.set(task.phase_id, list);
  }

  return (
    <main className="space-y-6">
      {/* PRD s10: paused-work state shows a VISIBLE banner */}
      {project.status === "paused" && (
        <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
          <strong>All work on this project is paused.</strong>{" "}
          {project.paused_reason}
        </div>
      )}

      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold">{project.name}</h1>
          <p className="text-xs text-slate-500">
            {project.timeline_start} → {project.timeline_end} · status {project.status}
            {project.budget_total ? ` · budget ${project.budget_total}` : ""}
          </p>
        </div>
        <Link href={`/review-queue?project_id=${project.project_id}`}
              className="rounded border px-3 py-1.5 text-xs hover:bg-slate-100">
          Review queue for this project
        </Link>
      </header>

      {me.role === "client_admin" && project.status !== "archived" && (
        <ProjectActions projectId={project.project_id} status={project.status}
                        hasPlan={project.tasks.length > 0} />
      )}

      {project.phases.length === 0 ? (
        <p className="rounded border bg-white p-4 text-sm text-slate-500">
          No plan yet — run onboarding to generate phases and tasks from the scope.
        </p>
      ) : (
        project.phases.map((phase) => (
          <section key={phase.phase_id} className="rounded border bg-white">
            <div className="flex items-center justify-between border-b bg-slate-50 px-4 py-2">
              <h2 className="text-sm font-semibold">
                {phase.sequence_order}. {phase.name}
                <span className="ml-2 font-normal text-slate-500">
                  {phase.planned_start} → {phase.planned_end} · {phase.status}
                </span>
              </h2>
              {phase.needs_clarification && (
                <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                  needs clarification
                </span>
              )}
            </div>
            <table className="w-full text-left text-xs">
              <thead className="text-slate-500">
                <tr className="border-b">
                  <th className="px-4 py-2">Task</th>
                  <th className="px-2 py-2">Owner</th>
                  <th className="px-2 py-2">Planned</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">%</th>
                  <th className="px-2 py-2">Slack</th>
                  <th className="px-2 py-2">Flags</th>
                </tr>
              </thead>
              <tbody>
                {(tasksByPhase.get(phase.phase_id) ?? []).map((t) => (
                  <tr key={t.task_id}
                      className={`border-b last:border-0 ${
                        t.on_critical_path ? "bg-rose-50" : ""
                      }`}>
                    <td className="px-4 py-2">
                      {t.on_critical_path ? (
                        <span title="critical path" className="mr-1 text-rose-600">●</span>
                      ) : null}
                      {t.title}
                      <span className="ml-2 text-slate-400">
                        {t.effort_hours != null ? `${t.effort_hours}h` : "unestimated"}
                        {t.skill_tags.length ? ` · ${t.skill_tags.join(", ")}` : ""}
                      </span>
                    </td>
                    <td className="px-2 py-2">{t.owner_name ?? "—"}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      {t.planned_start ? `${t.planned_start} → ${t.planned_end}` : "unscheduled"}
                    </td>
                    <td className="px-2 py-2">{t.status}</td>
                    <td className="px-2 py-2">{t.percent_complete ?? "—"}</td>
                    <td className="px-2 py-2">{t.slack_days ?? "—"}</td>
                    <td className="px-2 py-2">
                      {t.unassignable ? (
                        <span className="mr-1 rounded bg-red-100 px-1.5 py-0.5 text-red-800">
                          unassignable
                        </span>
                      ) : null}
                      {t.needs_clarification ? (
                        <span title={t.needs_clarification}
                              className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                          clarify
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </main>
  );
}

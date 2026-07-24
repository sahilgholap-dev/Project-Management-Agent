import Link from "next/link";
import { notFound } from "next/navigation";
import { ProjectActions } from "@/components/ProjectActions";
import { Timeline } from "@/components/Timeline";
import { Alert, Badge, EmptyState, PageHeader, statusTone } from "@/components/ui";
import { ProjectDetail, requireClientUser, serverApiOrNull } from "@/lib/api";

const tabCls =
  "rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 " +
  "hover:bg-slate-100 hover:text-slate-900";

export default async function ProjectDashboard({ params }: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireClientUser(); // gate BEFORE data (403-race guard)
  const project = await serverApiOrNull<ProjectDetail>(`/projects/${id}`);
  if (!project) notFound();

  const tasksByPhase = new Map<number, ProjectDetail["tasks"]>();
  for (const task of project.tasks) {
    const list = tasksByPhase.get(task.phase_id) ?? [];
    list.push(task);
    tasksByPhase.set(task.phase_id, list);
  }

  return (
    <div className="space-y-6">
      {/* PRD s10: paused-work state shows a VISIBLE banner */}
      {project.status === "paused" && (
        <Alert tone="danger">
          <strong>All work on this project is paused.</strong>{" "}
          {project.paused_reason}
        </Alert>
      )}

      <PageHeader
        title={project.name}
        description={
          <>
            {project.timeline_start} → {project.timeline_end} · status {project.status}
            {project.budget_total ? ` · budget ${project.budget_total}` : ""}
          </>
        }
        actions={
          // deadline lateness is its own number — slack/critical-path is
          // anchored to the computed finish and never encodes this
          project.behind_working_days > 0 ? (
            <Badge tone="danger">
              {project.behind_working_days} working day
              {project.behind_working_days === 1 ? "" : "s"} behind deadline
            </Badge>
          ) : undefined
        }
      />

      <nav className="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
        <Link href={`/projects/${project.project_id}/status`} className={tabCls}>
          Status reports
        </Link>
        <Link href={`/projects/${project.project_id}/meetings`} className={tabCls}>
          Meetings
        </Link>
        <Link href={`/projects/${project.project_id}/risks`} className={tabCls}>
          Risks
        </Link>
        <Link href={`/projects/${project.project_id}/blockers`} className={tabCls}>
          Blockers
        </Link>
        <Link href={`/projects/${project.project_id}/settings`} className={tabCls}>
          Settings
        </Link>
        <Link href={`/projects/${project.project_id}/logs`} className={tabCls}>
          Logs
        </Link>
        <Link href={`/projects/${project.project_id}/close`} className={tabCls}>
          Close
        </Link>
        <Link href={`/review-queue?project_id=${project.project_id}`} className={tabCls}>
          Review queue
        </Link>
      </nav>

      {me.role === "client_admin" && project.status !== "archived" && (
        <ProjectActions projectId={project.project_id} status={project.status}
                        hasPlan={project.tasks.length > 0} />
      )}

      {project.phases.length > 0 && (
        <Timeline phases={project.phases} tasks={project.tasks}
                  deadline={project.timeline_end} />
      )}

      {project.phases.length === 0 ? (
        <EmptyState>
          No plan yet — run onboarding to generate phases and tasks from the scope.
        </EmptyState>
      ) : (
        project.phases.map((phase) => (
          <section key={phase.phase_id}
                   className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
              <h2 className="text-sm font-semibold text-slate-900">
                {phase.sequence_order}. {phase.name}
                <span className="ml-2 font-normal text-slate-500">
                  {phase.planned_start} → {phase.planned_end} · {phase.status}
                </span>
              </h2>
              {phase.needs_clarification && (
                <Badge tone="warning">needs clarification</Badge>
              )}
            </div>
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Task</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Owner</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Planned</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Status</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">%</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Slack</th>
                  <th className="px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Flags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(tasksByPhase.get(phase.phase_id) ?? []).map((t) => (
                  <tr key={t.task_id}
                      className={t.on_critical_path ? "bg-red-50" : ""}>
                    <td className="px-4 py-2 text-slate-900">
                      {t.on_critical_path ? (
                        <span title="critical path" className="mr-1 text-red-600">●</span>
                      ) : null}
                      {t.title}
                      <span className="ml-2 text-slate-400">
                        {t.effort_hours != null ? `${t.effort_hours}h` : "unestimated"}
                        {t.skill_tags.length ? ` · ${t.skill_tags.join(", ")}` : ""}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-slate-700">{t.owner_name ?? "—"}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-slate-700">
                      {t.planned_start ? `${t.planned_start} → ${t.planned_end}` : "unscheduled"}
                    </td>
                    <td className="px-2 py-2">
                      <Badge tone={statusTone(t.status)}>{t.status}</Badge>
                    </td>
                    <td className="px-2 py-2 text-slate-700">{t.percent_complete ?? "—"}</td>
                    <td className="px-2 py-2 text-slate-700">{t.slack_days ?? "—"}</td>
                    <td className="px-2 py-2">
                      {t.unassignable ? (
                        <span className="mr-1 inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                          unassignable
                        </span>
                      ) : null}
                      {t.needs_clarification ? (
                        <span title={t.needs_clarification}
                              className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
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
    </div>
  );
}

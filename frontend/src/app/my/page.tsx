import { QuickUpdate } from "@/components/my/QuickUpdate";
import { Timeline } from "@/components/Timeline";
import { Alert, Badge, Card, EmptyState, PageHeader, statusTone } from "@/components/ui";
import { MyWork, requireMember, serverApi } from "@/lib/api";

export default async function MyWorkPage() {
  await requireMember(); // gate BEFORE data (403-race guard)
  const work = await serverApi<MyWork>("/me/work");

  if (!work.linked) {
    return (
      <>
        <PageHeader title="My Work" />
        <EmptyState>
          Your login isn&apos;t linked to a team member yet — ask your admin to
          link it on the Team page. Once linked, your tasks and timelines
          appear here.
        </EmptyState>
      </>
    );
  }

  const pending = new Set(work.pending_task_ids);
  const openTasks = work.projects.flatMap((p) => p.tasks)
    .filter((t) => t.status !== "done" && t.status !== "cancelled");
  const doneCount = work.projects.flatMap((p) => p.tasks)
    .filter((t) => t.status === "done").length;

  return (
    <>
      <PageHeader
        title={`My Work — ${work.member!.name}`}
        description={`${openTasks.length} open task(s) · ${doneCount} done · ${work.projects.length} active project(s)`}
      />
      <div className="space-y-6">
        {work.blockers.length > 0 && (
          <Alert tone="warning" title="Blockers involving you">
            <ul className="list-disc pl-4">
              {work.blockers.map((b) => (
                <li key={b.blocker_id}>
                  <span className="font-medium">{b.project_name}:</span>{" "}
                  {b.description}
                </li>
              ))}
            </ul>
          </Alert>
        )}

        {work.projects.length === 0 && (
          <EmptyState>No tasks assigned to you on any active project.</EmptyState>
        )}

        {work.projects.map((project) => (
          <Card
            key={project.project_id}
            title={project.name}
            description={`${project.timeline_start} → ${project.timeline_end} · ${project.tasks.length} of the project's tasks are yours`}
          >
            <div className="space-y-4">
              <div className="divide-y divide-slate-100">
                {project.tasks.map((t) => (
                  <div key={t.task_id}
                       className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">
                        {t.title}
                        {t.on_critical_path ? (
                          <span className="ml-2 align-middle text-[10px] font-semibold uppercase text-red-600">
                            critical path
                          </span>
                        ) : null}
                      </p>
                      <p className="text-xs text-slate-500">
                        {t.planned_start ?? "unscheduled"} → {t.planned_end ?? "?"}
                        {t.effort_hours != null ? ` · ${t.effort_hours}h` : " · no estimate yet"}
                        {t.percent_complete != null ? ` · ${t.percent_complete}%` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={statusTone(t.status)}>{t.status}</Badge>
                      {pending.has(t.task_id) ? (
                        <Badge tone="info">update pending next cycle</Badge>
                      ) : t.status !== "done" && t.status !== "cancelled" ? (
                        <QuickUpdate taskId={t.task_id}
                                     memberId={work.member!.member_id} />
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
              <Timeline phases={project.phases} tasks={project.tasks}
                        deadline={project.timeline_end} />
            </div>
          </Card>
        ))}

        <p className="text-xs text-slate-500">
          Updates are filed as status reports and applied on the next
          monitoring cycle — a submitted update shows as &quot;pending&quot;
          until then. Unclear updates are flagged for review, never guessed.
        </p>
      </div>
    </>
  );
}

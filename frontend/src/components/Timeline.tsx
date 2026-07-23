// Gantt-ish timeline: positioned divs, no charting library (plan F5 —
// "no charting library unless it stays trivial"; it stays trivial).
// Server component: pure date math, bars as % offsets of the plan span.

import type { Phase, Task } from "@/lib/api";

const DAY = 86_400_000;

function pct(from: number, to: number, span: number): { left: string; width: string } {
  return {
    left: `${(from / span) * 100}%`,
    width: `${Math.max(((to - from + DAY) / span) * 100, 0.5)}%`,
  };
}

export function Timeline({ phases, tasks }: { phases: Phase[]; tasks: Task[] }) {
  const dated = tasks.filter((t) => t.planned_start && t.planned_end);
  if (dated.length === 0) return null;

  const starts = [
    ...dated.map((t) => Date.parse(t.planned_start!)),
    ...phases.map((p) => Date.parse(p.planned_start)),
  ];
  const ends = [
    ...dated.map((t) => Date.parse(t.planned_end!)),
    ...phases.map((p) => Date.parse(p.planned_end)),
  ];
  const min = Math.min(...starts);
  const span = Math.max(...ends) - min + DAY;

  return (
    <section className="rounded border bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold">
        Timeline
        <span className="ml-3 text-xs font-normal text-slate-500">
          <span className="mr-1 inline-block h-2 w-4 rounded-sm bg-rose-500 align-middle" />
          critical path
          <span className="mx-1 ml-3 inline-block h-2 w-4 rounded-sm bg-slate-400 align-middle" />
          task
          <span className="mx-1 ml-3 inline-block h-2 w-4 rounded-sm bg-slate-200 align-middle" />
          phase
        </span>
      </h2>
      <div className="space-y-4">
        {phases.map((phase) => {
          const phaseTasks = dated.filter((t) => t.phase_id === phase.phase_id);
          const phaseBar = pct(
            Date.parse(phase.planned_start) - min,
            Date.parse(phase.planned_end) - min,
            span,
          );
          return (
            <div key={phase.phase_id}>
              <div className="relative mb-1 h-5">
                <div className="absolute inset-y-0 rounded bg-slate-200"
                     style={phaseBar} />
                <span className="absolute inset-y-0 flex items-center pl-1 text-[10px] font-medium text-slate-600"
                      style={{ left: phaseBar.left }}>
                  {phase.name} ({phase.planned_start} → {phase.planned_end})
                </span>
              </div>
              {phaseTasks.map((t) => {
                const bar = pct(
                  Date.parse(t.planned_start!) - min,
                  Date.parse(t.planned_end!) - min,
                  span,
                );
                return (
                  <div key={t.task_id} className="relative h-4">
                    <div
                      className={`absolute inset-y-0.5 rounded-sm ${
                        t.on_critical_path ? "bg-rose-500" : "bg-slate-400"
                      } ${t.status === "done" ? "opacity-40" : ""}`}
                      style={bar}
                      title={`${t.title} · ${t.planned_start} → ${t.planned_end}` +
                             `${t.owner_name ? ` · ${t.owner_name}` : ""}` +
                             ` · slack ${t.slack_days ?? "?"}d`}
                    />
                    <span
                      className="absolute inset-y-0 flex items-center pl-1 text-[10px] text-slate-700"
                      style={{ left: `calc(${bar.left} + ${bar.width})` }}
                    >
                      {t.title}
                      {t.status === "done" ? " ✓" : ""}
                    </span>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </section>
  );
}

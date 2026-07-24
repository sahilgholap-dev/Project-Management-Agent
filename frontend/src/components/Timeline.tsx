// Gantt-ish timeline: positioned divs, no charting library (plan F5 —
// "no charting library unless it stays trivial"; it stays trivial).
// Server component: pure date math, bars as % offsets of the plan span.
//
// Layout: a sticky label column + a horizontally scrollable chart pane with a
// minimum width per day, so large plans (50+ tasks, multi-month spans) scroll
// instead of compressing labels and bars into an overflowing smear. Labels
// live in their own column and can never spill past the card edge.

import type { Phase, Task } from "@/lib/api";

const DAY = 86_400_000;
const PX_PER_DAY = 18; // chart minimum width; wider viewports stretch beyond it

function pct(from: number, to: number, span: number): { left: string; width: string } {
  return {
    left: `${(from / span) * 100}%`,
    width: `${Math.max(((to - from + DAY) / span) * 100, 0.5)}%`,
  };
}

/** Monday ticks across the span, as % offsets, for the scale row + gridlines. */
function weekTicks(min: number, span: number): { left: string; label: string }[] {
  const ticks = [];
  for (let t = min; t < min + span; t += DAY) {
    if (new Date(t).getUTCDay() === 1) {
      ticks.push({
        left: `${((t - min) / span) * 100}%`,
        label: new Date(t).toISOString().slice(5, 10), // MM-DD
      });
    }
  }
  return ticks;
}

const PHASE_ROW = "h-6";
const TASK_ROW = "h-5";

export function Timeline({ phases, tasks, deadline }: {
  phases: Phase[];
  tasks: Task[];
  /** Project timeline_end: rendered as a red dashed marker so an overrunning
   *  plan visibly crosses it (pairs with the behind-deadline badge). */
  deadline?: string | null;
}) {
  const dated = tasks.filter((t) => t.planned_start && t.planned_end);
  if (dated.length === 0) return null;

  const starts = [
    ...dated.map((t) => Date.parse(t.planned_start!)),
    ...phases.map((p) => Date.parse(p.planned_start)),
  ];
  const ends = [
    ...dated.map((t) => Date.parse(t.planned_end!)),
    ...phases.map((p) => Date.parse(p.planned_end)),
    ...(deadline ? [Date.parse(deadline)] : []),
  ];
  const min = Math.min(...starts);
  const span = Math.max(...ends) - min + DAY;
  const chartMinWidth = Math.round((span / DAY) * PX_PER_DAY);
  const ticks = weekTicks(min, span);
  const deadlineLeft = deadline
    ? `${((Date.parse(deadline) - min + DAY) / span) * 100}%`
    : null;

  // label column and chart column render the same row sequence with identical
  // heights, so the two stay aligned while only the chart scrolls
  const rows: ({ kind: "phase"; phase: Phase } | { kind: "task"; task: Task })[] = [];
  for (const phase of phases) {
    rows.push({ kind: "phase", phase });
    for (const t of dated.filter((x) => x.phase_id === phase.phase_id)) {
      rows.push({ kind: "task", task: t });
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <h2 className="flex flex-wrap items-center gap-x-3 border-b border-slate-100 px-5 py-3 text-sm font-semibold text-slate-900">
        Timeline
        <span className="text-xs font-normal text-slate-500">
          <span className="mr-1 inline-block h-2 w-4 rounded-sm bg-red-500 align-middle" />
          critical path
          <span className="mx-1 ml-3 inline-block h-2 w-4 rounded-sm bg-indigo-500 align-middle" />
          task
          <span className="mx-1 ml-3 inline-block h-2 w-4 rounded-sm bg-indigo-100 align-middle" />
          phase
          {deadline && (
            <>
              <span className="ml-3 mr-1 inline-block h-2 w-0 border-l-2 border-dashed border-red-400 align-middle" />
              deadline {deadline}
            </>
          )}
        </span>
      </h2>

      <div className="overflow-x-auto">
        <div className="flex" style={{ minWidth: `${chartMinWidth + 208}px` }}>
          {/* label column — sticky so titles stay readable while scrolling */}
          <div className="sticky left-0 z-10 w-52 shrink-0 border-r border-slate-200 bg-white pl-5 pr-2">
            <div className="h-6" /> {/* scale-row spacer */}
            {rows.map((row) =>
              row.kind === "phase" ? (
                <div key={`p${row.phase.phase_id}`}
                     className={`${PHASE_ROW} flex items-center truncate pt-1 text-xs font-semibold text-indigo-900`}
                     title={`${row.phase.name} · ${row.phase.planned_start} → ${row.phase.planned_end}`}>
                  {row.phase.name}
                </div>
              ) : (
                <div key={`t${row.task.task_id}`}
                     className={`${TASK_ROW} flex items-center gap-1 truncate text-[11px] text-slate-600`}
                     title={`${row.task.title} · ${row.task.planned_start} → ${row.task.planned_end}` +
                            `${row.task.owner_name ? ` · ${row.task.owner_name}` : ""}`}>
                  {row.task.on_critical_path ? (
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
                  ) : null}
                  <span className="truncate">
                    {row.task.title}
                    {row.task.status === "done" ? " ✓" : ""}
                  </span>
                </div>
              ),
            )}
          </div>

          {/* chart column */}
          <div className="relative min-w-0 flex-1 pr-5">
            {/* week gridlines spanning the full chart height */}
            {ticks.map((tick) => (
              <div key={tick.left}
                   className="absolute inset-y-0 border-l border-slate-100"
                   style={{ left: tick.left }} />
            ))}
            {deadlineLeft && (
              <div className="absolute inset-y-0 z-[1] border-l-2 border-dashed border-red-400"
                   style={{ left: deadlineLeft }}
                   title={`deadline ${deadline}`} />
            )}

            {/* week scale */}
            <div className="relative h-6 border-b border-slate-100">
              {ticks.map((tick) => (
                <span key={tick.left}
                      className="absolute top-1 pl-1 text-[10px] text-slate-400"
                      style={{ left: tick.left }}>
                  {tick.label}
                </span>
              ))}
            </div>

            {rows.map((row) => {
              if (row.kind === "phase") {
                const bar = pct(
                  Date.parse(row.phase.planned_start) - min,
                  Date.parse(row.phase.planned_end) - min,
                  span,
                );
                return (
                  <div key={`p${row.phase.phase_id}`} className={`relative ${PHASE_ROW}`}>
                    <div className="absolute inset-y-1.5 rounded-md border border-indigo-200 bg-indigo-100"
                         style={bar}
                         title={`${row.phase.name} · ${row.phase.planned_start} → ${row.phase.planned_end}`} />
                  </div>
                );
              }
              const t = row.task;
              const bar = pct(
                Date.parse(t.planned_start!) - min,
                Date.parse(t.planned_end!) - min,
                span,
              );
              return (
                <div key={`t${t.task_id}`} className={`relative ${TASK_ROW}`}>
                  <div
                    className={`absolute inset-y-1 rounded-sm ${
                      t.on_critical_path ? "bg-red-500" : "bg-indigo-500"
                    } ${t.status === "done" ? "opacity-40" : ""}`}
                    style={bar}
                    title={`${t.title} · ${t.planned_start} → ${t.planned_end}` +
                           `${t.owner_name ? ` · ${t.owner_name}` : ""}` +
                           ` · slack ${t.slack_days ?? "?"}d`}
                  />
                </div>
              );
            })}
            <div className="h-2" /> {/* bottom padding inside scroll pane */}
          </div>
        </div>
      </div>
    </section>
  );
}

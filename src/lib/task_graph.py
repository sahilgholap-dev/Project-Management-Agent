"""Shared dependency graph (used by Scheduler 8.2 and Dependency Manager 8.6).

Finish-to-Start edges only, no lag/lead (confirmed Q8). A cycle is a loud
failure, never silently tolerated."""

from __future__ import annotations

import sqlite3
from graphlib import CycleError, TopologicalSorter


class DependencyCycleError(Exception):
    pass


class TaskGraph:
    def __init__(self, task_ids: list[int], edges: list[tuple[int, int]]):
        """edges are (predecessor_task_id, successor_task_id)."""
        self.task_ids = list(task_ids)
        self.predecessors: dict[int, set[int]] = {t: set() for t in task_ids}
        self.successors: dict[int, set[int]] = {t: set() for t in task_ids}
        for pred, succ in edges:
            if pred in self.predecessors and succ in self.predecessors:
                self.predecessors[succ].add(pred)
                self.successors[pred].add(succ)

    @classmethod
    def for_project(
        cls, conn: sqlite3.Connection, project_id: int,
        include_unestimated: bool = False,
    ) -> TaskGraph:
        """Graph over the project's schedulable tasks (not cancelled).

        By default NULL-effort tasks are excluded — they have no duration and
        cannot participate in CPM (NEW-OQ 4 treatment). The Scheduler uses
        include_unestimated=True to build the FULL graph first, so exclusion
        cascades: everything downstream of an unestimated task is also
        excluded and flagged, never scheduled as if the dependency didn't
        exist."""
        effort_filter = "" if include_unestimated else " AND effort_hours IS NOT NULL"
        task_ids = [
            r["task_id"]
            for r in conn.execute(
                "SELECT task_id FROM tasks WHERE project_id = ? AND status != 'cancelled'"
                + effort_filter,
                (project_id,),
            )
        ]
        edges = [
            (r["predecessor_task_id"], r["successor_task_id"])
            for r in conn.execute(
                "SELECT d.predecessor_task_id, d.successor_task_id"
                " FROM task_dependencies d"
                " JOIN tasks t ON t.task_id = d.predecessor_task_id"
                " WHERE t.project_id = ?",
                (project_id,),
            )
        ]
        return cls(task_ids, edges)

    def topological_order(self) -> list[int]:
        sorter = TopologicalSorter(self.predecessors)
        try:
            return list(sorter.static_order())
        except CycleError as err:
            raise DependencyCycleError(f"dependency cycle detected: {err.args[1]}") from err

    def without(self, excluded: set[int]) -> TaskGraph:
        """A new graph with the excluded nodes (and their edges) removed."""
        remaining = [t for t in self.task_ids if t not in excluded]
        edges = [
            (pred, succ)
            for succ, preds in self.predecessors.items() if succ not in excluded
            for pred in preds if pred not in excluded
        ]
        return TaskGraph(remaining, edges)

    def descendants(self, task_id: int) -> set[int]:
        """Every task downstream of task_id (excluding itself)."""
        seen: set[int] = set()
        frontier = list(self.successors.get(task_id, ()))
        while frontier:
            node = frontier.pop()
            if node not in seen:
                seen.add(node)
                frontier.extend(self.successors.get(node, ()))
        return seen

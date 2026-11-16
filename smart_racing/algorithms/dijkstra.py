"""Dijkstra's shortest path on the hand-written binary heap."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from smart_racing.algorithms.heap import MinHeap
from smart_racing.core.cost import CostFn, distance_cost
from smart_racing.core.graph import TrackGraph

Observer = Callable[[dict], None]


@dataclass
class PathResult:
    """Result of Dijkstra and A*."""
    algorithm: str
    source: int
    target: int | None = None
    found: bool = False
    path: list[int] = field(default_factory=list)        # vertex ids source..target
    edge_path: list[int] = field(default_factory=list)   # edge ids along `path`
    cost: float = math.inf                               # optimal cost to target
    # Best known cost per discovered vertex. Final for every vertex in `closed`.
    dist: dict[int, float] = field(default_factory=dict)
    parent: dict[int, tuple[int, int] | None] = field(default_factory=dict)  # v -> (prev, edge id)
    closed: set[int] = field(default_factory=set)        # expanded vertices
    expanded: int = 0              # vertices settled
    relaxed: int = 0               # successful relaxations
    edges_examined: int = 0
    heap_ops: int = 0              # pushes + pops
    heap_comparisons: int = 0
    heuristic_ratio: float | None = None   # A* only: min cost per straight-line unit

    def path_to(self, vertex: int) -> tuple[list[int], list[int]]:
        """(vertex path, edge path) from the source, or ([], []) if undiscovered."""
        if vertex not in self.parent:
            return [], []
        path, edges = [vertex], []
        while self.parent[path[-1]] is not None:
            prev, edge_id = self.parent[path[-1]]
            path.append(prev)
            edges.append(edge_id)
        return path[::-1], edges[::-1]


def checked_cost(cost_fn: CostFn, edge) -> float:
    cost = cost_fn(edge)
    if cost < 0:
        raise ValueError(f"negative cost {cost} on edge {edge.id}")
    return cost


def dijkstra(graph: TrackGraph, source: int, target: int | None = None,
             cost_fn: CostFn = distance_cost, observer: Observer | None = None) -> PathResult:
    """Cheapest path under non-negative `cost_fn(edge)` over traversable edges.

    With a `target` the search stops when the target is settled. Without one it
    settles every reachable vertex (`dist` is then the full shortest-path map).
    An unreachable target gives `found=False`, `cost=inf` and an empty path.
    Decrease-key is done by pushing a new entry and skipping stale ones. Ties
    are broken by lower vertex id, and a parent changes only on strict
    improvement, so results are deterministic.

    Time O((V + E) log V), space O(V + E).
    """
    graph.vertex(source)
    if target is not None:
        graph.vertex(target)
    res = PathResult("dijkstra", source, target)
    res.dist[source] = 0.0
    res.parent[source] = None
    heap = MinHeap()
    heap.push((0.0, source), source)
    while heap:
        (d, _), u = heap.pop()
        if u in res.closed:
            continue                     # stale entry
        res.closed.add(u)
        res.expanded += 1
        if observer:
            observer({"type": "expand", "vertex": u, "dist": d, "frontier": len(heap)})
        if u == target:
            break
        for edge, w in graph.neighbors(u):
            res.edges_examined += 1
            if w in res.closed:
                continue
            new = d + checked_cost(cost_fn, edge)
            improved = new < res.dist.get(w, math.inf)
            if improved:
                res.dist[w] = new
                res.parent[w] = (u, edge.id)
                res.relaxed += 1
                heap.push((new, w), w)
            if observer:
                observer({"type": "relax", "edge": edge.id, "from": u, "to": w,
                          "dist": new, "improved": improved})
    res.heap_ops, res.heap_comparisons = heap.ops, heap.comparisons
    if target is not None and target in res.closed:
        res.found = True
        res.cost = res.dist[target]
        res.path, res.edge_path = res.path_to(target)
    if observer:
        observer({"type": "done", "found": res.found, "path": res.path,
                  "edge_path": res.edge_path, "cost": res.cost})
    return res

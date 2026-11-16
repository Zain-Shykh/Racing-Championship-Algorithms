"""A* search with the straight-line heuristic of SPEC 4.4."""
from __future__ import annotations

import math
from typing import Callable

from smart_racing.algorithms.dijkstra import PathResult, checked_cost
from smart_racing.algorithms.heap import MinHeap
from smart_racing.core.cost import CostFn, distance_cost
from smart_racing.core.graph import TrackGraph

Observer = Callable[[dict], None]


def min_cost_ratio(graph: TrackGraph, cost_fn: CostFn) -> float:
    """Smallest `cost(e) / straight_line(e)` over unblocked edges whose
    endpoints do not coincide; 0.0 when there is no such edge. O(E)."""
    best = math.inf
    for edge in graph.edges():
        if edge.blocked:
            continue
        line = graph.straight_line(edge.src, edge.dst)
        if line > 0:
            best = min(best, checked_cost(cost_fn, edge) / line)
    return best if best < math.inf else 0.0


def astar(graph: TrackGraph, source: int, target: int,
          cost_fn: CostFn = distance_cost, observer: Observer | None = None) -> PathResult:
    """Cheapest path from `source` to `target` under non-negative `cost_fn`.

    h(u) = straight_line(u, target) * r with r = min_cost_ratio, recomputed on
    every call because events change costs. Every edge costs at least
    r * straight_line(edge), so by the triangle inequality h is admissible and
    consistent: a closed vertex is never reopened and the result has the same
    cost as Dijkstra. If r is 0 the search degenerates to Dijkstra.
    Heap key is (f, vertex id); stale entries are skipped.

    Time O(E) for r plus O((V + E) log V) worst case; space O(V + E).
    """
    graph.vertex(source)
    graph.vertex(target)
    ratio = min_cost_ratio(graph, cost_fn)

    def h(v: int) -> float:
        return graph.straight_line(v, target) * ratio

    res = PathResult("astar", source, target, heuristic_ratio=ratio)
    res.dist[source] = 0.0
    res.parent[source] = None
    heap = MinHeap()
    heap.push((h(source), source), source)
    while heap:
        (f, _), u = heap.pop()
        if u in res.closed:
            continue                     # stale entry
        res.closed.add(u)
        res.expanded += 1
        g = res.dist[u]
        if observer:
            observer({"type": "expand", "vertex": u, "dist": g, "h": f - g, "f": f,
                      "frontier": len(heap)})
        if u == target:
            break
        for edge, w in graph.neighbors(u):
            res.edges_examined += 1
            if w in res.closed:
                continue
            new = g + checked_cost(cost_fn, edge)
            improved = new < res.dist.get(w, math.inf)
            if improved:
                res.dist[w] = new
                res.parent[w] = (u, edge.id)
                res.relaxed += 1
                heap.push((new + h(w), w), w)
            if observer:
                observer({"type": "relax", "edge": edge.id, "from": u, "to": w,
                          "dist": new, "improved": improved})
    res.heap_ops, res.heap_comparisons = heap.ops, heap.comparisons
    if target in res.closed:
        res.found = True
        res.cost = res.dist[target]
        res.path, res.edge_path = res.path_to(target)
    if observer:
        observer({"type": "done", "found": res.found, "path": res.path,
                  "edge_path": res.edge_path, "cost": res.cost})
    return res

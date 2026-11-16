"""Breadth-first search: reachability and minimum-edge-count paths."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from smart_racing.core.graph import TrackGraph

Observer = Callable[[dict], None]


@dataclass
class BFSResult:
    source: int
    target: int | None = None
    found: bool = False                 # target reached (always False without a target)
    path: list[int] = field(default_factory=list)       # vertex ids source..target
    edge_path: list[int] = field(default_factory=list)  # edge ids along `path`
    order: list[int] = field(default_factory=list)      # vertices in dequeue order
    dist: dict[int, int] = field(default_factory=dict)  # edge count from source
    parent: dict[int, tuple[int, int] | None] = field(default_factory=dict)  # v -> (prev, edge id)
    visited: int = 0                    # vertices dequeued
    edges_examined: int = 0

    @property
    def reachable(self) -> set[int]:
        """Vertices discovered from the source (all reachable ones when the
        search ran without a target)."""
        return set(self.dist)

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


def bfs(graph: TrackGraph, source: int, target: int | None = None,
        observer: Observer | None = None) -> BFSResult:
    """BFS over traversable edges from `source`.

    With a `target` it stops as soon as the target is discovered and returns a
    path with the minimum number of edges (not minimum distance or cost).
    Without one it explores everything reachable. An unreachable target gives
    `found=False` and an empty path.

    Time O(V + E), auxiliary space O(V).
    """
    graph.vertex(source)
    if target is not None:
        graph.vertex(target)
    res = BFSResult(source, target)
    res.dist[source] = 0
    res.parent[source] = None
    queue = deque([source])
    done = source == target
    while queue and not done:
        u = queue.popleft()
        res.order.append(u)
        res.visited += 1
        if observer:
            observer({"type": "visit", "vertex": u, "depth": res.dist[u], "frontier": list(queue)})
        for edge, w in graph.neighbors(u):
            res.edges_examined += 1
            new = w not in res.dist
            if new:
                res.dist[w] = res.dist[u] + 1
                res.parent[w] = (u, edge.id)
                queue.append(w)
            if observer:
                observer({"type": "examine", "edge": edge.id, "from": u, "to": w,
                          "discovered": new, "depth": res.dist[w]})
            if new and w == target:
                done = True
                break
    if target is not None and target in res.dist:
        res.found = True
        res.path, res.edge_path = res.path_to(target)
    if observer:
        observer({"type": "done", "found": res.found, "path": res.path,
                  "edge_path": res.edge_path, "visited": res.visited})
    return res

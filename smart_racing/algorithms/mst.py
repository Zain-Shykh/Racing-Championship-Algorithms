"""Kruskal's minimum spanning tree / forest with union-find."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Hashable, Iterable

from smart_racing.algorithms.sorting import merge_sort

Observer = Callable[[dict], None]
WeightedEdge = tuple[int, Hashable, Hashable, float]     # (edge id, u, v, weight)


class UnionFind:
    """Disjoint sets with union by rank and path compression.

    A sequence of m operations costs O(m * alpha(n)), alpha being the inverse
    Ackermann function. Counters: `finds` (find calls), `unions` (successful merges).
    """

    def __init__(self, items: Iterable[Hashable]) -> None:
        self.parent = {x: x for x in items}
        self.rank = dict.fromkeys(self.parent, 0)
        self.finds = self.unions = 0

    def find(self, x: Hashable) -> Hashable:
        self.finds += 1
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:            # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: Hashable, b: Hashable) -> bool:
        """Merge the sets of `a` and `b`. False if they were already one set."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.unions += 1
        return True


@dataclass
class MSTResult:
    edges: list[WeightedEdge] = field(default_factory=list)   # chosen edges in acceptance order
    total_weight: float = 0.0
    components: int = 0            # trees in the result
    is_spanning_tree: bool = False # one tree covering every vertex; otherwise a spanning forest
    edges_examined: int = 0
    comparisons: int = 0           # comparisons made while sorting the edges
    finds: int = 0
    unions: int = 0


def kruskal(vertices: Iterable[Hashable], edges: Iterable[WeightedEdge],
            observer: Observer | None = None) -> MSTResult:
    """Minimum spanning tree of an undirected weighted graph, or a minimum
    spanning forest when the graph is disconnected (`is_spanning_tree=False`).

    Edges are taken in ascending `(weight, edge id)` order, which makes the
    result deterministic, and an edge is accepted when it joins two different
    components. Self-loops and parallel edges are handled by that same test.

    Time O(E log E) for the hand-written merge sort plus O(E alpha(V)) for
    union-find; space O(V + E).
    """
    sets = UnionFind(vertices)
    edges = list(edges)
    for edge_id, u, v, _ in edges:
        if u not in sets.parent or v not in sets.parent:
            raise ValueError(f"edge {edge_id} uses an unknown vertex")
    res = MSTResult(components=len(sets.parent))
    ordered = merge_sort(edges, lambda a, b: (a[3], a[0]) < (b[3], b[0]))
    res.comparisons = ordered.comparisons
    for edge in ordered.items:
        if res.components <= 1:
            break                                # tree complete
        edge_id, u, v, weight = edge
        res.edges_examined += 1
        accepted = sets.union(u, v)
        if accepted:
            res.edges.append(edge)
            res.total_weight += weight
            res.components -= 1
        if observer:
            observer({"type": "edge", "edge": edge_id, "u": u, "v": v, "weight": weight,
                      "accepted": accepted, "components": res.components})
    res.is_spanning_tree = res.components == 1
    res.finds, res.unions = sets.finds, sets.unions
    if observer:
        observer({"type": "done", "edges": [e[0] for e in res.edges], "weight": res.total_weight,
                  "components": res.components})
    return res

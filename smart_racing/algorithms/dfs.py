"""Depth-first search: traversal, cycle detection, connected components,
dead-end analysis and bounded simple-path enumeration.

All searches are iterative (explicit stack), so deep graphs cannot hit the
Python recursion limit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from smart_racing import config
from smart_racing.core.graph import TrackGraph

Observer = Callable[[dict], None]


# --- traversal ----------------------------------------------------------------
@dataclass
class DFSResult:
    source: int
    order: list[int] = field(default_factory=list)       # discovery (pre) order
    postorder: list[int] = field(default_factory=list)   # finish order
    parent: dict[int, tuple[int, int] | None] = field(default_factory=dict)  # v -> (prev, edge id)
    visited: int = 0
    edges_examined: int = 0

    @property
    def reachable(self) -> set[int]:
        return set(self.parent)


def dfs(graph: TrackGraph, source: int, observer: Observer | None = None) -> DFSResult:
    """Depth-first traversal over traversable edges from `source`.

    Time O(V + E), auxiliary space O(V).
    """
    graph.vertex(source)
    res = DFSResult(source)

    def discover(v: int, via: tuple[int, int] | None) -> None:
        res.parent[v] = via
        res.order.append(v)
        res.visited += 1
        stack.append((v, graph.neighbors(v)))
        if observer:
            observer({"type": "visit", "vertex": v, "depth": len(stack) - 1,
                      "from": via[0] if via else None, "edge": via[1] if via else None})

    stack: list = []
    discover(source, None)
    while stack:
        u, pending = stack[-1]
        for edge, w in pending:
            res.edges_examined += 1
            new = w not in res.parent
            if observer:
                observer({"type": "examine", "edge": edge.id, "from": u, "to": w, "discovered": new})
            if new:
                discover(w, (u, edge.id))
                break
        else:
            stack.pop()
            res.postorder.append(u)
            if observer:
                observer({"type": "backtrack", "vertex": u})
    return res


# --- cycle detection ----------------------------------------------------------
@dataclass
class CycleResult:
    has_cycle: bool = False
    cycle: list[int] = field(default_factory=list)   # closed vertex walk, first == last
    visited: int = 0
    edges_examined: int = 0


def _tree_path(a: int, b: int, parent: dict, depth: dict) -> list[int]:
    """Vertices from a to b along the DFS tree that contains both."""
    left, right = [a], [b]
    while a != b:
        if depth[a] >= depth[b]:
            a = parent[a][0]
            left.append(a)
        else:
            b = parent[b][0]
            right.append(b)
    return left + right[-2::-1]


def find_cycle(graph: TrackGraph, observer: Observer | None = None) -> CycleResult:
    """Find a cycle (a closed walk that repeats no edge) among traversable edges.

    Works on graphs mixing two-way and one-way roads with two DFS passes:
    1. DFS over two-way edges only. A non-tree edge closes an undirected cycle.
    2. If there is none, the two-way edges form a forest. Contract every tree
       to one node and run a white/grey/black DFS over the one-way edges; an
       edge into a grey node closes a cycle, which is lifted back through the
       tree paths.

    Time O(V + E), auxiliary space O(V + E).
    """
    res = CycleResult()

    def finish(cycle: list[int]) -> CycleResult:
        res.has_cycle, res.cycle = True, cycle
        if observer:
            observer({"type": "cycle", "cycle": cycle})
        return res

    # Pass 1: two-way edges.
    parent: dict[int, tuple[int, int] | None] = {}
    depth: dict[int, int] = {}
    tree: dict[int, int] = {}            # vertex -> root of its two-way tree
    for root in graph.vertex_ids():
        if root in parent:
            continue
        parent[root], depth[root], tree[root] = None, 0, root
        res.visited += 1
        stack = [(root, graph.neighbors(root))]
        while stack:
            u, pending = stack[-1]
            for edge, w in pending:
                if edge.directed:
                    continue
                res.edges_examined += 1
                if parent[u] is not None and parent[u][1] == edge.id:
                    continue             # the edge we arrived by is not a cycle
                if observer:
                    observer({"type": "examine", "edge": edge.id, "from": u, "to": w,
                              "discovered": w not in parent})
                if w in parent:
                    return finish(_tree_path(w, u, parent, depth) + [w])
                parent[w], depth[w], tree[w] = (u, edge.id), depth[u] + 1, root
                res.visited += 1
                stack.append((w, graph.neighbors(w)))
                break
            else:
                stack.pop()

    # Pass 2: one-way edges between contracted trees.
    out: dict[int, list] = {}
    for edge in graph.edges():
        if edge.directed and not edge.blocked:
            out.setdefault(tree[edge.src], []).append(edge)
    grey, black = {}, set()              # grey: node -> number of trail edges at entry
    for root in sorted(out):
        if root in black:
            continue
        grey[root] = 0
        trail: list = []                 # one-way edges on the current DFS branch
        stack = [(root, iter(out[root]))]
        while stack:
            node, pending = stack[-1]
            for edge in pending:
                res.edges_examined += 1
                nxt = tree[edge.dst]
                if observer:
                    observer({"type": "examine", "edge": edge.id, "from": edge.src,
                              "to": edge.dst, "discovered": nxt not in grey and nxt not in black})
                if nxt in grey:
                    loop = trail[grey[nxt]:] + [edge]
                    cycle = [loop[0].src]
                    for i, e in enumerate(loop):
                        cycle += _tree_path(e.dst, loop[(i + 1) % len(loop)].src, parent, depth)
                    return finish(cycle)
                if nxt not in black:
                    trail.append(edge)
                    grey[nxt] = len(trail)
                    stack.append((nxt, iter(out.get(nxt, ()))))
                    break
            else:
                stack.pop()
                del grey[node]
                black.add(node)
                if trail:
                    trail.pop()
    return res


# --- connected components -----------------------------------------------------
@dataclass
class ComponentsResult:
    components: list[list[int]] = field(default_factory=list)   # each sorted, ordered by smallest id
    component_of: dict[int, int] = field(default_factory=dict)  # vertex -> index in `components`
    visited: int = 0
    edges_examined: int = 0

    @property
    def count(self) -> int:
        return len(self.components)


def connected_components(graph: TrackGraph, observer: Observer | None = None) -> ComponentsResult:
    """Connected components by DFS. Road direction is ignored (weak
    connectivity); currently blocked edges do not connect anything.

    Time O(V + E), auxiliary space O(V).
    """
    res = ComponentsResult()
    for root in graph.vertex_ids():
        if root in res.component_of:
            continue
        index = len(res.components)
        members = []
        res.component_of[root] = index
        stack = [root]
        while stack:
            u = stack.pop()
            members.append(u)
            res.visited += 1
            if observer:
                observer({"type": "visit", "vertex": u, "component": index})
            for edge, w in graph.incident(u):
                res.edges_examined += 1
                if not edge.blocked and w not in res.component_of:
                    res.component_of[w] = index
                    stack.append(w)
        res.components.append(sorted(members))
    return res


# --- dead-end analysis --------------------------------------------------------
@dataclass
class DeadEndResult:
    dead_ends: list[int] = field(default_factory=list)   # ascending vertex ids
    states: int = 0                # (arrival edge, vertex) states explored
    edges_examined: int = 0


def dead_ends(graph: TrackGraph, start: int | None = None, finish: int | None = None,
              observer: Observer | None = None) -> DeadEndResult:
    """Dead ends: non-mandatory vertices from which the finish cannot be
    reached without reversing (Project.md 5.1).

    "Reversing" is leaving a vertex by the edge just used to arrive. A driving
    state is `(arrival edge, vertex)`. One DFS from the start collects every
    state reachable without reversing; a second DFS over the reversed state
    graph marks the states that can still reach the finish. A vertex is a dead
    end when it is not Start/Finish/Checkpoint, can be driven to, and none of
    its arrival states can reach the finish. Vertices that cannot be reached
    from the start at all are not reported here (see connected_components/bfs).
    `start` and `finish` default to the graph's Start and Finish vertices.

    Time and space O(sum over v of deg(v)^2) <= O(E * max degree).
    """
    start = graph.start.id if start is None else start
    finish = graph.finish.id if finish is None else finish
    res = DeadEndResult()
    before: dict[tuple[int, int], list[tuple[int, int]]] = {}   # state -> predecessor states
    seen: set[tuple[int, int]] = set()
    stack = [(edge.id, w) for edge, w in graph.neighbors(start)]
    while stack:
        state = stack.pop()
        if state in seen:
            continue
        seen.add(state)
        for edge, w in graph.neighbors(state[1]):
            res.edges_examined += 1
            if edge.id != state[0]:
                before.setdefault((edge.id, w), []).append(state)
                stack.append((edge.id, w))
    res.states = len(seen)

    escapes = {state for state in seen if state[1] == finish}
    stack = list(escapes)
    while stack:
        for prev in before.get(stack.pop(), ()):
            if prev not in escapes:
                escapes.add(prev)
                stack.append(prev)

    arrived = {v for _, v in seen}
    safe = {v for _, v in escapes}
    res.dead_ends = sorted(v for v in arrived - safe - {start, finish}
                           if not graph.vertex(v).is_mandatory)
    if observer:
        for v in res.dead_ends:
            observer({"type": "dead_end", "vertex": v})
    return res


# --- bounded simple-path enumeration -----------------------------------------
@dataclass
class PathsResult:
    paths: list[list[int]] = field(default_factory=list)        # vertex ids
    edge_paths: list[list[int]] = field(default_factory=list)   # edge ids, parallel to `paths`
    route_limit_hit: bool = False      # stopped at max_routes: more paths may exist
    length_limit_hit: bool = False     # at least one branch was cut by max_length
    edges_examined: int = 0


def enumerate_paths(graph: TrackGraph, source: int, target: int,
                    max_routes: int = config.ALT_ROUTE_LIMIT,
                    max_length: int = config.ALT_PATH_MAX_EDGES,
                    exclude: list[int] | None = None,
                    observer: Observer | None = None) -> PathsResult:
    """Simple paths from `source` to `target` by DFS backtracking, in
    deterministic (ascending edge id) order.

    At most `max_routes` paths are returned and no path has more than
    `max_length` edges. `exclude` is the edge-id list of the main route: that
    exact route is skipped, so the result is the list of alternative routes
    (simple paths differing from the main route by at least one edge).

    Unbounded enumeration is exponential. With the limits the work is bounded
    by O(b^max_length) for branching factor b and stops early at `max_routes`.
    Space O(max_length + output).
    """
    graph.vertex(source)
    graph.vertex(target)
    res = PathsResult()
    if max_routes <= 0:
        return res
    if source == target:
        if exclude != []:
            res.paths.append([source])
            res.edge_paths.append([])
        return res
    path, edges, on_path = [source], [], {source}
    stack = [graph.neighbors(source)]
    while stack and not res.route_limit_hit:
        for edge, w in stack[-1]:
            res.edges_examined += 1
            if w in on_path:
                continue
            if w == target:
                found = edges + [edge.id]
                if found != exclude:
                    res.paths.append(path + [w])
                    res.edge_paths.append(found)
                    if observer:
                        observer({"type": "path", "path": path + [w], "edge_path": found})
                    if len(res.paths) >= max_routes:
                        res.route_limit_hit = True
                        break
                continue
            if len(edges) + 1 >= max_length:
                res.length_limit_hit = True
                continue
            path.append(w)
            edges.append(edge.id)
            on_path.add(w)
            stack.append(graph.neighbors(w))
            if observer:
                observer({"type": "visit", "vertex": w, "edge": edge.id, "depth": len(edges)})
            break
        else:
            stack.pop()
            on_path.discard(path.pop())
            if edges:
                edges.pop()
            if observer and path:
                observer({"type": "backtrack", "vertex": path[-1]})
    return res

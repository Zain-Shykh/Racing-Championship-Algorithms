"""Experiment 1: BFS and DFS on sparse and denser graphs (Project.md section 7).

Run alone: `.venv/bin/python -m smart_racing.experiments.exp1_bfs_dfs [--quick]`
"""
from __future__ import annotations

from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import connected_components, dfs, find_cycle
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.experiments import common as X

# family -> (extra edges per vertex, number of components)
FAMILIES = {"sparse": (0.5, 1), "dense": (5.0, 1), "forest": (0.0, 8)}
SIZES = [1000, 2000, 5000, 10000, 20000]
QUICK_SIZES = [60, 120]


def check(g, n: int, parts: int, cyclic: bool, results: dict) -> None:
    """Correctness conditions, outside every timed region."""
    block = set(range(0, n, parts))                       # vertices of the source's component
    degree_sum = sum(1 for v in block for _ in g.neighbors(v))
    b, d, comps, cyc = results["bfs"], results["dfs"], results["components"], results["cycle"]
    # BFS minimum edge count, check 1: optimality certificate. dist[source] = 0, no
    # road shortens a label, and every other vertex has a neighbour one level closer.
    assert b.dist[0] == 0 and set(b.dist) == block
    closer = {0}
    for u in block:
        for _, w in g.neighbors(u):
            assert b.dist[w] <= b.dist[u] + 1
            if b.dist[w] == b.dist[u] + 1:
                closer.add(w)
    assert closer == block
    # check 2: a different algorithm (Dijkstra with unit edge cost) gives the same counts.
    unit = dijkstra(g, 0, cost_fn=lambda edge: 1.0)
    assert unit.dist == {v: float(k) for v, k in b.dist.items()}
    # check 3: the returned path to the farthest vertex is a real path of that length.
    far = max(b.dist, key=lambda v: (b.dist[v], v))
    path = bfs(g, 0, far)
    assert path.found and len(path.edge_path) == b.dist[far] and path.path[0] == 0 and path.path[-1] == far
    for (u, w), edge_id in zip(zip(path.path, path.path[1:]), path.edge_path):
        assert {g.edge(edge_id).src, g.edge(edge_id).dst} == {u, w}
    # DFS against the known construction.
    assert set(d.order) == block == set(d.postorder) and d.visited == len(block)
    assert b.visited == len(block) and b.edges_examined == d.edges_examined == degree_sum
    assert comps.count == parts and comps.visited == n
    assert comps.components == [list(range(k, n, parts)) for k in range(parts)]
    assert cyc.has_cycle == cyclic
    if cyclic:
        assert cyc.cycle[0] == cyc.cycle[-1] and len(cyc.cycle) >= 3
        for u, w in zip(cyc.cycle, cyc.cycle[1:]):
            assert any(other == w for _, other in g.neighbors(u))


def run(cfg: X.Config) -> str:
    raw: list[dict] = []
    sizes = QUICK_SIZES if cfg.quick else SIZES
    algorithms = {"bfs": lambda g: bfs(g, 0), "dfs": lambda g: dfs(g, 0),
                  "components": connected_components, "cycle": find_cycle}
    for family, (extra, parts) in FAMILIES.items():
        for n in sizes:
            g = X.random_graph(n, int(extra * n), cfg.seed + n, parts)
            fields = {"family": family, "V": n, "E": g.num_edges, "V_plus_E": n + g.num_edges,
                      "components_built": parts, "cycle_built": extra > 0}
            results = {}
            for name, fn in algorithms.items():
                results[name] = X.record(
                    raw, cfg, {**fields, "algorithm": name}, lambda fn=fn: fn(g),
                    lambda r: {"visited": r.visited, "edges_examined": r.edges_examined})
            check(g, n, parts, extra > 0, results)
    summary = X.save_tables(cfg, "exp1", raw)
    for row in summary:
        row["ns_per_V_plus_E"] = row["median_ms"] * 1e6 / row["V_plus_E"]

    fig, (left, right) = X.new_axes("Experiment 1: BFS and DFS full traversal from one source",
                                    "V + E (vertices + edges)", "median runtime (ms)", ncols=2)
    index = 0
    for family in ("sparse", "dense"):
        for name in ("bfs", "dfs"):
            rows = X.pick(summary, family=family, algorithm=name)
            xs = [r["V_plus_E"] for r in rows]
            X.series(left, xs, [r["median_ms"] for r in rows], index, f"{name.upper()} {family}")
            X.series(right, xs, [r["ns_per_V_plus_E"] for r in rows], index, f"{name.upper()} {family}")
            index += 1
    left.set_title("Runtime against the O(V + E) term", fontsize=10)
    right.set_title("Runtime divided by (V + E): flat = linear", fontsize=10)
    right.set_ylabel("ns per unit of V + E")
    right.set_xscale("log")
    right.set_ylim(bottom=0)
    left.legend()
    right.legend()
    X.save_fig(fig, cfg, "exp1_runtime.png")

    def span(family, name):
        rows = X.pick(summary, family=family, algorithm=name)
        lo, hi = rows[0], rows[-1]
        per = [r["ns_per_V_plus_E"] for r in rows]
        return (f"- {name} on {family}: V+E grew {hi['V_plus_E'] / lo['V_plus_E']:.1f}x "
                f"({lo['V_plus_E']:,} to {hi['V_plus_E']:,}), median time grew "
                f"{hi['median_ms'] / lo['median_ms']:.1f}x ({lo['median_ms']:.3f} ms to "
                f"{hi['median_ms']:.2f} ms); time per unit of V+E between {min(per):.0f} and {max(per):.0f} ns.")

    table = [r for r in summary if r["algorithm"] in ("bfs", "dfs", "components")]
    cyc = X.pick(summary, algorithm="cycle")
    return f"""## Experiment 1: BFS and DFS

**Objective.** Measure how the gameplay BFS (`algorithms/bfs.py: bfs`) and DFS
(`algorithms/dfs.py: dfs`, `connected_components`, `find_cycle`) grow with graph size on
sparse and denser graphs, and compare with the O(V + E) bound.

**Environment.** {X.env_line(cfg)}

**Input generation.** `common.random_graph(V, extra, seed={cfg.seed} + V, components)`: V random
points in a 1000 x 1000 square; vertex i belongs to block i mod components; each block is joined
by a random tree and then receives random extra two-way roads. Edge distance = straight line x
U(1.0, 1.3). Families: sparse (0.5 V extra roads, E about 1.5 V), dense (5 V extra roads, E about
6 V), forest (8 trees, no extra road, E = V - 8).

**Dataset sizes.** V in {sizes}; E from {min(r['E'] for r in summary):,} to {max(r['E'] for r in summary):,}.

**Procedure.** For each graph: BFS without a target from vertex 0, DFS from vertex 0, connected
components, and cycle detection, each timed as described above. The timed call includes the
algorithm's own initialization (result record, visited/parent dictionaries, queue or stack);
building the graph is excluded. Checks run after timing: (1) BFS distances pass an optimality
certificate (source 0, no road joins levels more than one apart, every vertex has a neighbour one
level closer); (2) they equal the distances of Dijkstra with unit edge cost; (3) the BFS path to
the farthest vertex is a real path of that many edges; (4) DFS visits exactly the source's block;
(5) the component count and member lists equal the construction; (6) `find_cycle` reports a cycle
exactly when extra roads were added and the reported walk is closed and uses existing roads.
All checks passed for every graph.

**Metrics.** Runtime (ms; mean, median, standard deviation over {cfg.runs} runs), visited vertices,
examined edges (adjacency entries read).

**Results.** Raw runs: `exp1_raw.csv`; aggregates: `exp1_summary.csv`; chart: `exp1_runtime.png`.

{X.md_table(table, ["family", "V", "E", "algorithm", "visited", "edges_examined", "mean_ms", "median_ms", "stdev_ms", "ns_per_V_plus_E"])}

Cycle detection (stops at the first cycle, so it only scans everything on the forest):

{X.md_table(cyc, ["family", "V", "E", "visited", "edges_examined", "median_ms"])}

**Interpretation.** On a connected two-way graph BFS and DFS each visited V vertices and examined
exactly 2E adjacency entries (each road is seen from both ends), which is the V + E work the
bound counts. Measured growth:

{span("sparse", "bfs")}
{span("sparse", "dfs")}
{span("dense", "bfs")}
{span("dense", "dfs")}

The counters are exactly linear in V + E. Runtime grew by the factors listed above, in every
series faster than V + E itself (about 2 to 2.5 times as fast), so the cost of one operation rose with graph size. The
operation counts cannot explain that; a likely cause, not isolated by this experiment, is memory
locality (the dictionaries and edge objects of a large graph no longer fit in the CPU caches).
The per-unit cost also differs between sparse and dense graphs because a vertex visit and an
edge examination do not cost the same. In the forest family BFS and DFS from vertex 0 only reach
one of the 8 trees (V/8 vertices), so their per-unit figure there is not comparable; the
component search covers the whole forest. On cyclic graphs `find_cycle` returned after examining
a few edges, so its runtime there says nothing about growth; on the forest it scanned everything.

**Limitations.** Pure Python: constant factors are dominated by the interpreter and by
`TrackGraph.neighbors`, which re-derives the blocked state of every edge. Random graphs only; one
graph per (family, V). Large dictionaries also bring cache effects that the model ignores.
Timings of the smallest graphs are short and therefore relatively noisy.

**Conclusion.** Both traversals did work proportional to V + E on every input (exactly, by the
counters). Measured runtime grew somewhat faster than V + E (the per-unit cost roughly doubled over a
20-fold size range; a cache effect is a possible but untested explanation), which is consistent with
a linear operation count but is not by itself a measurement of O(V + E). BFS
returned minimum edge counts on every graph, and DFS component and cycle results matched the
known construction.
"""


if __name__ == "__main__":
    X.main(run, __doc__)

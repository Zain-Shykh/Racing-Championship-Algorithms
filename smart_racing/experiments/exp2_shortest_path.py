"""Experiment 2: Dijkstra and A* (Project.md section 7).

Run alone: `.venv/bin/python -m smart_racing.experiments.exp2_shortest_path [--quick]`
"""
from __future__ import annotations

import math
import random

from smart_racing import config
from smart_racing.algorithms.astar import astar
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.core.cost import distance_cost, make_cost_fn, time_cost
from smart_racing.experiments import common as X
from smart_racing.tracks.generator import generate
from smart_racing.tracks.loader import load_builtin

SIDES = [20, 40, 60, 90, 120]          # lattice side: V = side * side
QUICK_SIDES = [8, 12]
ALGORITHMS = {"dijkstra": dijkstra, "astar": astar}


def synthetic(side: int, seed: int) -> list[tuple]:
    """(family, graph, cost name, cost function, source, target) for one lattice size."""
    last = side * side - 1
    mid = side // 2
    cases = []
    g = X.grid_graph(side, side, seed)
    cases.append(("open_far", g, "distance", distance_cost, 0, last))
    cases.append(("open_near", g, "distance", distance_cost, mid * side + mid, mid * side + mid + side // 4))
    cases.append(("open_time", g, "time", time_cost, 0, last))
    w = X.grid_graph(side, side, seed, wall=True)
    cases.append(("wall", w, "distance", distance_cost, mid * side + mid - 1, mid * side + mid))
    for family, factor in (("weak_ratio", 0.001), ("zero_ratio", 0.0)):
        m = X.grid_graph(side, side, seed)          # same lattice as open_time, one road changed
        motorway = max(edge.id for edge, _ in m.incident(side - 1))    # a road at the top-right corner
        m.edge(motorway).base_time *= factor
        cases.append((family, m, "time", time_cost, 0, last))
    return cases


def circuits(cfg: X.Config) -> list[tuple]:
    """(name, graph) of the three built-in circuits and one generated track."""
    out = [(name, load_builtin(name).graph) for name in config.BUILTIN_CIRCUITS]
    for seed in range(cfg.seed, cfg.seed + 50):
        circuit, _ = generate(seed)
        if circuit is not None:
            out.append((f"generated_seed_{seed}", circuit.graph))
            break
    return out


def counters(results) -> dict:
    """Counters of one query or, for a lap plan, summed over its legs."""
    rs = results if isinstance(results, list) else [results]
    return {"expanded": sum(r.expanded for r in rs), "relaxed": sum(r.relaxed for r in rs),
            "edges_examined": sum(r.edges_examined for r in rs),
            "heap_ops": sum(r.heap_ops for r in rs),
            "heap_comparisons": sum(r.heap_comparisons for r in rs),
            "path_cost": sum(r.cost for r in rs), "path_edges": sum(len(r.edge_path) for r in rs),
            "heuristic_ratio": rs[0].heuristic_ratio if rs[0].heuristic_ratio is not None else ""}


def check(g, cost_fn, legs, by_alg: dict) -> None:
    """Equal optimal cost, and each returned path really has that cost."""
    for i, (source, target) in enumerate(legs):
        d, a = by_alg["dijkstra"][i], by_alg["astar"][i]
        assert d.found and a.found
        assert math.isclose(d.cost, a.cost, rel_tol=1e-9, abs_tol=1e-9), (d.cost, a.cost)
        for r in (d, a):
            assert r.path[0] == source and r.path[-1] == target
            assert math.isclose(sum(cost_fn(g.edge(e)) for e in r.edge_path), r.cost,
                                rel_tol=1e-9, abs_tol=1e-9)


def relation(astar_expanded: int, dijkstra_expanded: int) -> str:
    if astar_expanded == dijkstra_expanded:
        return "equal"
    return "fewer" if astar_expanded < dijkstra_expanded else "more"


def random_sweep(cfg: X.Config) -> list[dict]:
    """Untimed: many small random graphs and random queries, to count how often
    A* expands fewer, equal or more vertices than Dijkstra."""
    rng = random.Random(cfg.seed)
    rows = []
    for i in range(20 if cfg.quick else 400):
        n = rng.randint(30, 200)
        g = X.random_graph(n, int(n * rng.choice([0.2, 1.0, 3.0])), cfg.seed * 1000 + i)
        source, target = rng.sample(range(n), 2)
        cost_name = rng.choice(["distance", "Balanced"])
        cost_fn = distance_cost if cost_name == "distance" else make_cost_fn(cost_name)
        d, a = dijkstra(g, source, target, cost_fn), astar(g, source, target, cost_fn)
        check(g, cost_fn, [(source, target)], {"dijkstra": [d], "astar": [a]})
        rows.append({"instance": i, "V": n, "E": g.num_edges, "cost_model": cost_name,
                     "source": source, "target": target, "path_cost": d.cost,
                     "dijkstra_expanded": d.expanded, "astar_expanded": a.expanded,
                     "relation": relation(a.expanded, d.expanded)})
    return rows


def run(cfg: X.Config) -> str:
    raw: list[dict] = []

    def measure(family, g, cost_name, cost_fn, legs, query):
        fields = {"family": family, "V": g.num_vertices, "E": g.num_edges,
                  "cost_model": cost_name, "query": query}
        by_alg = {}
        for name, alg in ALGORITHMS.items():          # same graph object and legs for both
            by_alg[name] = X.record(
                raw, cfg, {**fields, "algorithm": name},
                lambda alg=alg: [alg(g, s, t, cost_fn) for s, t in legs], counters)
        check(g, cost_fn, legs, by_alg)

    sides = QUICK_SIDES if cfg.quick else SIDES
    for side in sides:
        for family, g, cost_name, cost_fn, source, target in synthetic(side, cfg.seed + side):
            measure(family, g, cost_name, cost_fn, [(source, target)], f"{source}->{target}")
    tracks = circuits(cfg)
    for name, g in tracks:
        stops = [g.start.id] + [v.id for v in g.checkpoints()] + [g.finish.id]
        legs = list(zip(stops, stops[1:]))
        for cost_name in ("distance", *config.COST_PRESETS):
            cost_fn = distance_cost if cost_name == "distance" else make_cost_fn(cost_name)
            measure(name, g, cost_name, cost_fn, legs, f"lap plan, {len(legs)} legs")

    summary = X.save_tables(cfg, "exp2", raw)
    comparison = []
    for d in X.pick(summary, algorithm="dijkstra"):
        a = X.pick(summary, algorithm="astar", family=d["family"], V=d["V"], cost_model=d["cost_model"])[0]
        comparison.append({
            "family": d["family"], "V": d["V"], "E": d["E"], "cost_model": d["cost_model"],
            "query": d["query"], "path_cost": d["path_cost"], "heuristic_ratio": a["heuristic_ratio"],
            "dijkstra_expanded": d["expanded"], "astar_expanded": a["expanded"],
            "expanded_pct": 100.0 * a["expanded"] / d["expanded"],
            "relation": relation(a["expanded"], d["expanded"]),
            "dijkstra_relaxed": d["relaxed"], "astar_relaxed": a["relaxed"],
            "dijkstra_heap_ops": d["heap_ops"], "astar_heap_ops": a["heap_ops"],
            "dijkstra_median_ms": d["median_ms"], "astar_median_ms": a["median_ms"],
            "time_pct": 100.0 * a["median_ms"] / d["median_ms"]})
    X.write_csv(cfg.out / "exp2_comparison.csv", comparison)
    sweep = random_sweep(cfg)
    X.write_csv(cfg.out / "exp2_random_sweep.csv", sweep)

    families = ["open_far", "open_near", "open_time", "wall", "weak_ratio", "zero_ratio"]
    fig, (left, right) = X.new_axes("Experiment 2: A* relative to Dijkstra on lattice graphs",
                                    "V (vertices)", "A* expanded vertices, % of Dijkstra", ncols=2)
    for i, family in enumerate(families):
        rows = X.pick(comparison, family=family)
        X.series(left, [r["V"] for r in rows], [r["expanded_pct"] for r in rows], i, family)
        X.series(right, [r["V"] for r in rows], [r["time_pct"] for r in rows], i, family)
    for ax in (left, right):
        ax.axhline(100, color="#6b6a63", linewidth=1, linestyle="--")
        ax.set_xscale("log")
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8)
    left.set_title("Expanded vertices (100% = same as Dijkstra)", fontsize=10)
    right.set_title("Median runtime (100% = same as Dijkstra)", fontsize=10)
    right.set_ylabel("A* median runtime, % of Dijkstra")
    X.save_fig(fig, cfg, "exp2_astar_vs_dijkstra.png")

    fig, ax = X.new_axes("Experiment 2: runtime against the (V + E) log2 V term",
                         "(V + E) x log2(V)", "median runtime (ms)")
    index = 0
    for family in ("open_far", "zero_ratio"):
        for name in ALGORITHMS:
            rows = X.pick(summary, family=family, algorithm=name)
            X.series(ax, [(r["V"] + r["E"]) * math.log2(r["V"]) for r in rows],
                     [r["median_ms"] for r in rows], index, f"{name} on {family}")
            index += 1
    ax.legend()
    X.save_fig(fig, cfg, "exp2_runtime_growth.png")

    top = sides[-1] ** 2
    largest = [r for r in comparison if r["family"] in families and r["V"] == top]
    track_rows = [r for r in comparison if r["family"] not in families]
    count = {k: sum(1 for r in comparison if r["relation"] == k) for k in ("fewer", "equal", "more")}
    swept = {k: sum(1 for r in sweep if r["relation"] == k) for k in ("fewer", "equal", "more")}
    slower = sum(1 for r in comparison if r["relation"] == "fewer" and r["time_pct"] > 100)
    lines = "\n".join(
        f"- {r['family']} ({r['cost_model']} cost, r = {r['heuristic_ratio']:.3g}): A* expanded "
        f"{r['astar_expanded']:,} against {r['dijkstra_expanded']:,} ({r['expanded_pct']:.1f}%), "
        f"median time {r['astar_median_ms']:.2f} ms against {r['dijkstra_median_ms']:.2f} ms "
        f"({r['time_pct']:.0f}%)." for r in largest)
    grow = []
    for name in ALGORITHMS:
        rows = X.pick(summary, family="open_far", algorithm=name)
        term = [(r["V"] + r["E"]) * math.log2(r["V"]) for r in rows]
        grow.append(f"{name}: the term grew {term[-1] / term[0]:.0f}x and the median time "
                    f"{rows[-1]['median_ms'] / rows[0]['median_ms']:.0f}x "
                    f"({rows[0]['median_ms']:.2f} ms to {rows[-1]['median_ms']:.1f} ms)")
    if count["more"] + swept["more"] == 0:
        more = ("A* never expanded more vertices than Dijkstra, neither in the timed configurations "
                "nor in the random sweep. That is what the theory predicts for this implementation: "
                "the heuristic is consistent, so A* only expands vertices with g + h <= C*, and "
                "Dijkstra expands every vertex with g < C*. We could not construct an honest input "
                "with more expansions and do not claim one.")
    else:
        more = (f"A* expanded more vertices than Dijkstra in {count['more']} timed configurations and "
                f"{swept['more']} sweep instances (see `exp2_comparison.csv`, `exp2_random_sweep.csv`).")
    columns = ["family", "V", "E", "cost_model", "path_cost", "dijkstra_expanded", "astar_expanded",
               "expanded_pct", "relation", "dijkstra_relaxed", "astar_relaxed", "dijkstra_heap_ops",
               "astar_heap_ops", "dijkstra_median_ms", "astar_median_ms"]
    return f"""## Experiment 2: Dijkstra and A*

**Objective.** Compare the gameplay `dijkstra` and `astar` (`algorithms/dijkstra.py`,
`algorithms/astar.py`) on runtime, expanded vertices, relaxed edges, heap operations and path
cost, check that both return the same optimal cost, and find where A* expands fewer, the same
number of, or more vertices.

**Environment.** {X.env_line(cfg)}

**Input generation.** Lattices from `common.grid_graph(side, side, seed={cfg.seed} + side)`: vertex
r x side + c at (100 c, 100 r) moved by up to 30 in x and y; two-way roads between 4-neighbours;
distance = straight line x U(1.0, 1.2), so never below the straight line; difficulty 1..3;
time = distance / (40, 36 or 32 by difficulty); fuel = 0.05 x distance. Families:
`open_far` corner to opposite corner, distance cost; `open_near` centre to a vertex side/4
columns away, distance cost; `open_time` corner to corner, travel-time cost; `wall` the same
lattice with no road across the middle column except in row 0, source and target facing each
other across the wall, distance cost; `weak_ratio` = `open_time` with one top-right corner road
made 1000 times faster, which drags the heuristic ratio r down; `zero_ratio` = the same with that
road at zero time, so r = 0 and h = 0. Real tracks: the three built-in circuits and
`{tracks[-1][0]}` from `tracks.generator.generate`, each planned as a full lap (Start, checkpoints
in order, Finish, one query per leg, counters summed over legs) under distance cost and the four
presets. Random sweep (untimed): {len(sweep)} `common.random_graph` instances with 30 to 200
vertices and a random source and target.

**Dataset sizes.** Lattices with V in {[s * s for s in sides]} (E up to {max(r['E'] for r in comparison):,});
circuits with {min(g.num_vertices for _, g in tracks)} to {max(g.num_vertices for _, g in tracks)} vertices.

**Procedure.** Both algorithms run on the same graph object, cost function and query. The timed
call is the complete search call, including its own heap and dictionaries; for A* it also
includes computing the ratio r over all edges (O(E)), because the gameplay function does that on
every query. Graph construction is excluded. After timing: both must find a path, the two costs
must agree (relative tolerance 1e-9), and the cost summed along each returned path must equal the
reported cost. All checks passed in every configuration and every sweep instance.

**Metrics.** Runtime (ms), expanded vertices, relaxed edges (successful relaxations), examined
edges, heap operations (pushes + pops), heap comparisons, final path cost.

**Results.** Raw runs: `exp2_raw.csv`; aggregates: `exp2_summary.csv`; side by side:
`exp2_comparison.csv`; sweep: `exp2_random_sweep.csv`; charts: `exp2_astar_vs_dijkstra.png`,
`exp2_runtime_growth.png`. Lattices at the largest size (V = {top:,}):

{X.md_table(largest, columns)}

Lap plans on real tracks:

{X.md_table(track_rows, columns)}

**Interpretation.** Path costs were equal in all {len(comparison)} timed configurations. Over those,
A* expanded fewer vertices in {count['fewer']}, exactly as many in {count['equal']} and more in
{count['more']}; in the random sweep the split was {swept['fewer']} fewer, {swept['equal']} equal,
{swept['more']} more. At V = {top:,}:

{lines}

So the saving depends on how informative h is. It was largest when the target is near and
nothing blocks the straight line (`open_near`). In `wall` the target is also only one column away
in a straight line, but the route has to go round the wall and A* still expanded the share shown
above: the heuristic pulls the search towards the wall first. When one cheap road lowers r
(`weak_ratio`) the heuristic is almost zero everywhere and the saving of `open_time` on the same
lattice disappears. With r = 0 (`zero_ratio`) A* is Dijkstra with extra bookkeeping: identical
expansions and no time saved. {more}
On the real tracks A* expanded {min(r['expanded_pct'] for r in track_rows):.0f}% to {max(r['expanded_pct'] for r in track_rows):.0f}% of Dijkstra's vertices over a
lap plan but took {min(r['time_pct'] for r in track_rows):.0f}% to {max(r['time_pct'] for r in track_rows):.0f}% of its median time: on graphs of 25 to 31 vertices
the fixed per-query work of A* (the scan over all edges for r, which also evaluates the cost
function on every edge, and a square root per step) was larger than the expansions it saved. This
is a likely explanation, not isolated by a separate measurement.
Fewer expansions rarely meant less time: in {slower} of the {count['fewer']} configurations
where A* expanded fewer vertices its median time was still higher, probably because each A* step also
evaluates a square root and every query scans all edges for r. Growth on `open_far`:
{grow[0]}; {grow[1]}. This is in line with O((V + E) log V) but, being a
few sizes on one machine, it does not prove the bound.

**Limitations.** Lattice-like synthetic graphs with bounded degree; one graph and one query per
(family, size). The built-in circuits have about 30 vertices, so one lap plan takes well under a few
milliseconds and its timings are noisy; their counters are exact. Heap operations count pushes and
pops of the lazy-deletion heap, not decrease-key operations. Pure Python constant factors.

**Conclusion.** Dijkstra and A* always agreed on the optimal cost. A* with the straight-line
heuristic of SPEC 4.4 expanded between {min(r['expanded_pct'] for r in comparison):.1f}% and
{max(r['expanded_pct'] for r in comparison):.1f}% of Dijkstra's vertices in the timed configurations: a
large saving for near, unobstructed targets, little or none when the heuristic is weak, and no
case with more expansions was {"observed" if count["more"] + swept["more"] == 0 else "ruled out (see above)"}.
"""


if __name__ == "__main__":
    X.main(run, __doc__)

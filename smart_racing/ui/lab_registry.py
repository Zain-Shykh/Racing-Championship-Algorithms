"""Algorithm Lab registry: the one place that maps a Lab name to the gameplay function.

No pygame here. `ALGOS[name].fn` IS the function gameplay imports (a test checks `is`), `run` calls it,
`record` collects its `observer` steps, and the Lab only replays those steps. For the event heap (which has
no observer) the same `EventQueue` calls the engine makes are driven here and recorded step by step.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from smart_racing import config
from smart_racing.algorithms.astar import astar
from smart_racing.algorithms.backtracking import solve
from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import dfs
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.algorithms.knapsack import Item, knapsack_dp, knapsack_greedy
from smart_racing.algorithms.mst import kruskal
from smart_racing.algorithms.sorting import heap_sort, merge_sort, quick_sort
from smart_racing.core.cost import make_cost_fn
from smart_racing.core.models import ChampionshipEntry
from smart_racing.engine.events import EventQueue


@dataclass
class Algo:
    name: str
    family: str            # graph | knapsack | backtrack | kruskal | heap | sort
    fn: Callable           # the gameplay function (EventQueue for the heap)
    explain: str
    complexity: str
    role: str


@dataclass
class Recording:
    name: str
    steps: list[dict]
    counters: dict         # final counters, taken from the result object of the same call
    result: object
    data: dict


ALGOS: dict[str, Algo] = {a.name: a for a in [
    Algo("BFS", "graph", bfs,
         "Explores the graph in rings of equal road count using a FIFO queue. The first time it reaches a vertex is "
         "by the fewest roads.",
         "Time O(V + E), space O(V).",
         "Reachability and minimum-road routes: the validator's checkpoint-order checks and the Explorer's Reach tab."),
    Algo("DFS", "graph", dfs,
         "Follows one road as deep as possible, then backtracks, using an explicit stack. Cycles, components, dead "
         "ends and alternative routes are built on it.",
         "Time O(V + E), space O(V).",
         "Cycle, dead-end and component checks in the validator and generator; the Explorer's alternative routes."),
    Algo("Dijkstra", "graph", dijkstra,
         "Settles vertices in order of cheapest known cost using a min-heap. Costs must be non-negative.",
         "Time O((V + E) log V), space O(V + E).",
         "Opponent 3's distance route, nearest fuel station (fuel cost), pickup detour costs."),
    Algo("A*", "graph", astar,
         "Dijkstra guided by h(u) = straight-line distance x the cheapest cost per unit length, so it expands fewer "
         "vertices and still finds the optimum.",
         "Worst case as Dijkstra, usually far fewer expansions.",
         "The player's recommended route at race start and at every re-plan after an event."),
    Algo("Knapsack DP", "knapsack", knapsack_dp,
         "dp[i][b] = best benefit using the first i items within budget b. Each cell is the better of skipping item "
         "i or taking it. The traceback walks back from dp[m][B].",
         "Time O(m B), space O(m B). Pseudo-polynomial in B.",
         "Chooses which nitro pickups and stations are worth a detour (the autopilot's resource plan)."),
    Algo("Greedy", "knapsack", knapsack_greedy,
         "Sorts items by benefit/cost and takes each one that still fits. Fast, feasible, not always optimal: try "
         "the Greedy trap presets.",
         "Time O(m log m) with merge sort.",
         "The comparison heuristic beside the DP in the resource panel; selectable for the autopilot."),
    Algo("Backtracking", "backtrack", solve,
         "Assigns variables one at a time, rejects values that break a constraint, and undoes the last choice "
         "(backtracks) when a branch cannot be completed. Forward checking prunes dead branches early.",
         "Worst case O(d^n); pruning reduces the explored part.",
         "The track generator places the main loop, checkpoints, stations, shortcuts and obstacles with it. "
         "Here: spacing fuel stations along this circuit."),
    Algo("Kruskal", "kruskal", kruskal,
         "Sorts roads by length (merge sort) and accepts a road when it joins two different components, tested "
         "with union-find. Rejected roads would close a cycle.",
         "Time O(E log E) + O(E alpha(V)).",
         "The generator's road backbone: a spanning tree before extra roads add cycles."),
    Algo("Event heap", "heap", EventQueue,
         "Race events wait in a binary min-heap keyed (time, priority, sequence). Popping applies the event to the "
         "graph; temporary effects schedule their own expiry; cancelling is lazy (flagged, skipped when popped).",
         "Schedule and pop O(log n), cancel O(1).",
         "Every scripted race event (blockage, oil, speed limit, station outage, nitro spawn) runs through it."),
    Algo("Merge sort", "sort", merge_sort,
         "Bottom-up: merge sorted runs of width 1, 2, 4, ... Stable, with the same cost on every input.",
         "Time O(n log n) always, space O(n).",
         "Default championship ranking and every race classification."),
    Algo("Quick sort", "sort", quick_sort,
         "Median-of-three pivot (seeded) and a three-way partition: smaller | equal | larger, then the smaller "
         "side first.",
         "O(n log n) expected, O(n^2) worst case, O(log n) stack.",
         "Alternative championship ranking on the Dashboard."),
    Algo("Heap sort", "sort", heap_sort,
         "Builds a heap with the worst-ranked entry at the root, then swaps the root to the end and sifts down.",
         "Time O(n log n) always, in place.",
         "Third championship ranking on the Dashboard."),
]}
REGISTRY: dict[str, Callable] = {name: a.fn for name, a in ALGOS.items()}
SORTS = ("Merge sort", "Quick sort", "Heap sort")


# --- data builders ----------------------------------------------------------------------------
def sample_entries(n: int, seed: int = 7) -> list[ChampionshipEntry]:
    """n made-up championship records with plenty of tied points, so the tie-breaks matter."""
    rng = random.Random(seed)
    return [ChampionshipEntry(i, rng.randrange(0, 12) * 5, rng.randint(0, 3), rng.randint(4, 12),
                              round(rng.uniform(70, 95), 1)) for i in range(n)]


def items_from(rows) -> list[Item]:
    return [Item(i, c, v, chr(65 + i % 26)) for i, (c, v) in enumerate(rows)]


KNAPSACK_PRESETS = {
    "Brief A/B/C (B=10)": ([(6, 30), (5, 24), (5, 24)], 10),
    "Greedy trap 1 (B=10)": ([(1, 2), (10, 15)], 10),
    "Greedy trap 2 (B=9)": ([(5, 6), (4, 4), (4, 4), (1, 1)], 8),
    "Random 6 items (B=20)": ([(c, v) for c, v in zip(random.Random(4).sample(range(2, 12), 6),
                                                      random.Random(5).sample(range(5, 40), 6))], 20),
}


STATION_DEFAULTS = {"harbor_eight": (5, 4), "grand_ring": (3, 7), "serpent_pass": (5, 5)}   # (stations, min gap)


def station_problem(circuit, k: int, gap: int) -> dict:
    """Spacing example for backtracking: k fuel stations on non-mandatory vertices of the main route, at
    least `gap` positions apart (cyclically). Each station tries the positions nearest its ideal slot first,
    as the generator's placement does."""
    route, g = circuit.main_route, circuit.graph
    n = len(route)
    spots = [i for i in range(1, n - 1) if not g.vertex(route[i]).is_mandatory]
    variables = list(range(1, k + 1))
    domains = {v: sorted(spots, key=lambda p: (abs(p - v * n / (k + 1)), p)) for v in variables}

    def consistent(assignment, var, value):
        return all(min(abs(value - p), n - abs(value - p)) >= gap for p in assignment.values())

    def prune(assignment, remaining):                    # forward check: enough free positions left?
        return len(spots) - len(assignment) < len(remaining)

    return dict(variables=variables, domains=domains, consistent=consistent, prune=prune, route=route)


# --- running ------------------------------------------------------------------------------------
def run(name: str, data: dict, observer=None) -> tuple[object, dict]:
    """Call the gameplay function `ALGOS[name].fn` and return (result, final counters)."""
    algo = ALGOS[name]
    fn = algo.fn
    if algo.family == "graph":
        g, src, dst = data["graph"], data["src"], data["dst"]
        if name == "BFS":
            res = fn(g, src, dst, observer=observer)
            return res, {"visited": res.visited, "edges_examined": res.edges_examined}
        if name == "DFS":
            res = fn(g, src, observer=observer)
            return res, {"visited": res.visited, "edges_examined": res.edges_examined}
        res = fn(g, src, dst, make_cost_fn(data["preset"]), observer=observer)
        return res, {"expanded": res.expanded, "relaxed": res.relaxed, "edges_examined": res.edges_examined,
                     "heap_ops": res.heap_ops, "heap_comparisons": res.heap_comparisons}
    if algo.family == "knapsack":
        res = fn(data["items"], data["budget"], observer=observer)
        return res, {"states": res.states, "total_cost": res.total_cost, "total_benefit": res.total_benefit}
    if algo.family == "backtrack":
        p = station_problem(data["circuit"], data["k"], data["gap"])
        res = fn(p["variables"], p["domains"], p["consistent"], p["prune"], observer=observer)
        return res, {"nodes": res.nodes, "prunes": res.prunes, "backtracks": res.backtracks}
    if algo.family == "kruskal":
        g = data["graph"]
        res = fn(g.vertex_ids(), [(e.id, e.src, e.dst, e.distance) for e in g.edges()], observer=observer)
        return res, {"edges_examined": res.edges_examined, "comparisons": res.comparisons,
                     "finds": res.finds, "unions": res.unions}
    if algo.family == "sort":
        res = fn(data["entries"], observer=observer)
        return res, {"comparisons": res.comparisons}
    return _run_event_heap(fn, data["circuit"], observer)


def record(name: str, data: dict) -> Recording:
    steps: list[dict] = []
    result, counters = run(name, data, steps.append)
    return Recording(name, steps, counters, result, data)


# --- event heap: the engine's EventQueue driven the way the race drives it ----------------------
def _snapshot(g) -> tuple:
    return ({e.id: dict(e.effects) for e in g.edges()}, {v.id: v.active for v in g.vertices()})


def restore_snapshot(g, snap) -> None:
    for e in g.edges():
        e.effects = dict(snap[0][e.id])
    for v in g.vertices():
        v.active = snap[1][v.id]


def _run_event_heap(queue_cls, circuit, observer) -> tuple[object, dict]:
    g = circuit.graph
    q = queue_cls(g)
    stats = {"applied": 0, "rejected": 0, "cancelled": 0, "skipped": 0}
    scheduled, logged = [], set()

    def emit(kind: str, text: str, event=None) -> None:
        if observer:
            observer({"type": kind, "text": text, "event": event, "snapshot": _snapshot(g),
                      "pending": [(e.event_id, e.type, e.trigger_time, e.priority, e.target) for e in q.pending()],
                      "heap": dict(pushes=q.heap.pushes, pops=q.heap.pops, comparisons=q.heap.comparisons,
                                   swaps=q.heap.swaps), "stats": dict(stats)})

    for e in circuit.events:
        ev = q.schedule(e["type"], e["time"], e["target"], e.get("duration"))
        scheduled.append(ev)
        emit("schedule", f"schedule #{ev.event_id} {ev.type} on {ev.target} at t={ev.trigger_time:g}s "
                         f"(priority {ev.priority})", ev)
    victim = scheduled[-2]                                   # cancel a late event to show lazy deletion
    q.cancel(victim.event_id)
    stats["cancelled"] += 1
    emit("cancel", f"cancel #{victim.event_id} {victim.type}: flagged, it stays in the heap until popped", victim)

    def skips(now: float, strict: bool = False) -> None:
        for ev in scheduled:
            if ev.cancelled and ev.event_id not in logged and (ev.trigger_time < now if strict else ev.trigger_time <= now):
                logged.add(ev.event_id)
                stats["skipped"] += 1
                emit("skip", f"pop #{ev.event_id} {ev.type}: cancelled, discarded without effect", ev)

    while (t := q.next_time()) is not None:
        skips(t, True)
        for rec in q.pop_due(t):
            ev = rec.event
            stats["applied"] += 1
            emit("expire" if ev.type == config.EVENT_EXPIRE else "pop",
                 f"t={ev.trigger_time:g}s pop #{ev.event_id} {ev.type}: {rec.description}", ev)
        while len(q.rejected) > stats["rejected"]:
            rej = q.rejected[stats["rejected"]]
            stats["rejected"] += 1
            emit("reject", f"t={rej.event.trigger_time:g}s pop #{rej.event.event_id}: rejected, {rej.description}",
                 rej.event)
        skips(t)
    skips(float("inf"))
    emit("done", f"queue empty: {stats['applied']} applied, {stats['rejected']} rejected, "
                 f"{stats['skipped']} cancelled skipped")
    h = q.heap
    return q, {"pushes": h.pushes, "pops": h.pops, "comparisons": h.comparisons, "swaps": h.swaps,
               "applied": stats["applied"], "rejected": stats["rejected"], "cancelled": stats["cancelled"]}


# --- replay: counters and state folded from the recorded steps -------------------------------------
def live_counters(name: str, steps: list[dict], n: int) -> dict:
    """Counters that can be rebuilt from the first `n` steps (the rest appear when the run is complete)."""
    s = steps[:n]
    count = lambda kind, **kw: sum(1 for x in s if x["type"] == kind and all(x.get(k) == v for k, v in kw.items()))  # noqa: E731
    family = ALGOS[name].family
    if family == "graph":
        if name in ("BFS", "DFS"):
            return {"visited": count("visit"), "edges_examined": count("examine")}
        return {"expanded": count("expand"), "relaxed": count("relax", improved=True)}
    if family == "knapsack":
        return {"states": count("cell") + count("consider")}
    if family == "backtrack":
        return {"nodes": count("assign") + count("reject"), "prunes": count("reject") + count("prune"),
                "backtracks": count("backtrack")}
    if family == "kruskal":
        return {"edges_examined": count("edge")}
    if family == "sort":
        return {"comparisons": count("compare")}
    last = s[-1] if s else None
    return dict(last["heap"], **{k: v for k, v in last["stats"].items() if k != "skipped"}) if last else {}


def graph_state(name: str, steps: list[dict], n: int) -> dict:
    """What a graph search has seen after `n` steps: visited, frontier (vertex -> label), current vertex,
    tree edges, the road under examination and, once finished, the final path."""
    visited, frontier, tree, parent, stack = set(), {}, [], {}, []
    current = examined = None
    path: list[int] = []
    for st in steps[:n]:
        kind = st["type"]
        if kind in ("visit", "expand"):
            current = st["vertex"]
            visited.add(current)
            frontier.pop(current, None)
            if name == "DFS":
                stack.append(current)
                if st["edge"] is not None:
                    tree.append(st["edge"])
                frontier = {v: "" for v in stack}
        elif kind in ("examine", "relax"):
            examined = st["edge"]
            if st.get("discovered") and name == "BFS":
                frontier[st["to"]] = f"{st['depth']}"
                tree.append(st["edge"])
            elif st.get("improved"):
                frontier[st["to"]] = f"{st['dist']:.1f}"
                parent[st["to"]] = st["edge"]
        elif kind == "backtrack":
            if stack:
                stack.pop()
            current = stack[-1] if stack else None
            frontier = {v: "" for v in stack}
        elif kind == "done":
            path = st["edge_path"]
            examined = None
    if name in ("Dijkstra", "A*"):
        tree = list(parent.values())
    return dict(visited=visited, frontier=frontier, current=current, tree=tree, examined=examined, path=path)


def describe(name: str, st: dict) -> str:
    """One readable line for a recorded step."""
    k = st["type"]
    if "text" in st:
        return st["text"]
    if k == "visit":
        return f"visit v{st['vertex']}" + (f" at depth {st['depth']}" if "depth" in st else "") + \
            (f", queue holds {len(st['frontier'])}" if "frontier" in st else "")
    if k == "examine":
        return f"road {st['edge']}: v{st['from']} -> v{st['to']}, " + ("new vertex, queued/stacked" if st["discovered"] else "already seen")
    if k == "expand":
        extra = f", h={st['h']:.2f}, f={st['f']:.2f}" if "f" in st else ""
        return f"settle v{st['vertex']} at cost {st['dist']:.2f}{extra}; heap holds {st['frontier']}"
    if k == "relax":
        return f"road {st['edge']}: v{st['from']} -> v{st['to']} cost {st['dist']:.2f}, " + ("improved, pushed" if st["improved"] else "not better")
    if k == "backtrack":
        return f"backtrack: undo {'v' if name == 'DFS' else 'place '}{st.get('vertex', st.get('var'))}" + (
            f" = {st['value']}" if "value" in st else "")
    if k == "done":
        if name in ("BFS", "Dijkstra", "A*"):
            return f"done: path of {len(st['edge_path'])} roads" if st["found"] else "done: target not reachable"
        if name in ("Knapsack DP", "Greedy"):
            return f"done: items {[chr(65 + i % 26) for i in st['selected']]}, cost {st['cost']}, benefit {st['benefit']:g}"
        if name == "Backtracking":
            return f"done: {'solved' if st['solved'] else 'no solution'} after {st['nodes']} candidates"
        if name == "Kruskal":
            return f"done: {len(st['edges'])} roads in the tree, total length {st['weight']:.0f}"
        return f"done: {st.get('comparisons', '')} comparisons"
    if k == "cell":
        return f"cell dp[{st['i']}][{st['b']}] = {st['value']:g} ({'take' if st['take'] else 'skip'} item {chr(65 + st['item'] % 26)})"
    if k == "trace":
        return f"traceback at item {chr(65 + st['item'] % 26)}, budget {st['b']}: " + ("taken" if st["taken"] else "not taken")
    if k == "consider":
        ratio = "free" if st["ratio"] is None else f"ratio {st['ratio']:.2f}"
        return f"item {chr(65 + st['item'] % 26)} (cost {st['cost']}, benefit {st['benefit']:g}, {ratio}): " + (
            f"picked, {st['remaining']} left" if st["picked"] else "does not fit, rejected")
    if k == "assign":
        return f"place station {st['var']} at route position {st['value']} (depth {st['depth']})"
    if k == "reject":
        return f"station {st['var']} at position {st['value']}: breaks a constraint"
    if k == "prune":
        return f"station {st['var']} at {st['value']}: forward check, not enough positions left, cut"
    if k == "edge":
        return f"road {st['edge']} (v{st['u']}-v{st['v']}, length {st['weight']:.0f}): " + (
            "accepted, joins two components" if st["accepted"] else "rejected, would close a cycle") + \
            f"; {st['components']} components"
    if k == "compare":
        a, b = st["a"], st["b"]
        return f"compare racer {a.racer_id} ({a.total_points} pts) with racer {b.racer_id} ({b.total_points} pts): " + \
            ("first ranks ahead" if st["less"] else "not ahead")
    if k == "pass":
        return f"merge pass done: runs of width {st['width']} merged into {2 * st['width']}"
    if k == "partition":
        return f"partition [{st['lo']}..{st['hi']}] around racer {st['pivot'].racer_id}"
    if k == "extract":
        return f"extract root to position {st['position']}: racer {st['item'].racer_id}"
    return k

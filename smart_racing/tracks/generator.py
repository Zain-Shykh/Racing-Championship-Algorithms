"""Automatic track generation (Project.md 5.4 and Challenge 1).

Pipeline, one `Stage` snapshot each so the GUI can show it:
  1 vertices     seeded jittered lattice of intersections
  2 candidates   undirected candidate roads (lattice sides + one diagonal per cell),
                 checked for connectivity before the MST
  3 mst          Kruskal backbone
  4 extras       extra candidate roads -> cycles and alternatives (degree capped)
  5 loop         backtracking: a closed main loop of fixed length through the roads
  6 one_way      one-way roads (Finish -> Start, plus one extra road)
  7 placement    backtracking: shortcuts, fuel stations, checkpoints, nitro
                 pickups and obstacle sites along and around the loop
then the validator; a failed candidate is recorded and the next attempt runs,
up to `config.GEN_MAX_ATTEMPTS`. Pruning rules are documented in docs/RULES.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from smart_racing import config as C
from smart_racing.algorithms.backtracking import BacktrackResult, solve
from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import connected_components
from smart_racing.algorithms.mst import kruskal
from smart_racing.core import graph as G
from smart_racing.tracks.loader import Circuit
from smart_racing.tracks.validator import validate_circuit


@dataclass
class Stage:
    name: str
    description: str
    graph: G.TrackGraph
    info: dict = field(default_factory=dict)


@dataclass
class Rejection:
    attempt: int
    stage: str                 # pipeline stage that refused the candidate
    reasons: list[str]         # the validator's failures, or why the solver gave up


@dataclass
class GenerationReport:
    seed: int
    success: bool = False
    attempts: int = 0
    stages: list[Stage] = field(default_factory=list)        # of the accepted (or last) attempt
    solver: dict[str, BacktrackResult] = field(default_factory=dict)   # "loop" and "placement" counters
    rejected: list[Rejection] = field(default_factory=list)


def generate(seed: int, max_attempts: int = C.GEN_MAX_ATTEMPTS) -> tuple[Circuit | None, GenerationReport]:
    """Generate a validated circuit. Deterministic for a given seed. Returns
    `(None, report)` if every attempt was rejected."""
    report = GenerationReport(seed)
    for attempt in range(1, max_attempts + 1):
        report.attempts = attempt
        rng = random.Random(seed * 1000 + attempt)
        report.stages, report.solver = [], {}
        circuit, stage, reasons = _attempt(rng, f"Generated #{seed}", report.stages, report.solver)
        if circuit is not None:
            report.success = True
            return circuit, report
        report.rejected.append(Rejection(attempt, stage, reasons))
    return None, report


def _snapshot(points, roads, edge_ids, rate, one_way=None, shortcuts=(), roles=None) -> G.TrackGraph:
    """TrackGraph of the chosen roads. roles: vertex id -> (type, checkpoint order, active)."""
    graph = G.TrackGraph()
    for vid, (x, y) in points.items():
        graph.add_vertex(vid, x, y, *(roles or {}).get(vid, (G.INTERSECTION,)))
    for eid in sorted(edge_ids):
        u, v, distance, difficulty = roads[eid]
        if one_way and eid in one_way:
            u, v = one_way[eid]
        speed, thirst = C.GEN_SPEED[difficulty], 1.0
        if eid in shortcuts:
            difficulty, speed, thirst = C.GEN_SHORTCUT_DIFFICULTY, C.GEN_SHORTCUT_SPEED, C.GEN_SHORTCUT_THIRST
        graph.add_edge(eid, u, v, distance, round(distance / speed, 2), round(distance * rate * thirst, 2),
                       difficulty, eid in shortcuts, bool(one_way and eid in one_way))
    return graph


def _bypass(graph: G.TrackGraph, edge_id: int, a: int, b: int) -> list[int]:
    """Fewest-roads way from a to b with one road closed, [] if there is none."""
    graph.block_edge(edge_id)
    path = bfs(graph, a, b).path
    graph.unblock_edge(edge_id)
    return path


def _attempt(rng: random.Random, name: str, stages: list[Stage],
             solver: dict) -> tuple[Circuit | None, str, list[str]]:
    cols, rows = C.GEN_COLS, C.GEN_ROWS
    width, height = C.GEN_MAP_SIZE
    rate = rng.uniform(*C.GEN_FUEL_RATE)

    # 1. vertices
    cw, ch = (width - 2 * C.GEN_MARGIN) / (cols - 1), (height - 2 * C.GEN_MARGIN) / (rows - 1)
    points = {r * cols + c: (round(C.GEN_MARGIN + (c + rng.uniform(-1, 1) * C.GEN_JITTER) * cw, 1),
                             round(C.GEN_MARGIN + (r + rng.uniform(-1, 1) * C.GEN_JITTER) * ch, 1))
              for r in range(rows) for c in range(cols)}
    stages.append(Stage("vertices", f"{len(points)} intersections on a jittered {cols}x{rows} lattice",
                        _snapshot(points, {}, [], rate)))

    # 2. candidate roads: eid -> (u, v, distance, difficulty)
    pairs = []
    for r in range(rows):
        for c in range(cols):
            v = r * cols + c
            if c + 1 < cols:
                pairs.append((v, v + 1))
            if r + 1 < rows:
                pairs.append((v, v + cols))
            if c + 1 < cols and r + 1 < rows:
                pairs.append((v, v + cols + 1) if rng.random() < 0.5 else (v + 1, v + cols))
    roads = {}
    for eid, (u, v) in enumerate(pairs):
        straight = math.dist(points[u], points[v])
        roads[eid] = (u, v, math.ceil(straight * rng.uniform(1.0, 1.3) * 10) / 10,
                      rng.choice((1, 1, 1, 2, 2, 2, 3, 3)))
    candidates = _snapshot(points, roads, roads, rate)
    stages.append(Stage("candidates", f"{len(roads)} candidate two-way roads", candidates))
    parts = len(connected_components(candidates).components)
    if parts != 1:
        return None, "candidates", [f"candidate road graph is disconnected ({parts} parts), no spanning tree exists"]

    # 3. MST backbone (weight = road length)
    mst = kruskal(list(points), [(eid, u, v, d) for eid, (u, v, d, _) in roads.items()])
    chosen = {edge[0] for edge in mst.edges}
    stages.append(Stage("mst", f"Kruskal backbone: {len(chosen)} roads, total length {mst.total_weight:.0f}",
                        _snapshot(points, roads, chosen, rate),
                        {"total_weight": mst.total_weight, "edges_examined": mst.edges_examined,
                         "comparisons": mst.comparisons, "finds": mst.finds, "unions": mst.unions}))

    # 4. extra roads. One MST leaf is kept as the track's dead end.
    degree = dict.fromkeys(points, 0)
    for eid in chosen:
        degree[roads[eid][0]] += 1
        degree[roads[eid][1]] += 1
    leaf = rng.choice([v for v in sorted(points) if degree[v] == 1])
    spare = [eid for eid in roads if eid not in chosen]
    rng.shuffle(spare)
    extras = []
    for eid in spare:
        u, v = roads[eid][:2]
        if len(extras) >= C.GEN_EXTRA_FRACTION * len(spare):
            break
        if leaf in (u, v) or max(degree[u], degree[v]) >= C.GEN_MAX_DEGREE:
            continue
        extras.append(eid)
        degree[u] += 1
        degree[v] += 1
    chosen |= set(extras)
    base = _snapshot(points, roads, chosen, rate)
    stages.append(Stage("extras", f"{len(extras)} extra roads add cycles and alternative routes", base,
                        {"extras": sorted(extras), "dead_end": leaf}))

    # 5. main loop by backtracking: loop[i] adjacent to loop[i-1], all distinct, last adjacent to first
    road_between = {v: {w: e.id for e, w in base.incident(v)} for v in points}
    hops = {v: bfs(base, v).dist for v in points}
    order = sorted(points)
    rng.shuffle(order)
    loop: list[int] = []
    for length in C.GEN_LOOP_LENGTHS:
        slots = list(range(length))

        def fits(assignment, slot, vertex, length=length):
            if slot == 0:
                return True
            if vertex in assignment.values() or vertex not in road_between[assignment[slot - 1]]:
                return False
            return slot < length - 1 or assignment[0] in road_between[vertex]

        def too_far(assignment, remaining):     # cannot get back to the first vertex in time
            return hops[assignment[len(assignment) - 1]][assignment[0]] > len(remaining) + 1

        found = solve(slots, dict.fromkeys(slots, order), fits, too_far, C.GEN_LOOP_NODE_LIMIT)
        solver["loop"] = found
        if found.solved:
            loop = [found.assignment[i] for i in slots]
            break
    if not loop:
        return None, "loop", [f"backtracking found no closed loop of {C.GEN_LOOP_LENGTHS} roads"
                              + (" (node limit hit)" if solver["loop"].limit_hit else "")]
    n = len(loop)
    pos = {v: i for i, v in enumerate(loop)}
    loop_roads = [road_between[a][b] for a, b in zip(loop, loop[1:])]
    closing = road_between[loop[-1]][loop[0]]

    stages.append(Stage("loop", f"backtracking found a closed main loop of {n} roads", base, {"loop": loop}))

    # 6. one-way roads, added after the MST: Finish -> Start and one extra road off the loop
    one_way = {closing: (loop[-1], loop[0])}
    off_loop = [eid for eid in extras if eid not in loop_roads and eid != closing]
    if off_loop:
        eid = rng.choice(off_loop)
        u, v = roads[eid][:2]
        one_way[eid] = (u, v) if rng.random() < 0.5 else (v, u)
    directed = _snapshot(points, roads, chosen, rate, one_way)
    stages.append(Stage("one_way", f"{len(one_way)} roads made one-way (Finish -> Start and one off the loop)",
                        directed, {"one_way": sorted(one_way)}))

    # 7. placement by backtracking. Positions are indices into `loop` (0 = Start, n-1 = Finish).
    bridges = set()
    for eid in chosen:
        base.block_edge(eid)
        if len(connected_components(base).components) > 1:
            bridges.add(eid)
        base.unblock_edge(eid)
    chords = []                                   # (road id, i, j, is a new road)
    for eid, (u, v, _, _) in roads.items():
        if u in pos and v in pos and eid not in one_way:
            i, j = sorted((pos[u], pos[v]))
            if 2 <= j - i <= C.GEN_SHORTCUT_MAX_SKIP + 1:
                chords.append((eid, i, j, eid not in chosen))
    chords.sort(key=lambda chord: (chord[2] - chord[1], chord[0]))
    inner = list(range(1, n - 1))
    on_loop = [e for e in loop_roads if _bypass(directed, e, *_ends(loop, pos, roads[e]))]
    rng.shuffle(on_loop)
    others = [e for e in sorted(chosen) if e not in loop_roads and e != closing]
    rng.shuffle(others)
    spots = sorted(points, key=lambda v: (v in pos, v))       # nitro: off the loop first
    cps = [("cp", k) for k in range(1, C.MIN_CHECKPOINTS + 1)]

    def near(target: float) -> list[int]:
        """Loop positions, closest to `target` first: value order that spreads things round the lap."""
        return sorted(inner, key=lambda p: (abs(p - target), p))

    domains = {("shortcut", 1): chords, ("shortcut", 2): chords,
               ("station", 1): near(n / 4), ("station", 2): near(3 * n / 4),
               **{cp: near(cp[1] * (n - 1) / (len(cps) + 1)) for cp in cps},
               ("nitro", 1): spots, ("nitro", 2): spots, ("nitro", 3): spots,
               ("block", 1): on_loop, ("block", 2): others, ("oil", 1): loop_roads, ("speed", 1): loop_roads}
    variables = list(domains)

    def blocked_positions(a) -> set[int]:
        """Loop positions that cannot hold a checkpoint: stations and vertices a shortcut cuts off."""
        out = {a[key] for key in (("station", 1), ("station", 2)) if key in a}
        for key in (("shortcut", 1), ("shortcut", 2)):
            if key in a:
                out.update(range(a[key][1] + 1, a[key][2]))
        return out

    def consistent(a, var, value) -> bool:
        kind, k = var
        if kind == "shortcut":
            eid, i, j, new = value
            if new and max(degree[loop[i]], degree[loop[j]]) >= C.GEN_MAX_DEGREE:
                return False                                   # maximum degree
            return k == 1 or i > a[("shortcut", 1)][2]          # apart from the first shortcut
        if kind == "station":
            if k == 1:
                return True
            gap = value - a[("station", 1)]                     # fuel-station spacing, both ways round
            return gap >= C.GEN_STATION_MIN_GAP and n - gap >= C.GEN_STATION_MIN_GAP
        if kind == "cp":
            return value > a.get(("cp", k - 1), 0) and value not in blocked_positions(a)
        if kind == "nitro":
            if value == leaf or (value in pos and (pos[value] in (0, n - 1) or
                                                   pos[value] in {a[cp] for cp in cps} | blocked_positions(a))):
                return False
            return all(hops[value][a[("nitro", m)]] >= C.GEN_NITRO_MIN_HOPS for m in range(1, k))
        # obstacle sites (roads)
        if value in (a[("shortcut", 1)][0], a[("shortcut", 2)][0]):
            return False
        if kind == "block" and value in bridges:
            return False                                       # never close a critical bridge
        ends = set(roads[value][:2])
        placed = [a[key] for key in (("block", 1), ("block", 2), ("oil", 1), ("speed", 1)) if key in a]
        return all(ends.isdisjoint(roads[e][:2]) for e in placed)   # obstacle spacing

    def no_room(a, remaining) -> bool:
        """Forward check: every checkpoint still to place needs its own later free loop position."""
        waiting = sum(1 for var in remaining if var[0] == "cp")
        last = max((a[cp] for cp in cps if cp in a), default=0)
        return waiting > len(set(range(last + 1, n - 1)) - blocked_positions(a))

    placed = solve(variables, domains, consistent, no_room)
    solver["placement"] = placed
    if not placed.solved:
        return None, "placement", ["backtracking found no placement of shortcuts, stations, checkpoints, "
                                   "pickups and obstacles that satisfies the spacing and degree rules"
                                   + (" (node limit hit)" if placed.limit_hit else "")]
    a = placed.assignment
    shortcuts = [a[("shortcut", 1)][0], a[("shortcut", 2)][0]]
    roles = {loop[0]: (G.START,), loop[-1]: (G.FINISH,), leaf: (G.DEAD_END,)}
    roles.update({loop[a[cp]]: (G.CHECKPOINT, cp[1]) for cp in cps})
    roles.update({loop[a[("station", k)]]: (G.FUEL_STATION,) for k in (1, 2)})
    roles.update({a[("nitro", k)]: (G.NITRO_PICKUP, None, k != 3) for k in (1, 2, 3)})   # third = event-driven booster
    final = _snapshot(points, roads, chosen | set(shortcuts), rate, one_way, set(shortcuts), roles)
    block1, block2 = a[("block", 1)], a[("block", 2)]
    events = [(12, C.EVENT_NITRO_SPAWN, a[("nitro", 3)]), (22, C.EVENT_OIL_SPILL, a[("oil", 1)]),
              (35, C.EVENT_ROAD_BLOCK, block1), (50, C.EVENT_SHORTCUT_CLOSE, shortcuts[0]),
              (62, C.EVENT_SPEED_RESTRICTION, a[("speed", 1)]), (75, C.EVENT_ROAD_CLEAR, block1),
              (88, C.EVENT_STATION_OUTAGE, loop[a[("station", 2)]]), (100, C.EVENT_SHORTCUT_OPEN, shortcuts[0]),
              (115, C.EVENT_ROAD_BLOCK, block2), (130, C.EVENT_OIL_SPILL, a[("oil", 1)]),
              (150, C.EVENT_ROAD_CLEAR, block2), (165, C.EVENT_NITRO_SPAWN, a[("nitro", 3)])]
    circuit = Circuit(name, final, list(loop), _bypass(final, block1, *_ends(loop, pos, roads[block1])),
                      shortcuts, [{"time": t, "type": kind, "target": target} for t, kind, target in events])
    stages.append(Stage("placement", "start, finish, checkpoints, services, shortcuts and obstacle sites placed",
                        final, {"assignment": dict(a), "bridges": sorted(bridges)}))
    check = validate_circuit(circuit)
    if not check.ok:
        return None, "validation", check.failures
    return circuit, "", []


def _ends(loop, pos, road) -> tuple[int, int]:
    """Endpoints of a loop road in driving order."""
    u, v = road[:2]
    return (u, v) if pos[u] < pos[v] else (v, u)

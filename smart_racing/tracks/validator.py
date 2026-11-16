"""Playability checks for a circuit (Project.md 4.1 and 5.4, SPEC 4.1).

Everything here calls the gameplay algorithms (BFS, DFS, Dijkstra, refuel DP);
nothing is re-implemented. A track is validated in its current state, so run
this on a freshly loaded track with no active effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from smart_racing import config
from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import dead_ends, enumerate_paths, find_cycle
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.algorithms.refuel import RefuelResult, plan_refuel
from smart_racing.core.cost import CostFn
from smart_racing.core.graph import DEAD_END, FUEL_STATION, NITRO_PICKUP, START, FINISH, TrackGraph
from smart_racing.tracks.loader import Circuit, route_edges


@dataclass
class ValidationResult:
    ok: bool = True
    failures: list[str] = field(default_factory=list)   # one readable reason per failed rule
    info: dict = field(default_factory=dict)            # counts and the fuel plan, for display

    def fail(self, reason: str) -> None:
        self.ok = False
        self.failures.append(reason)


def fuel_cost(edge) -> float:
    return edge.effective_fuel


def checkpoint_route(graph: TrackGraph, cost_fn: CostFn = fuel_cost,
                     laps: int = 1) -> tuple[list[int], list[int]] | None:
    """Cheapest race route that respects checkpoint order: Dijkstra leg by leg
    Start -> cp1 -> ... -> cpn -> Finish, then Finish -> cp1 ... for each further
    lap. Returns (vertex path, edge path) or None when a leg has no route.
    Time O(laps * n * (V + E) log V) for n checkpoints."""
    stops = [cp.id for cp in graph.checkpoints()] + [graph.finish.id]
    vertices, edges = [graph.start.id], []
    for target in stops * laps:
        leg = dijkstra(graph, vertices[-1], target, cost_fn)
        if not leg.found:
            return None
        vertices += leg.path[1:]
        edges += leg.edge_path
    return vertices, edges


def fuel_plan(graph: TrackGraph, vertices: list[int], edges: list[int]) -> RefuelResult:
    """Refuel DP along a fixed route. Stops are the route's first vertex (no
    fuel on sale) and every visit to an active fuel station; a station that is
    the last vertex only adds an empty final leg. O(len(route)) plus the DP."""
    demands, available = [0.0], [False]
    for edge_id, arrive in zip(edges, vertices[1:]):
        demands[-1] += graph.edge(edge_id).effective_fuel
        vertex = graph.vertex(arrive)
        if vertex.type == FUEL_STATION and vertex.active:
            demands.append(0.0)
            available.append(True)
    return plan_refuel(demands, available)


def main_route_race(graph: TrackGraph, main_route: list[int], laps: int) -> tuple[list[int], list[int]] | None:
    """The fixed main route driven for `laps` laps: laps after the first go
    Finish -> checkpoint 1 by the least-fuel road and rejoin the main route there."""
    first_cp = graph.checkpoints()[0].id
    back = dijkstra(graph, main_route[-1], first_cp, fuel_cost)
    if not back.found or first_cp not in main_route:
        return None
    later = back.path[1:] + main_route[main_route.index(first_cp) + 1:]
    vertices = list(main_route) + later * (laps - 1)
    return vertices, route_edges(graph, vertices)


def validate(graph: TrackGraph, main_route: list[int] | None = None, *,
             min_checkpoints: int = config.MIN_CHECKPOINTS,
             min_shortcuts: int = config.MIN_SHORTCUTS,
             min_stations: int = config.MIN_FUEL_STATIONS,
             min_nitro: int = config.MIN_NITRO_PICKUPS,
             min_one_way: int = config.MIN_ONE_WAY_ROADS,
             min_difficulty_levels: int = config.MIN_DIFFICULTY_LEVELS,
             min_routes: int = config.MIN_START_FINISH_ROUTES,
             require_dead_end: bool = True,
             laps: int = config.LAPS_PER_RACE) -> ValidationResult:
    """Check every playability rule and list each one that fails.

    The fuel rule passes when the refuel DP finds a plan for the whole race on
    the least-fuel route through the checkpoints or, when `main_route` is
    given, on that route.
    """
    res = ValidationResult()
    starts, finishes = graph.vertices_of_type(START), graph.vertices_of_type(FINISH)
    if len(starts) != 1 or len(finishes) != 1:
        res.fail(f"need exactly one Start and one Finish, found {len(starts)} and {len(finishes)}")
        return res                                   # nothing else can be checked
    start, finish = starts[0].id, finishes[0].id
    cps = graph.checkpoints()
    edges = graph.edges()
    counts = {
        "checkpoints": len(cps),
        "shortcuts": sum(e.is_shortcut for e in edges),
        "fuel stations": len(graph.vertices_of_type(FUEL_STATION)),
        "nitro pickups": len(graph.vertices_of_type(NITRO_PICKUP)),
        "one-way roads": sum(e.directed for e in edges),
        "difficulty levels": len({e.difficulty for e in edges}),
    }
    res.info["counts"] = counts
    minimums = (min_checkpoints, min_shortcuts, min_stations, min_nitro, min_one_way, min_difficulty_levels)
    for (what, found), needed in zip(counts.items(), minimums):
        if found < needed:
            res.fail(f"too few {what}: {found}, need at least {needed}")
    if [cp.checkpoint_order for cp in cps] != list(range(1, len(cps) + 1)):
        res.fail("checkpoint orders must be exactly 1..n with no gaps or repeats")
    if not cps:
        return res

    # Ordered reachability, leg by leg, in the directed graph.
    names = ([("Start", start)] + [(f"checkpoint {cp.checkpoint_order}", cp.id) for cp in cps]
             + [("Finish", finish)])
    legs_ok = True
    for (a_name, a), (b_name, b) in zip(names, names[1:]):
        if not bfs(graph, a, b).found:
            legs_ok = False
            res.fail(f"{b_name} (vertex {b}) is unreachable from {a_name} (vertex {a})")
    if not bfs(graph, finish, cps[0].id).found:
        legs_ok = False
        res.fail(f"no route from Finish (vertex {finish}) back to checkpoint 1 "
                 f"(vertex {cps[0].id}) for the next lap")

    # ponytail: enumerate_paths is exponential when fewer than min_routes paths
    # exist in a large cyclic graph; fine at circuit size (limits in config).
    routes = len(enumerate_paths(graph, start, finish, max_routes=min_routes).paths)
    res.info["start_finish_routes"] = routes
    if routes < min_routes:
        res.fail(f"only {routes} Start-to-Finish route(s), need at least {min_routes}")

    if not find_cycle(graph).has_cycle:
        res.fail("the track has no cycle")
    reported = dead_ends(graph, start, finish).dead_ends
    res.info["dead_ends"] = reported
    if require_dead_end and not any(graph.vertex(v).type == DEAD_END for v in reported):
        res.fail("no DeadEnd vertex is reported by the dead-end analysis")

    if legs_ok:
        plan = fuel_plan(graph, *checkpoint_route(graph, fuel_cost, laps))
        if not plan.feasible and main_route:
            try:
                race = main_route_race(graph, main_route, laps)
            except ValueError:
                race = None
            if race:
                plan = fuel_plan(graph, *race)
        res.info["fuel_plan"] = plan
        if not plan.feasible:
            res.fail(f"no feasible fuel plan for {laps} lap(s): {plan.reason}")
    return res


def validate_circuit(circuit: Circuit, **thresholds) -> ValidationResult:
    """`validate` plus the race data: main route, detour, Opponent 2's
    shortcuts and the event script must fit the graph."""
    graph, route = circuit.graph, circuit.main_route
    res = validate(graph, route, **thresholds)
    if len(graph.vertices_of_type(START)) != 1 or len(graph.vertices_of_type(FINISH)) != 1:
        return res
    cp_ids = [cp.id for cp in graph.checkpoints()]
    position = {v: i for i, v in enumerate(route)}
    try:
        route_edges(graph, route)
        route_edges(graph, circuit.detour)
    except ValueError as error:
        res.fail(f"main route or detour is not drivable: {error}")
    if (len(position) != len(route) or not route or route[0] != graph.start.id
            or route[-1] != graph.finish.id or [v for v in route if v in set(cp_ids)] != cp_ids):
        res.fail("main route must be a simple path Start -> checkpoints in order -> Finish")
        return res

    def skips_checkpoint(a: int, b: int) -> bool:
        return any(graph.vertex(v).is_mandatory for v in route[position[a] + 1:position[b]])

    d = circuit.detour
    if (len(d) < 2 or d[0] not in position or d[-1] not in position
            or position[d[0]] >= position[d[-1]] or skips_checkpoint(d[0], d[-1])):
        res.fail("detour must leave the main route and rejoin it further on without skipping a checkpoint")
    if not circuit.opponent_shortcuts:
        res.fail("no shortcut is designated for Opponent 2")
    for edge_id in circuit.opponent_shortcuts:
        edge = graph.edge(edge_id) if graph.has_edge(edge_id) else None
        if edge is None or not edge.is_shortcut:
            res.fail(f"designated shortcut {edge_id} is not a shortcut road")
            continue
        a, b = edge.src, edge.dst
        if a in position and b in position and position[a] > position[b] and not edge.directed:
            a, b = b, a
        if a not in position or b not in position or position[a] >= position[b] or skips_checkpoint(a, b):
            res.fail(f"designated shortcut {edge_id} must join two main-route vertices, "
                     f"forwards, without skipping a checkpoint")
    for event in circuit.events:
        on_edge = event["type"] not in (config.EVENT_STATION_OUTAGE, config.EVENT_NITRO_SPAWN)
        if event["type"] not in config.EVENT_PRIORITY:
            res.fail(f"event script: unknown event type {event['type']!r}")
        elif not (graph.has_edge if on_edge else graph.has_vertex)(event["target"]):
            res.fail(f"event script: {event['type']} targets missing "
                     f"{'road' if on_edge else 'vertex'} {event['target']}")
    return res

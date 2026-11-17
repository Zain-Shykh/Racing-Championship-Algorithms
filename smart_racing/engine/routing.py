"""Checkpoint-aware route planning (Project.md 5.2, SPEC 4.1 and 4.6).

A race route is planned leg by leg: current vertex -> next required checkpoint
-> ... -> Finish, then on into the following laps. Each leg is one Dijkstra or
A* search, so a route can never skip a mandatory checkpoint. Nothing is cached:
re-planning after an event is simply calling the planner again on the changed graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from smart_racing import config
from smart_racing.algorithms.astar import astar
from smart_racing.algorithms.dijkstra import PathResult, dijkstra
from smart_racing.core.cost import CostFn, make_cost_fn, route_summary
from smart_racing.core.graph import FUEL_STATION, TrackGraph

ALGORITHMS = {"dijkstra": dijkstra, "astar": astar}
Cost = str | Sequence[float] | Callable


@dataclass
class RoutePlan:
    """A planned route with the totals and search counters a screen shows."""
    found: bool
    algorithm: str
    vertices: list[int] = field(default_factory=list)   # vertex ids, source first
    edges: list[int] = field(default_factory=list)      # edge ids along `vertices`
    targets: list[int] = field(default_factory=list)    # mandatory vertices, in visiting order
    legs: list[PathResult] = field(default_factory=list)  # one search result per leg
    failed_target: int | None = None                    # first target with no route
    distance: float = 0.0
    time: float = 0.0              # effective travel time, s
    fuel: float = 0.0              # effective fuel
    cost: float = 0.0              # exact scalar cost that was minimised
    expanded: int = 0
    relaxed: int = 0
    edges_examined: int = 0
    heap_ops: int = 0

    @property
    def summary(self) -> dict[str, float]:
        return {"distance": self.distance, "time": self.time, "fuel": self.fuel, "cost": self.cost}


def as_cost_fn(cost: Cost) -> CostFn:
    """A preset name or weight tuple becomes the SPEC 4.3 cost; a function is kept."""
    return cost if callable(cost) else make_cost_fn(cost)


def race_targets(graph: TrackGraph, next_checkpoint: int = 1, laps: int = 1) -> list[int]:
    """Mandatory vertices still to visit: the rest of this lap, then `laps - 1` full laps."""
    lap = [cp.id for cp in graph.checkpoints()] + [graph.finish.id]
    return lap[next_checkpoint - 1:] + lap * (laps - 1)


def walk(graph: TrackGraph, vertex: int, edges: Iterable[int]) -> list[int]:
    """Vertex ids visited when driving `edges` from `vertex`. O(len(edges))."""
    vertices = [vertex]
    for edge_id in edges:
        vertices.append(graph.edge(edge_id).other(vertices[-1]))
    return vertices


def make_plan(graph: TrackGraph, vertices: list[int], edges: list[int], cost: Cost = "Balanced",
              algorithm: str = "fixed", targets: Iterable[int] = (),
              legs: Iterable[PathResult] = ()) -> RoutePlan:
    """Wrap a known route in a RoutePlan with its totals. O(len(edges))."""
    legs = list(legs)
    return RoutePlan(True, algorithm, list(vertices), list(edges), list(targets), legs,
                     **route_summary(graph, edges, as_cost_fn(cost)),
                     expanded=sum(leg.expanded for leg in legs),
                     relaxed=sum(leg.relaxed for leg in legs),
                     edges_examined=sum(leg.edges_examined for leg in legs),
                     heap_ops=sum(leg.heap_ops for leg in legs))


def plan_through(graph: TrackGraph, source: int, targets: Sequence[int], cost: Cost = "Balanced",
                 algorithm: str = "astar") -> RoutePlan:
    """Cheapest route visiting `targets` in order, one search per leg.
    If a leg has no route the plan has `found=False`, names the target and keeps
    the part found so far. Time O(len(targets) * (V + E) log V)."""
    cost_fn, search = as_cost_fn(cost), ALGORITHMS[algorithm]
    vertices, edges, legs = [source], [], []
    for target in targets:
        leg = search(graph, vertices[-1], target, cost_fn)
        legs.append(leg)
        if not leg.found:
            plan = make_plan(graph, vertices, edges, cost_fn, algorithm, targets, legs)
            plan.found, plan.failed_target = False, target
            return plan
        vertices += leg.path[1:]
        edges += leg.edge_path
    return make_plan(graph, vertices, edges, cost_fn, algorithm, targets, legs)


def plan_route(graph: TrackGraph, source: int, next_checkpoint: int = 1, laps: int = 1,
               cost: Cost = "Balanced", algorithm: str = "astar") -> RoutePlan:
    """Race route from a racer's vertex and checkpoint progress to the end of
    the race (`laps` = laps still to finish, the current one included)."""
    return plan_through(graph, source, race_targets(graph, next_checkpoint, laps), cost, algorithm)


def compare_presets(graph: TrackGraph, source: int, next_checkpoint: int = 1, laps: int = 1,
                    algorithm: str = "astar") -> dict[str, RoutePlan]:
    """The race route under each of the four weight presets (Challenge 2)."""
    return {preset: plan_route(graph, source, next_checkpoint, laps, preset, algorithm)
            for preset in config.COST_PRESETS}


def route_affected(route_edges: Iterable[int], changed_edges: Iterable[int]) -> bool:
    """True when an edge that was blocked, reopened or re-costed lies on the route."""
    return not set(changed_edges).isdisjoint(route_edges)


def effective_fuel(edge) -> float:
    return edge.effective_fuel


def nearest_station(graph: TrackGraph, vertex: int, fuel: float,
                    include_closed: bool = False) -> RoutePlan | None:
    """Route to the active fuel station that takes the least fuel to reach and
    that `fuel` can reach (ties: lower vertex id). The current vertex does not
    count. `include_closed` also accepts a station that is out of service.
    One Dijkstra on effective fuel, O((V + E) log V)."""
    search = dijkstra(graph, vertex, None, effective_fuel)
    best = None
    for station in graph.vertices_of_type(FUEL_STATION):
        need = search.dist.get(station.id)
        if ((station.active or include_closed) and station.id != vertex
                and need is not None and need <= fuel):
            if best is None or need < search.dist[best]:
                best = station.id
    if best is None:
        return None
    return make_plan(graph, *search.path_to(best), effective_fuel, "dijkstra", [best], [search])

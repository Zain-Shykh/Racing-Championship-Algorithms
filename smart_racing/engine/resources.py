"""Resource planner (Project.md 5.3): pickup recommendation by 0/1 knapsack
(DP, with greedy for comparison) and a refuelling plan from the refuel DP.

Pickup model (docs/RULES.md "Resource planner"). An item is an optional
service vertex next to the route. Its cost is the extra travel time of the
cheapest out-and-back loop from a route vertex, in tenths of a second, rounded
up. The budget is the detour time the racer accepts. Benefits are points:
a nitro charge is worth the time one activation saves, an off-route fuel
station (offered only when the route has no feasible refuel plan) the units
of the route's fuel shortfall it can cover. Fuel is a
separate resource and is not folded into the budget: the chosen detours are
spliced into the route and checked with the refuel DP, and items are dropped
until that plan is feasible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from smart_racing import config
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.algorithms.knapsack import Item, KnapsackResult, knapsack_dp, knapsack_greedy
from smart_racing.algorithms.refuel import RefuelResult, plan_refuel
from smart_racing.algorithms.sorting import merge_sort
from smart_racing.core.cost import time_cost
from smart_racing.core.graph import FUEL_STATION, NITRO_PICKUP, TrackGraph
from smart_racing.engine.routing import walk


def fuel_to_next_station(graph: TrackGraph, vertex: int, edges: list[int]) -> tuple[float, int | None]:
    """Fuel needed to drive `edges` from `vertex` up to the first active fuel
    station ahead, or to the end of the route: (fuel, station id or None)."""
    need = 0.0
    for edge_id in edges:
        edge = graph.edge(edge_id)
        need += edge.effective_fuel
        vertex = edge.other(vertex)
        stop = graph.vertex(vertex)
        if stop.type == FUEL_STATION and stop.active:
            return need, vertex
    return need, None


@dataclass
class RefuelAdvice:
    result: RefuelResult
    stops: list[int]               # vertex id of each DP stop; stop 0 is the current vertex
    demands: list[float]
    available: list[bool]

    @property
    def buy_now(self) -> int:
        """Units to buy at the current vertex (0 when the plan is infeasible)."""
        return self.result.purchases[0] if self.result.feasible else 0

    @property
    def purchases(self) -> list[tuple[int, int]]:
        """(station vertex, units) for every paid stop of the plan."""
        return [(v, a) for v, a in zip(self.stops, self.result.purchases) if a > 0]


def refuel_plan(graph: TrackGraph, vertex: int, edges: list[int], fuel: float,
                here_open: bool | None = None) -> RefuelAdvice:
    """Refuel DP along a fixed route from `vertex` with `fuel` in the tank.
    Stops are the current vertex and every later visit to an active station.
    `here_open` says whether fuel can be bought right now (default: the
    current vertex is an active station). O(len(edges)) plus the DP."""
    here = graph.vertex(vertex)
    if here_open is None:
        here_open = here.type == FUEL_STATION and here.active
    stops, demands, available = [vertex], [0.0], [here_open]
    for edge_id in edges:
        edge = graph.edge(edge_id)
        demands[-1] += edge.effective_fuel
        vertex = edge.other(vertex)
        stop = graph.vertex(vertex)
        if stop.type == FUEL_STATION and stop.active:
            stops.append(vertex)
            demands.append(0.0)
            available.append(True)
    fuel = min(max(fuel, 0.0), config.TANK_CAPACITY)
    return RefuelAdvice(plan_refuel(demands, available, fuel), stops, demands, available)


@dataclass
class PickupOption:
    vertex: int
    kind: str                      # "nitro" or "fuel"
    leave_index: int               # index in the route's vertex list where the loop is driven
    loop_edges: list[int]          # out and back; empty when the pickup is on the route
    extra_time: float
    extra_fuel: float
    item: Item


@dataclass
class PickupPlan:
    options: list[PickupOption]
    budget: int                    # scaled detour-time budget
    dp: KnapsackResult
    greedy: KnapsackResult
    recommended: list[int]         # pickup vertex ids kept after the fuel check
    edges: list[int]               # the route with the recommended loops spliced in
    refuel: RefuelAdvice           # refuel plan for `edges`
    feasible: bool                 # the refuel DP can drive `edges`
    dropped: list[int] = field(default_factory=list)   # chosen by the knapsack, removed by the fuel check


def _splice(edges: list[int], options: list[PickupOption]) -> list[int]:
    out = list(edges)
    for option in merge_sort(options, lambda a, b: (-a.leave_index, a.vertex) < (-b.leave_index, b.vertex)).items:
        out[option.leave_index:option.leave_index] = option.loop_edges
    return out


def pickup_plan(graph: TrackGraph, vertex: int, edges: list[int], fuel: float, nitro_charges: int,
                budget_seconds: float = config.PICKUP_DETOUR_BUDGET, solver: str = "dp") -> PickupPlan:
    """Recommend optional pickups for the route `edges` driven from `vertex`.

    Candidates: active nitro pickups while a charge slot is free (at most as
    many as free slots, cheapest first, since they are worth the same), and
    active off-route fuel stations when the refuel DP finds no plan for the
    route as it stands. An
    inactive or unreachable pickup is never offered. `solver` picks whose
    selection is applied ("dp" or "greedy"); both results are returned.
    Time: one Dijkstra per distinct route vertex and per candidate, plus the
    O(items * budget) knapsack.
    """
    route = walk(graph, vertex, edges)
    ahead = set(route[1:])
    free = config.NITRO_MAX_CHARGES - nitro_charges
    shortfall = sum(graph.edge(e).effective_fuel for e in edges) - fuel
    if refuel_plan(graph, vertex, edges, fuel).result.feasible:
        shortfall = 0.0                    # the stations on the route are enough: none is offered
    from_route: dict[int, object] = {}
    options: list[PickupOption] = []
    for cand in graph.vertices():
        kind = {NITRO_PICKUP: "nitro", FUEL_STATION: "fuel"}.get(cand.type)
        if kind is None or not cand.active or cand.id == vertex:
            continue
        if (kind == "nitro" and free <= 0) or (kind == "fuel" and (shortfall <= 0 or cand.id in ahead)):
            continue
        best = (0.0, route.index(cand.id), [], 0.0) if cand.id in ahead else None
        if best is None:
            back = dijkstra(graph, cand.id, None, time_cost)
            for i, u in enumerate(route):
                if u not in from_route:
                    from_route[u] = dijkstra(graph, u, None, time_cost)
                out = from_route[u]
                if cand.id not in out.dist or u not in back.dist:
                    continue
                extra = out.dist[cand.id] + back.dist[u]
                if best is None or extra < best[0]:
                    loop = out.path_to(cand.id)[1] + back.path_to(u)[1]
                    best = (extra, i, loop, sum(graph.edge(e).effective_fuel for e in loop))
        if best is None:
            continue                                   # unreachable detour
        benefit = (config.PICKUP_NITRO_BENEFIT if kind == "nitro"
                   else min(config.STATION_MAX_PURCHASE, shortfall))
        cost = math.ceil(round(best[0] * config.PICKUP_COST_SCALE, 6))
        options.append(PickupOption(cand.id, kind, best[1], best[2], best[0], best[3],
                                    Item(cand.id, cost, benefit, f"{kind} at vertex {cand.id}")))
    nitro = merge_sort([o for o in options if o.kind == "nitro"],
                       lambda a, b: (a.item.cost, a.vertex) < (b.item.cost, b.vertex)).items[:max(free, 0)]
    options = [o for o in options if o.kind == "fuel" or o in nitro]
    items = [o.item for o in options]
    budget = int(budget_seconds * config.PICKUP_COST_SCALE)
    dp, greedy = knapsack_dp(items, budget), knapsack_greedy(items, budget)
    picked = set((dp if solver == "dp" else greedy).selected)
    chosen = [o for o in options if o.vertex in picked]
    dropped: list[int] = []
    while True:
        spliced = _splice(edges, chosen)
        advice = refuel_plan(graph, vertex, spliced, fuel)
        if advice.result.feasible or not chosen:
            break
        # Fuel check failed: give up the thirstiest loop, nitro loops before stations.
        worst = max(chosen, key=lambda o: (o.kind == "nitro", o.extra_fuel, o.vertex))
        chosen.remove(worst)
        dropped.append(worst.vertex)
    return PickupPlan(options, budget, dp, greedy, [o.vertex for o in chosen], spliced, advice,
                      advice.result.feasible, dropped)

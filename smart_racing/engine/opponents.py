"""Racer strategies (Project.md 4.4): the three deterministic opponents and the
player's autopilot. A strategy plans a route for the rest of the race and
decides how much fuel to buy at a station; the RaceEngine applies the same
rules, recovery policy and fuel limits to every one of them.
"""
from __future__ import annotations

import math

from smart_racing import config
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.core.cost import distance_cost
from smart_racing.core.graph import CHECKPOINT, Edge, TrackGraph
from smart_racing.engine.resources import fuel_to_next_station, pickup_plan, refuel_plan
from smart_racing.engine.routing import RoutePlan, make_plan, plan_route, walk
from smart_racing.tracks.loader import Circuit, route_edges


def fill_amount(fuel: float) -> int:
    """Whole units bought on a fill-up: at most 40 and never above the tank."""
    return max(0, min(config.STATION_MAX_PURCHASE, math.floor(config.TANK_CAPACITY - fuel)))


def needs_fuel(graph: TrackGraph, vertex: int, route: list[int], fuel: float) -> bool:
    """The opponents' "eligible station" test: below 25% of the tank, or not
    enough fuel (plus the safety margin) to reach the next active station on
    the route, or the end of the route when there is none."""
    need, _ = fuel_to_next_station(graph, vertex, route)
    return (fuel < config.LOW_FUEL_FRACTION * config.TANK_CAPACITY
            or fuel < need + config.REFUEL_SAFETY_MARGIN)


def wants_nitro(graph: TrackGraph, vertex: int, edge: Edge, route_after: list[int],
                fuel: float, charges: int, max_difficulty: int) -> bool:
    """Fixed nitro rule of every automatic racer, checked when entering `edge`
    from `vertex`: a charge is used on an easy, unobstructed road at least as
    long as the boost, and only if the doubled fuel use cannot stop the car
    reaching its next station (or the end of the route)."""
    if (charges <= 0 or edge.effective_difficulty > max_difficulty
            or edge.obstacle_penalty > 0 or edge.effective_time < config.NITRO_DURATION):
        return False
    route = [edge.id] + route_after
    need, _ = fuel_to_next_station(graph, vertex, route)
    window = config.NITRO_DURATION * config.NITRO_SPEED_MULT    # normal-speed seconds covered by the boost
    rate, seconds = 0.0, 0.0
    for edge_id in route:                      # thirstiest road the boost can touch
        e = graph.edge(edge_id)
        if e.effective_time > 0:
            rate = max(rate, e.effective_fuel / e.effective_time)
        seconds += e.effective_time
        if seconds >= window:
            break
    extra = rate * window * (config.NITRO_FUEL_MULT - 1.0)
    return fuel >= need + extra + config.REFUEL_SAFETY_MARGIN


class _Opponent:
    """Shared opponent refuelling: fill up at an eligible station (see needs_fuel)."""
    name = ""

    def refuel_amount(self, graph: TrackGraph, vertex: int, route: list[int], fuel: float) -> int:
        return fill_amount(fuel) if needs_fuel(graph, vertex, route, fuel) else 0


class FixedRoute(_Opponent):
    """Opponent 1: the circuit's stored main route. If a road of the stretch
    the fixed detour bypasses is blocked and the detour is open, it takes the
    detour; any other blockage is driven up to and waited at."""
    name = "fixed"
    use_shortcuts = False

    def lap(self, circuit: Circuit) -> tuple[list[int], list[int]]:
        """One lap Start..Finish as (vertices, edges) for the current track state."""
        g = circuit.graph
        vs, es = list(circuit.main_route), route_edges(g, circuit.main_route)

        def splice(a: int, b: int, new_vs: list[int], new_es: list[int], when_blocked: bool) -> None:
            if a not in vs or b not in vs or vs.index(a) >= vs.index(b):
                return
            i, j = vs.index(a), vs.index(b)
            if any(g.edge(e).blocked for e in new_es):
                return
            if when_blocked and not any(g.edge(e).blocked for e in es[i:j]):
                return
            vs[i:j + 1], es[i:j] = new_vs, new_es

        if self.use_shortcuts:
            position = {v: i for i, v in enumerate(circuit.main_route)}
            for edge_id in circuit.opponent_shortcuts:
                edge = g.edge(edge_id)
                a, b = edge.src, edge.dst
                if not edge.directed and position.get(a, 0) > position.get(b, 0):
                    a, b = b, a
                splice(a, b, [a, b], [edge_id], when_blocked=False)
        if len(circuit.detour) >= 2:
            splice(circuit.detour[0], circuit.detour[-1], list(circuit.detour),
                   route_edges(g, circuit.detour), when_blocked=True)
        return vs, es

    def plan(self, circuit: Circuit, vertex: int, next_checkpoint: int, laps: int, racer=None) -> RoutePlan:
        g = circuit.graph
        lap_v, lap_e = self.lap(circuit)
        state, cp = [], 1                      # checkpoint a racer needs next after visiting lap_v[i]
        for v in lap_v:
            if g.vertex(v).type == CHECKPOINT and g.vertex(v).checkpoint_order == cp:
                cp += 1
            state.append(cp)
        cps = g.checkpoints()
        vertices, edges = [vertex], []
        for _ in range(laps):
            here = vertices[-1]
            at = [i for i, v in enumerate(lap_v) if v == here and state[i] == next_checkpoint]
            if at:                             # on the lap: follow it from here
                vertices += lap_v[at[0] + 1:]
                edges += lap_e[at[0]:]
            else:                              # off it: shortest way to the next mandatory vertex, then the lap
                target = cps[next_checkpoint - 1].id if next_checkpoint <= len(cps) else g.finish.id
                leg = dijkstra(g, here, target, distance_cost)
                if not leg.found:
                    plan = make_plan(g, vertices, edges, distance_cost, self.name)
                    plan.found, plan.failed_target = False, target
                    return plan
                j = len(lap_v) - 1 - lap_v[::-1].index(target)
                vertices += leg.path[1:] + lap_v[j + 1:]
                edges += leg.edge_path + lap_e[j:]
            next_checkpoint = 1
        return make_plan(g, vertices, edges, distance_cost, self.name)


class ShortcutRoute(FixedRoute):
    """Opponent 2: the main route with every designated shortcut that is open
    in place of the stretch it cuts off; falls back to the main route (and
    Opponent 1's detour) when a shortcut is closed."""
    name = "shortcut"
    use_shortcuts = True


class ShortestDistance(_Opponent):
    """Opponent 3: minimum total distance through the checkpoints (Dijkstra),
    recomputed whenever the track changes."""
    name = "shortest"

    def plan(self, circuit: Circuit, vertex: int, next_checkpoint: int, laps: int, racer=None) -> RoutePlan:
        return plan_route(circuit.graph, vertex, next_checkpoint, laps, distance_cost, "dijkstra")


class Autopilot:
    """The player's recommended line: A* under a weight preset, optional
    pickups from the knapsack planner, refuelling from the refuel DP."""
    name = "human"

    def __init__(self, preset: str = "Balanced", pickup_solver: str | None = "dp",
                 pickup_budget: float = config.PICKUP_DETOUR_BUDGET) -> None:
        self.preset = preset
        self.pickup_solver = pickup_solver     # "dp", "greedy" or None (no pickup detours)
        self.pickup_budget = pickup_budget     # seconds of detour accepted per plan
        self.last_picks = None                 # the latest PickupPlan: DP and greedy side by side, for the HUD

    def plan(self, circuit: Circuit, vertex: int, next_checkpoint: int, laps: int, racer=None) -> RoutePlan:
        g = circuit.graph
        plan = plan_route(g, vertex, next_checkpoint, laps, self.preset, "astar")
        if plan.found and racer is not None and self.pickup_solver:
            picks = pickup_plan(g, vertex, plan.edges, racer.fuel, racer.nitro_charges,
                                self.pickup_budget, self.pickup_solver)
            self.last_picks = picks
            if picks.edges != plan.edges:
                plan = make_plan(g, walk(g, vertex, picks.edges), picks.edges, self.preset,
                                 "astar", plan.targets, plan.legs)
        return plan

    def refuel_amount(self, graph: TrackGraph, vertex: int, route: list[int], fuel: float) -> int:
        """First purchase of the refuel DP run with the safety margin held
        back; a fill-up when even the DP sees no feasible plan."""
        advice = refuel_plan(graph, vertex, route, max(0.0, fuel - config.REFUEL_SAFETY_MARGIN), True)
        return min(advice.buy_now, fill_amount(fuel)) if advice.result.feasible else fill_amount(fuel)


STRATEGIES = {"human": Autopilot, "fixed": FixedRoute, "shortcut": ShortcutRoute,
              "shortest": ShortestDistance}

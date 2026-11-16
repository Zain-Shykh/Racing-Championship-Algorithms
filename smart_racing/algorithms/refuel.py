"""Refuelling DP for a fixed route (Project.md 5.3 Problem B, SPEC 4.2)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, NamedTuple, Sequence

from smart_racing import config

Observer = Callable[[dict], None]


@dataclass
class RefuelResult:
    feasible: bool = False
    purchases: list[int] = field(default_factory=list)       # whole fuel units bought at each stop
    arrival_fuel: list[float] = field(default_factory=list)  # DP fuel on arrival at stops 0..m (a lower bound)
    stops_made: int = 0
    total_stop_time: float = 0.0
    total_purchased: int = 0
    final_fuel: float = 0.0        # DP fuel at the destination (a lower bound)
    reason: str = ""               # why the plan is infeasible
    failed_leg: int | None = None  # first leg that no reachable state can cover
    states: int = 0                # reachable (stop, fuel) states expanded
    transitions: int = 0           # purchase options evaluated


class ReplayResult(NamedTuple):
    feasible: bool
    total_stop_time: float
    final_fuel: float
    reason: str


def plan_refuel(demands: Sequence[float], available: Sequence[bool],
                start_fuel: float = config.TANK_CAPACITY,
                capacity: float = config.TANK_CAPACITY,
                max_purchase: int = config.STATION_MAX_PURCHASE,
                stop_time: float = config.REFUEL_STOP_TIME,
                scale: int = config.FUEL_SCALE,
                observer: Observer | None = None) -> RefuelResult:
    """Minimum total stop time to drive a fixed route.

    The route has stops `0..m-1` followed by the destination `m`.
    `demands[j]` is the fuel for the leg from stop `j` to stop `j+1`;
    `available[j]` says whether fuel can be bought at stop `j` (False for a
    closed station or a stop that is not a station, such as the racer's
    current vertex). Nothing is bought at the destination.

    Discretization: fuel is counted in `1/scale` units. Demands are rounded
    up, starting fuel and capacity down, purchases are whole fuel units, so the
    DP never has more fuel than the real car and its plan is always feasible.

    State: `dp[j][f]` = minimum stop time to arrive at stop `j` with `f`
    discrete units. Base case `dp[0][start] = 0`, everything else unreachable.
    Transition at stop `j`: buy `a` whole units, `0 <= a <= min(max_purchase,
    room in the tank)` (only `a = 0` when unavailable); if `f + a >= d_j` then
    `dp[j+1][f + a - d_j] = min(.., dp[j][f] + (stop_time if a > 0 else 0))`.
    Unreachable states are skipped. Answer: the destination state with the
    least stop time, ties broken by the most remaining fuel (a stop costs the
    same whatever is bought); the purchases are traced back through the table.
    If no state can cover some leg the result is infeasible and names that leg.

    Time O(m * F * P) with F = capacity * scale + 1 fuel states and
    P = max_purchase + 1 options (the brief's O(m * C^2)); space O(m * F).
    """
    m = len(demands)
    if len(available) != m:
        raise ValueError("demands and available must have the same length")
    if min(demands, default=0) < 0:
        raise ValueError("fuel demands must be non-negative")
    if not 0 <= start_fuel <= capacity:
        raise ValueError(f"start fuel {start_fuel} is outside 0..{capacity}")
    # round(.., 6) removes float noise such as 0.7 * 10 = 7.000000000000001
    cap = math.floor(round(capacity * scale, 6))
    need = [math.ceil(round(d * scale, 6)) for d in demands]
    start = math.floor(round(start_fuel * scale, 6))

    inf = math.inf
    dp = [[inf] * (cap + 1) for _ in range(m + 1)]
    bought = [[0] * (cap + 1) for _ in range(m + 1)]   # units bought at stop j-1 on the best way into dp[j][f]
    dp[0][start] = 0.0
    res = RefuelResult()
    for j in range(m):
        reached, most = False, 0
        for f in range(cap + 1):
            t = dp[j][f]
            if t == inf:
                continue
            res.states += 1
            top = min(max_purchase, (cap - f) // scale) if available[j] else 0
            most = max(most, f + top * scale)
            for a in range(top + 1):
                res.transitions += 1
                g = f + a * scale - need[j]
                if g < 0:
                    continue
                reached = True
                new = t + (stop_time if a else 0.0)
                if new < dp[j + 1][g]:
                    dp[j + 1][g] = new
                    bought[j + 1][g] = a
                    if observer:
                        observer({"type": "transition", "stop": j, "fuel": f / scale, "buy": a,
                                  "next_fuel": g / scale, "stop_time": new})
        if observer:
            observer({"type": "stop", "stop": j, "available": bool(available[j]),
                      "demand": need[j] / scale, "feasible": reached})
        if not reached:
            res.failed_leg = j
            res.reason = (f"leg {j} needs {need[j] / scale:g} fuel but at most {most / scale:g} "
                          f"can be on board at stop {j}"
                          + ("" if available[j] else " (no fuel available there)"))
            if observer:
                observer({"type": "done", "feasible": False, "reason": res.reason})
            return res

    best = 0
    for f in range(cap + 1):
        if dp[m][f] != inf:
            res.states += 1
            if dp[m][f] <= dp[m][best]:      # ascending scan, so ties end on the most fuel
                best = f
    res.feasible = True
    res.total_stop_time = dp[m][best]
    res.final_fuel = best / scale
    res.purchases = [0] * m
    res.arrival_fuel = [0.0] * (m + 1)
    f = best
    for j in range(m, 0, -1):
        res.arrival_fuel[j] = f / scale
        a = bought[j][f]
        res.purchases[j - 1] = a
        f = f - a * scale + need[j - 1]
        if observer:
            observer({"type": "trace", "stop": j - 1, "buy": a, "fuel": f / scale})
    res.arrival_fuel[0] = f / scale
    res.stops_made = sum(1 for a in res.purchases if a)
    res.total_purchased = sum(res.purchases)
    if observer:
        observer({"type": "done", "feasible": True, "purchases": res.purchases,
                  "stop_time": res.total_stop_time, "final_fuel": res.final_fuel})
    return res


def replay_plan(demands: Sequence[float], available: Sequence[bool], purchases: Sequence[int],
                start_fuel: float = config.TANK_CAPACITY,
                capacity: float = config.TANK_CAPACITY,
                max_purchase: int = config.STATION_MAX_PURCHASE,
                stop_time: float = config.REFUEL_STOP_TIME) -> ReplayResult:
    """Drive the route with real (unrounded) fuel under the game rules and check a plan.

    Rules checked: one purchase per stop, each a whole number in
    `0..max_purchase`, positive only at an available stop, the tank is capped
    at `capacity` (SPEC 4.2), and every leg starts with enough fuel. O(m).
    """
    if not len(demands) == len(available) == len(purchases):
        return ReplayResult(False, 0.0, start_fuel, "plan length does not match the route")
    fuel, time = start_fuel, 0.0
    for j, (demand, open_, buy) in enumerate(zip(demands, available, purchases)):
        if buy != int(buy) or not 0 <= buy <= max_purchase:
            return ReplayResult(False, time, fuel, f"stop {j}: purchase {buy} is not in 0..{max_purchase}")
        if buy and not open_:
            return ReplayResult(False, time, fuel, f"stop {j}: no fuel available")
        if buy:
            fuel = min(capacity, fuel + buy)
            time += stop_time
        if fuel < demand:
            return ReplayResult(False, time, fuel, f"leg {j}: needs {demand:g}, has {fuel:g}")
        fuel -= demand
    return ReplayResult(True, time, fuel, "")

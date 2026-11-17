"""Phase 4: checkpoint-aware routing and the resource planner."""
import math

import pytest

from smart_racing import config as C
from smart_racing.algorithms.refuel import replay_plan
from smart_racing.core.cost import distance_cost, make_cost_fn, route_summary
from smart_racing.core.graph import NITRO_PICKUP
from smart_racing.engine.resources import fuel_to_next_station, pickup_plan, refuel_plan
from smart_racing.engine.routing import (compare_presets, nearest_station, plan_route, plan_through,
                                         race_targets, route_affected, walk)
from smart_racing.tracks.loader import load_builtin


def in_order(sequence, wanted):
    it = iter(sequence)
    return all(w in it for w in wanted)


@pytest.mark.parametrize("name", C.BUILTIN_CIRCUITS)
def test_route_visits_every_checkpoint_in_order(name):
    g = load_builtin(name).graph
    targets = race_targets(g, 1, 2)
    assert len(targets) == 2 * (len(g.checkpoints()) + 1)
    plans = [plan_route(g, g.start.id, 1, 2, "Balanced", algo) for algo in ("dijkstra", "astar")]
    for plan in plans:
        assert plan.found and plan.vertices[0] == g.start.id and plan.vertices[-1] == g.finish.id
        assert in_order(plan.vertices, targets)
        assert walk(g, g.start.id, plan.edges) == plan.vertices
        assert plan.summary == route_summary(g, plan.edges, make_cost_fn("Balanced"))
        assert plan.expanded > 0 and plan.heap_ops > 0 and len(plan.legs) == len(targets)
    assert plans[0].cost == pytest.approx(plans[1].cost)


def test_plan_from_checkpoint_progress():
    g = load_builtin("harbor_eight").graph
    cps = g.checkpoints()
    plan = plan_route(g, cps[3].id, 5, 1)          # standing on checkpoint 4, needs 5
    assert plan.targets == [cp.id for cp in cps[4:]] + [g.finish.id]
    assert in_order(plan.vertices, plan.targets)
    # a direct route to the finish would be shorter: the planner must not take it
    direct = plan_through(g, cps[3].id, [g.finish.id], distance_cost, "dijkstra")
    assert direct.distance < plan_route(g, cps[3].id, 5, 1, distance_cost, "dijkstra").distance


def test_replan_after_block_and_unreachable_target():
    g = load_builtin("harbor_eight").graph
    before = plan_route(g, g.start.id)
    blocked = before.edges[6]
    g.block_edge(blocked)
    assert route_affected(before.edges, [blocked]) and not route_affected(before.edges, [10**6])
    after = plan_route(g, g.start.id)
    assert after.found and blocked not in after.edges and after.cost >= before.cost
    for edge, _ in list(g.neighbors(g.start.id)):
        g.block_edge(edge.id)
    stuck = plan_route(g, g.start.id)
    assert not stuck.found and stuck.failed_target == g.checkpoints()[0].id and stuck.edges == []


def test_presets_give_different_routes_with_summaries():
    g = load_builtin("harbor_eight").graph
    plans = compare_presets(g, g.start.id, 1, 1)
    assert set(plans) == set(C.COST_PRESETS) and all(p.found for p in plans.values())
    assert plans["Speed"].edges != plans["Economy"].edges
    assert plans["Speed"].time < plans["Economy"].time and plans["Economy"].fuel < plans["Speed"].fuel


def test_nearest_station_respects_fuel_and_availability():
    g = load_builtin("harbor_eight").graph
    plan = nearest_station(g, g.start.id, 100.0)
    assert plan.vertices[-1] == 5 and plan.fuel <= 100.0
    assert nearest_station(g, g.start.id, plan.fuel - 0.01) is None      # out of range
    g.set_vertex_active(5, False)
    assert nearest_station(g, g.start.id, 100.0).vertices[-1] == 11
    assert nearest_station(g, g.start.id, 100.0, include_closed=True).vertices[-1] == 5
    assert nearest_station(g, 11, 100.0) is None                          # the current vertex does not count


def test_refuel_plan_matches_engine_rules():
    g = load_builtin("serpent_pass").graph
    route = plan_route(g, g.start.id, 1, 2).edges
    advice = refuel_plan(g, g.start.id, route, C.TANK_CAPACITY)
    assert advice.result.feasible and advice.buy_now == 0 and advice.purchases
    assert all(0 < units <= C.STATION_MAX_PURCHASE for _, units in advice.purchases)
    assert replay_plan(advice.demands, advice.available, advice.result.purchases).feasible
    need, station = fuel_to_next_station(g, g.start.id, route)
    assert station == advice.stops[1] and need == pytest.approx(advice.demands[0])
    # full tank on a short route: nothing to buy
    one_lap = plan_route(g, g.start.id).edges
    assert refuel_plan(g, g.start.id, one_lap, C.TANK_CAPACITY).purchases == []
    # insufficient fuel and every station closed: infeasible, and nothing is recommended
    for v in (5, 22):
        g.set_vertex_active(v, False)
    stuck = refuel_plan(g, g.start.id, route, C.TANK_CAPACITY)
    assert not stuck.result.feasible and stuck.buy_now == 0 and stuck.purchases == []
    assert fuel_to_next_station(g, g.start.id, route)[1] is None


def test_pickup_plan_items_and_feasibility():
    g = load_builtin("grand_ring").graph
    route = plan_route(g, g.start.id, 1, 2).edges
    plan = pickup_plan(g, g.start.id, route, C.TANK_CAPACITY, 1)
    by_vertex = {o.vertex: o for o in plan.options}
    assert by_vertex[10].item.cost == 0 and by_vertex[10].loop_edges == []   # zero-cost pickup on the route
    assert 10 in plan.dp.selected and 10 in plan.recommended and plan.feasible
    assert 24 not in by_vertex                                              # inactive booster is never offered
    assert all(g.vertex(o.vertex).active for o in plan.options)
    assert plan.dp.total_cost <= plan.budget and plan.greedy.total_cost <= plan.budget
    assert pickup_plan(g, g.start.id, route, C.TANK_CAPACITY, C.NITRO_MAX_CHARGES).options == []  # no free slot
    # only one free slot: one nitro item at most, the cheapest
    assert [o.vertex for o in pickup_plan(g, g.start.id, route, 100.0, 2, 60.0).options] == [10]
    # a pickup cut off from the track is unreachable and not offered
    for edge, _ in list(g.incident(22)):
        g.block_edge(edge.id)
    assert 22 not in [o.vertex for o in pickup_plan(g, g.start.id, route, 100.0, 1, 60.0).options]


def test_pickup_detour_is_spliced_and_dp_is_not_worse_than_greedy():
    g = load_builtin("harbor_eight").graph
    route = plan_route(g, g.start.id, 1, 2).edges
    plan = pickup_plan(g, g.start.id, route, C.TANK_CAPACITY, 1, 30.0)
    assert plan.dp.total_benefit >= plan.greedy.total_benefit
    assert plan.recommended and plan.feasible and len(plan.edges) > len(route)
    visited = walk(g, g.start.id, plan.edges)
    assert all(v in visited for v in plan.recommended)
    assert visited[-1] == g.finish.id and in_order(visited, race_targets(g, 1, 2))
    assert replay_plan(plan.refuel.demands, plan.refuel.available, plan.refuel.result.purchases).feasible
    for option in plan.options:
        assert option.item.cost == math.ceil(round(option.extra_time * C.PICKUP_COST_SCALE, 6))
        assert g.vertex(option.vertex).type == NITRO_PICKUP and option.item.benefit == C.PICKUP_NITRO_BENEFIT


def test_pickup_plan_never_recommends_what_fuel_cannot_cover():
    g = load_builtin("harbor_eight").graph
    for v in (5, 11):
        g.set_vertex_active(v, False)                  # no fuel on sale anywhere
    lap = plan_route(g, g.start.id, 1, 1, "Economy").edges
    need = sum(g.edge(e).effective_fuel for e in lap)
    plan = pickup_plan(g, g.start.id, lap, need + 1.0, 1, 30.0)   # enough for the lap, not for a loop
    assert plan.dp.selected and plan.recommended == [] and plan.dropped and plan.feasible
    assert plan.edges == lap
    short = pickup_plan(g, g.start.id, lap, need - 5.0, 1, 30.0)  # not even the route itself
    assert not short.feasible and short.recommended == []


def test_autopilot_honours_the_pickup_solver_and_keeps_both_results():
    from smart_racing.engine.opponents import Autopilot
    from smart_racing.engine.race import create_race
    for solver in ("dp", "greedy"):
        engine = create_race("grand_ring", pickup_solver=solver)
        pilot = engine.human.strategy
        pilot.plan(engine.circuit, engine.circuit.graph.start.id, 1, 1, engine.human)
        assert isinstance(pilot, Autopilot) and pilot.pickup_solver == solver
        assert pilot.last_picks.dp.total_benefit >= pilot.last_picks.greedy.total_benefit
    assert create_race("grand_ring", pickup_solver=None).human.strategy.last_picks is None

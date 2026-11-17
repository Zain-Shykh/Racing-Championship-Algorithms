"""Phase 4 integration: the headless race engine, player input and opponents."""
import math

import pytest

from smart_racing import config as C
from smart_racing.core.cost import distance_cost
from smart_racing.core.graph import CHECKPOINT, FINISH, START, TrackGraph
from smart_racing.engine.race import (DNF, FINISHED, RACING, REFUELLING, WAITING, RacerSpec,
                                      create_race, default_racers)
from smart_racing.engine.routing import plan_route, walk
from smart_racing.tracks.loader import Circuit, load_builtin, route_edges

SOLO = [RacerSpec("P", "human", True)]


def tiny_circuit(fuel=5.0):
    """Start 0 - cp1 1 - cp2 2 - Finish 3, one-way 3 -> 0, and a bypass 0 - 2 that skips cp1."""
    g = TrackGraph()
    for i, kind in enumerate((START, CHECKPOINT, CHECKPOINT, FINISH)):
        g.add_vertex(i, 100.0 * i, 0.0, kind, i if kind == CHECKPOINT else None)
    for i, (u, v) in enumerate(((0, 1), (1, 2), (2, 3))):
        g.add_edge(i, u, v, 100.0, 10.0, fuel)
    g.add_edge(3, 3, 0, 100.0, 10.0, fuel, directed=True)
    g.add_edge(4, 0, 2, 100.0, 10.0, fuel)
    return Circuit("Tiny", g, [0, 1, 2, 3])


def snapshot(engine):
    return ([(r.id, r.status, r.finish_time, r.fuel, r.lap_times, r.driven) for r in engine.racers],
            engine.log, engine.feed, engine.clock)


def run_until(engine, condition, limit=400.0):
    while not condition() and not engine.finished and engine.clock < limit:
        engine.step()
    assert condition()


@pytest.mark.parametrize("name", C.BUILTIN_CIRCUITS)
def test_complete_two_lap_race_on_every_circuit(name):
    engine = create_race(name).run_to_completion()
    cps = len(engine.graph.checkpoints())
    assert engine.finished and len(engine.racers) == 4
    for r in engine.racers:
        assert r.status == FINISHED and r.lap == 2 and len(r.lap_times) == 2
        assert sum(r.lap_times) == pytest.approx(r.finish_time)
        assert 90.0 <= r.finish_time <= 240.0                  # 1.5 to 4 simulated minutes
        assert 0.0 <= r.fuel <= C.TANK_CAPACITY and 0 <= r.nitro_charges <= C.NITRO_MAX_CHARGES
        passed = [e for e in engine.log if e.racer_id == r.id and e.kind == "checkpoint"]
        assert len(passed) == 2 * cps
        # every road driven was joined to the previous one: cars stay on graph edges
        assert walk(engine.graph, engine.graph.start.id, r.driven)[-1] == engine.graph.finish.id
    times = [r.finish_time for r in engine.racers if not r.is_human]
    assert len(set(times)) == 3 and max(times) - min(times) > 5.0   # opponents are visibly apart
    order = engine.classification()
    assert [r.finish_time for r in order] == sorted(r.finish_time for r in engine.racers)
    assert len(engine.feed) >= len(engine.circuit.events)


def test_identical_inputs_give_identical_results():
    a = create_race("grand_ring").run_to_completion()
    b = create_race("grand_ring").run_to_completion()
    assert snapshot(a) == snapshot(b)
    c = create_race("grand_ring")                # the GUI path: frame times into the accumulator
    while not c.finished:
        c.update(0.016)
    assert snapshot(c) == snapshot(a)


def test_skipping_a_checkpoint_does_not_complete_the_lap():
    engine = create_race(tiny_circuit(), laps=1, racers=SOLO, autopilot=False)
    p = engine.racer(0)
    assert {c.edge_id for c in engine.legal_choices(0)} == {0, 4}
    assert [c.edge_id for c in engine.legal_choices(0) if c.recommended] == [0]
    assert not engine.choose_edge(0, 3) and not engine.choose_edge(0, 99)   # wrong way / unknown
    assert engine.choose_edge(0, 4)                                         # bypass checkpoint 1
    run_until(engine, lambda: p.to_vertex == 2)
    assert engine.choose_edge(0, 2)                                         # queued for vertex 2
    run_until(engine, lambda: p.current_vertex == 3 and p.edge_id is None)
    assert p.lap == 0 and p.next_checkpoint == 1 and p.status != FINISHED   # passing cp2 early counted nothing
    assert not [e for e in engine.log if e.kind in ("lap", "checkpoint")]
    engine.set_autopilot(0, True)                                           # go back and do it properly
    engine.run_to_completion()
    assert p.status == FINISHED and p.driven == [4, 2, 3, 0, 1, 2]
    assert [e.kind for e in engine.log if e.kind in ("checkpoint", "lap")] == ["checkpoint", "checkpoint", "lap"]


def test_manual_player_without_input_takes_the_recommended_road_after_the_grace_period():
    engine = create_race(tiny_circuit(), laps=1, racers=SOLO, autopilot=False)
    p = engine.racer(0)
    run_until(engine, lambda: p.edge_id is not None)
    assert engine.clock == pytest.approx(C.PLAYER_CHOICE_GRACE, abs=2 * C.SIM_DT) and p.driven == [0]
    engine.run_to_completion()
    # vertices 0, 1 and 2 each offer two or more legal roads; nowhere else is there a choice
    assert p.status == FINISHED and p.finish_time == pytest.approx(30.0 + 3 * C.PLAYER_CHOICE_GRACE)


def test_nitro_speed_fuel_and_limits():
    engine = create_race(tiny_circuit(), laps=1, racers=SOLO, autopilot=False)
    p = engine.racer(0)
    engine.choose_edge(0, 0)
    engine.step()
    assert engine.fire_nitro(0) and p.nitro_active and p.nitro_charges == 0
    assert not engine.fire_nitro(0)                       # no charge left
    run_until(engine, lambda: not p.nitro_active)
    # 4 s at 1.5x on a 10 s road costing 5 fuel: 60% covered at double fuel use
    assert p.progress == pytest.approx(0.05 / 10 + 0.6, abs=1e-6)
    assert C.TANK_CAPACITY - p.fuel == pytest.approx(5.0 * 0.005 + 2 * 5.0 * 0.6, abs=1e-6)
    assert engine.xy(0) == pytest.approx((100.0 * p.progress, 0.0))
    assert p.position == ("edge", 0, p.progress, 0, 1)


def test_nitro_cuts_out_instead_of_stranding_the_car():
    # a 70-unit road: with the boost on for its full 4 s the tank would run dry before the end
    engine = create_race(tiny_circuit(fuel=70.0), laps=1, racers=SOLO, autopilot=False)
    p = engine.racer(0)
    engine.choose_edge(0, 0)
    engine.step()
    assert engine.fire_nitro(0)
    run_until(engine, lambda: p.current_vertex == 1 and p.edge_id is None)
    assert 0.0 <= p.fuel < 1.5 and any("cut out" in e.text for e in engine.log)
    assert p.nitro_left == 0.0
    engine.run_to_completion()                            # nearly empty, the next road needs 70
    assert p.status == DNF and p.wait_reason == "out of fuel" and p.fuel >= 0.0


def test_player_refuels_by_choice_at_an_active_station():
    engine = create_race("harbor_eight", racers=SOLO, autopilot=False, events=[])
    p = engine.racer(0)
    assert engine.station_offer(0) is None and not engine.refuel(0, 10)     # not at a station
    run_until(engine, lambda: p.to_vertex == 4)
    assert engine.choose_edge(0, 4)                                          # road 4 leads to station 5
    run_until(engine, lambda: p.current_vertex == 5 and p.edge_id is None)
    most, recommended = engine.station_offer(0)
    assert most == math.floor(C.TANK_CAPACITY - p.fuel) and 0 <= recommended <= most
    before = p.fuel
    assert not engine.refuel(0, 0) and not engine.refuel(0, C.STATION_MAX_PURCHASE + 1)
    assert engine.refuel(0, 5) and p.fuel == pytest.approx(before + 5) and p.status == REFUELLING
    assert not engine.refuel(0, 5)                                           # still in the stop
    start = engine.clock
    run_until(engine, lambda: p.status != REFUELLING)
    assert engine.clock - start == pytest.approx(C.REFUEL_STOP_TIME, abs=C.SIM_DT)
    assert engine.refuel(0, 40) and p.fuel == C.TANK_CAPACITY                # capped by the tank
    assert p.fuel_stops == 2 and p.fuel_bought == pytest.approx(C.TANK_CAPACITY - before)
    engine.graph.set_vertex_active(5, False)
    run_until(engine, lambda: p.status != REFUELLING)
    assert engine.station_offer(0) is None and not engine.refuel(0, 1)       # station out of service


def test_road_closure_mid_race_reroutes_without_restart():
    block = [{"time": 5, "type": C.EVENT_ROAD_BLOCK, "target": 6}]          # main route, never cleared
    engine = create_race("harbor_eight", events=block).run_to_completion()
    assert engine.feed[0].text == "Road blocked: road 6 (6-7)" and engine.feed[0].time == 5.0
    assert all(r.status == FINISHED for r in engine.racers)
    detour = route_edges(engine.graph, engine.circuit.detour)
    for r in engine.racers:
        assert 6 not in r.driven
        assert r.reroutes >= 1 and any(e.kind == "reroute" and e.racer_id == r.id for e in engine.log)
    fixed = engine.racer(1)
    assert all(e in fixed.driven for e in detour)        # Opponent 1 took its documented detour


def test_closure_of_every_route_makes_racers_wait_then_dnf():
    def blocks(extra):
        circuit = load_builtin("harbor_eight")
        return circuit, 2, "Balanced", None, [{"time": 10, "type": C.EVENT_ROAD_BLOCK, "target": e.id}
                         for e in circuit.graph.edges()] + extra
    # a far-off pending event: everybody waits the full 60 s, then is out
    engine = create_race(*blocks([{"time": 800, "type": C.EVENT_NITRO_SPAWN, "target": 27}]))
    run_until(engine, lambda: all(r.status == WAITING for r in engine.racers), limit=30.0)
    engine.run_to_completion()
    assert engine.finished and engine.clock < 100.0
    for r in engine.racers:
        assert r.status == DNF and r.finish_time is None and r.wait_reason == "no open route"
        assert r.waited == pytest.approx(C.DNF_WAIT_TIME, abs=C.SIM_DT)
        assert r.end_time == pytest.approx(r.total_time)
    assert [e.kind for e in engine.log].count("dnf") == 4
    # nothing pending that could help: DNF at once
    engine = create_race(*blocks([])).run_to_completion()
    assert all(r.status == DNF and r.waited <= C.SIM_DT for r in engine.racers) and engine.clock < 30.0


def test_running_out_of_fuel_is_dnf_and_ranked_by_progress():
    closed = [{"time": 0, "type": C.EVENT_STATION_OUTAGE, "target": v, "duration": math.inf} for v in (5, 22)]
    engine = create_race("serpent_pass", events=closed).run_to_completion()
    assert all(r.status == DNF and r.fuel_stops == 0 for r in engine.racers)
    assert all(r.wait_reason in ("out of fuel", "fuel station closed") for r in engine.racers)
    order = engine.classification()
    keys = [(-r.lap, -r.checkpoints_done, r.end_time, r.id) for r in order]
    assert keys == sorted(keys) and all(r.lap >= 1 for r in order)


def test_time_limit_ends_the_race_for_everyone():
    engine = create_race("grand_ring", time_limit=50.0).run_to_completion()
    assert engine.finished and engine.clock == pytest.approx(50.0)
    assert all(r.status == RACING and r.finish_time is None and r.end_time == engine.clock
               for r in engine.racers)
    engine.step()
    assert engine.clock == pytest.approx(50.0)           # a finished race no longer advances


def test_pickup_goes_through_the_event_queue_and_respawns():
    engine = create_race("grand_ring", events=[]).run_to_completion()    # pickup 10 is on the main route
    taken = [e for e in engine.log if e.kind == "pickup"]
    assert taken and "vertex 10" in taken[0].text
    respawns = [e for e in engine.feed if e.kind == C.EVENT_NITRO_SPAWN]
    assert respawns and respawns[0].time >= taken[0].time + C.NITRO_RESPAWN_TIME - C.SIM_DT
    assert sum(r.nitro_used for r in engine.racers) > len(engine.racers) - 1   # collected charges get used


# --- opponents ----------------------------------------------------------------
def lap_vertices(engine, racer):
    return walk(engine.graph, engine.graph.start.id, racer.driven)


def test_opponent_1_follows_the_fixed_main_route():
    engine = create_race("harbor_eight", events=[]).run_to_completion()
    main = engine.circuit.main_route
    assert lap_vertices(engine, engine.racer(1)) == main + main


def test_opponent_2_takes_open_shortcuts_and_falls_back_when_closed():
    engine = create_race("harbor_eight", events=[]).run_to_completion()
    shortcuts = engine.circuit.opponent_shortcuts
    assert all(engine.racer(2).driven.count(s) == 2 for s in shortcuts)
    assert not any(s in engine.racer(1).driven for s in shortcuts)
    closed = [{"time": 0, "type": C.EVENT_SHORTCUT_CLOSE, "target": s} for s in shortcuts]
    engine = create_race("harbor_eight", events=closed).run_to_completion()
    main = engine.circuit.main_route
    assert lap_vertices(engine, engine.racer(2)) == main + main
    # closed during lap 1 only: back on the shortcut in lap 2
    script = [{"time": 0, "type": C.EVENT_SHORTCUT_CLOSE, "target": shortcuts[0]},
              {"time": 60, "type": C.EVENT_SHORTCUT_OPEN, "target": shortcuts[0]}]
    engine = create_race("harbor_eight", events=script).run_to_completion()
    assert engine.racer(2).driven.count(shortcuts[0]) == 1


def test_opponent_3_drives_the_minimum_distance_route():
    engine = create_race("grand_ring", events=[]).run_to_completion()
    g = load_builtin("grand_ring").graph
    best = plan_route(g, g.start.id, 1, 2, distance_cost, "dijkstra")
    shortest = engine.racer(3)
    assert shortest.driven == best.edges and shortest.distance == pytest.approx(best.distance)
    assert all(r.distance >= shortest.distance - 1e-6 for r in engine.racers)
    assert engine.racer(1).distance > shortest.distance


def test_opponents_refuel_at_an_eligible_station_and_use_nitro():
    engine = create_race("serpent_pass", events=[]).run_to_completion()
    for r in engine.racers[1:]:
        assert r.status == FINISHED and r.fuel_stops >= 1 and r.fuel_bought <= r.fuel_stops * C.STATION_MAX_PURCHASE
    assert any(r.nitro_used for r in engine.racers[1:])


def test_up_to_ten_racers_and_live_order():
    with pytest.raises(ValueError):
        default_racers(C.MAX_RACERS)
    engine = create_race("grand_ring", racers=default_racers(C.MAX_RACERS - 1))
    assert len(engine.racers) == C.MAX_RACERS
    assert [r.strategy_type for r in engine.racers[1:7]] == list(C.OPPONENT_STRATEGIES) * 2
    for stop in (0.0, 40.0, 120.0, 1000.0):
        run_until(engine, lambda: engine.clock >= stop or engine.finished)
        order = engine.running_order()
        for k in (1, 3, C.MAX_RACERS):
            top = engine.live_top_k(k)
            assert top.items == order[:k] and top.heap_ops > 0
        assert [engine.race_position(r.id) for r in order] == list(range(1, C.MAX_RACERS + 1))
    assert engine.finished and all(r.status == FINISHED for r in engine.racers)


@pytest.mark.parametrize("solver", ["dp", "greedy"])
@pytest.mark.parametrize("name", C.BUILTIN_CIRCUITS)
def test_recommended_pickup_and_refuel_plan_is_feasible_in_the_engine(name, solver):
    """Project.md 5.3: the planner's recommendations replay in the engine without a fuel failure."""
    engine = create_race(name, pickup_solver=solver).run_to_completion()
    me = engine.human
    assert me.status == FINISHED and me.fuel >= 0.0
    assert walk(engine.graph, engine.graph.start.id, me.driven)[-1] == engine.graph.finish.id
    assert not [e for e in engine.log if e.racer_id == me.id and e.kind == "dnf"]


def test_simultaneous_events_apply_in_heap_order_then_one_replan_per_racer():
    script = [{"time": 5, "type": C.EVENT_OIL_SPILL, "target": 3},
              {"time": 5, "type": C.EVENT_ROAD_BLOCK, "target": 6}]       # listed first, but priority 3 vs 1
    engine = create_race("harbor_eight", events=script)
    while engine.clock < 6.0:
        engine.step()
    at_five = [f.text for f in engine.feed if f.time == 5.0]
    assert at_five[0].startswith("Road blocked") and "il" in at_five[1]
    for r in engine.racers:
        assert len([e for e in engine.log if e.kind == "reroute" and e.racer_id == r.id and e.time == 5.0]) <= 1

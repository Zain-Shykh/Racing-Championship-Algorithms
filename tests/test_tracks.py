"""The three built-in circuits, the loader and the validator."""
import copy

import pytest

from smart_racing import config as C
from smart_racing.algorithms.dfs import dead_ends, find_cycle
from smart_racing.core.cost import make_cost_fn
from smart_racing.core.graph import DEAD_END, FUEL_STATION, NITRO_PICKUP, TrackGraph
from smart_racing.engine.events import EventQueue
from smart_racing.tracks.loader import (circuit_from_dict, circuit_to_dict, list_circuits,
                                        load_builtin, load_circuit, route_edges, save_circuit)
from smart_racing.tracks.validator import (checkpoint_route, fuel_cost, fuel_plan, validate,
                                           validate_circuit)

CIRCUITS = list_circuits()


def test_three_builtin_circuits_in_championship_order():
    assert CIRCUITS == list(C.BUILTIN_CIRCUITS) and len(CIRCUITS) == 3
    assert len({load_builtin(name).name for name in CIRCUITS}) == 3
    with pytest.raises(ValueError):
        load_builtin("nowhere")


@pytest.mark.parametrize("name", CIRCUITS)
def test_circuit_passes_validator_and_meets_minimums(name):
    circuit = load_builtin(name)
    g = circuit.graph
    result = validate_circuit(circuit)                      # default thresholds
    assert result.ok and result.failures == []
    assert g.start is not None and g.finish is not None
    assert [cp.checkpoint_order for cp in g.checkpoints()] == list(range(1, len(g.checkpoints()) + 1))
    assert len(g.checkpoints()) >= 10
    assert sum(e.is_shortcut for e in g.edges()) >= 2
    assert len(g.vertices_of_type(FUEL_STATION)) >= 2 and len(g.vertices_of_type(NITRO_PICKUP)) >= 2
    assert sum(e.directed for e in g.edges()) >= 1
    assert len({e.difficulty for e in g.edges()}) >= 3
    assert find_cycle(g).has_cycle
    reported = dead_ends(g).dead_ends
    assert any(g.vertex(v).type == DEAD_END for v in reported)
    # the A* heuristic needs road length >= straight-line length
    assert all(e.distance >= g.straight_line(e.src, e.dst) for e in g.edges())
    assert all(0 <= v.x <= 1000 and 0 <= v.y <= 700 for v in g.vertices())


@pytest.mark.parametrize("name", CIRCUITS)
def test_circuit_race_data(name):
    circuit = load_builtin(name)
    g = circuit.graph
    main = route_edges(g, circuit.main_route)
    assert circuit.main_route[0] == g.start.id and circuit.main_route[-1] == g.finish.id
    assert [v for v in circuit.main_route if g.vertex(v).type == "Checkpoint"] == [cp.id for cp in g.checkpoints()]
    assert len(circuit.detour) >= 3 and len(circuit.opponent_shortcuts) >= 1
    blocked = [e["target"] for e in circuit.events if e["type"] == C.EVENT_ROAD_BLOCK]
    assert set(blocked) & set(main)                         # a scripted blockage forces a reroute
    assert {e["type"] for e in circuit.events} == set(C.EVENT_PRIORITY)
    # the whole script is valid: nothing is rejected, and every temporary effect is restored
    queue = EventQueue(g)
    queue.load_script(circuit.events)
    assert len(queue.pop_due(1000.0)) > len(circuit.events) and queue.rejected == []
    assert all(e.effects == {} for e in g.edges())
    assert all(v.active for v in g.vertices_of_type(FUEL_STATION))


def test_two_lap_race_is_always_feasible_and_needs_fuel_somewhere():
    bought = {}
    for name in CIRCUITS:
        g = load_builtin(name).graph
        plan = fuel_plan(g, *checkpoint_route(g, fuel_cost, C.LAPS_PER_RACE))
        assert plan.feasible
        bought[name] = plan.total_purchased
    assert bought["grand_ring"] > 0 and bought["serpent_pass"] > 0


def test_presets_choose_different_routes():
    different = 0
    for name in CIRCUITS:
        g = load_builtin(name).graph
        routes = {preset: checkpoint_route(g, make_cost_fn(preset))[1] for preset in C.COST_PRESETS}
        different += routes["Speed"] != routes["Economy"]
        if name == "grand_ring":
            assert len({tuple(r) for r in routes.values()}) >= 3
    assert different >= 1


def test_save_load_round_trip(tmp_path):
    circuit = load_builtin("serpent_pass")
    save_circuit(circuit, tmp_path / "copy.json")
    again = load_circuit(tmp_path / "copy.json")
    assert circuit_to_dict(again) == circuit_to_dict(circuit)
    assert not again.graph.vertex(29).active and again.graph.edge(22).directed


def test_route_edges_respects_one_way_roads():
    g = load_builtin("grand_ring").graph
    assert route_edges(g, [19, 0, 1]) == [19, 0]
    with pytest.raises(ValueError):
        route_edges(g, [0, 19])                             # Finish -> Start is one-way
    with pytest.raises(ValueError):
        route_edges(g, [0, 5])


# --- validator on prepared invalid tracks -------------------------------------
def mini(edges, types=("Start", "Checkpoint", "Finish")):
    """Vertices 0..n-1 with the given types; edges (u, v, fuel, directed)."""
    g = TrackGraph()
    for vid, kind in enumerate(types):
        g.add_vertex(vid, vid * 50.0, (vid % 2) * 50.0, kind, 1 if kind == "Checkpoint" else None)
    for eid, (u, v, fuel, directed) in enumerate(edges):
        g.add_edge(eid, u, v, 80.0, 5.0, fuel, directed=directed)
    return g


LOOSE = dict(min_checkpoints=1, min_shortcuts=0, min_stations=0, min_nitro=0, min_one_way=0,
             min_difficulty_levels=1, require_dead_end=False)
TRIANGLE = [(0, 1, 5, False), (1, 2, 5, False), (2, 0, 5, False)]


def test_valid_mini_track_passes_with_lowered_thresholds():
    assert validate(mini(TRIANGLE), **LOOSE).ok
    strict = validate(mini(TRIANGLE))
    assert not strict.ok and any("too few checkpoints: 1, need at least 10" in f for f in strict.failures)
    assert any("no DeadEnd vertex" in f for f in strict.failures)


def test_unreachable_checkpoint_is_rejected():
    data = circuit_to_dict(load_builtin("grand_ring"))
    data["edges"] = [e for e in data["edges"] if 9 not in (e["from"], e["to"])]   # isolate checkpoint 5
    result = validate_circuit(circuit_from_dict(data))
    assert not result.ok
    assert "checkpoint 5 (vertex 9) is unreachable from checkpoint 4 (vertex 7)" in result.failures
    assert "checkpoint 6 (vertex 11) is unreachable from checkpoint 5 (vertex 9)" in result.failures


def test_no_return_path_is_rejected():
    g = mini([(0, 1, 5, True), (1, 2, 5, True), (0, 2, 5, True)])
    result = validate(g, **LOOSE)
    assert len(result.failures) == 2 and "the track has no cycle" in result.failures
    assert "no route from Finish (vertex 2) back to checkpoint 1 (vertex 1)" in result.failures[0]


def test_single_route_is_rejected():
    result = validate(mini(TRIANGLE[:2]), **LOOSE)
    assert "only 1 Start-to-Finish route(s), need at least 2" in result.failures


def test_infeasible_fuel_is_rejected():
    result = validate(mini([(0, 1, 60, False), (1, 2, 60, False), (2, 0, 60, False)]), **LOOSE)
    assert len(result.failures) == 1 and result.failures[0].startswith("no feasible fuel plan for 2 lap(s)")
    assert not result.info["fuel_plan"].feasible
    # the same thirsty track becomes valid once the checkpoint's neighbour sells fuel
    g = mini([(0, 1, 30, False), (1, 3, 30, False), (3, 2, 30, False), (2, 0, 45, False)],
             ("Start", "Checkpoint", "Finish", "FuelStation"))
    result = validate(g, **LOOSE)
    assert result.ok and result.info["fuel_plan"].stops_made >= 1
    g.vertex(3).type = "Intersection"
    assert not validate(g, **LOOSE).ok


def test_missing_start_or_bad_checkpoint_numbers():
    assert "need exactly one Start and one Finish, found 0 and 1" in validate(
        mini(TRIANGLE, ("Intersection", "Checkpoint", "Finish")), **LOOSE).failures[0]
    g = mini(TRIANGLE)
    g.vertex(1).checkpoint_order = 3
    assert any("exactly 1..n" in f for f in validate(g, **LOOSE).failures)


def test_circuit_race_data_is_validated():
    circuit = load_builtin("harbor_eight")
    broken = copy.deepcopy(circuit)
    broken.main_route.remove(9)                             # skips checkpoint 5 and a road
    broken.detour = [6, 24]
    broken.opponent_shortcuts = [0, 999]
    broken.events.append({"time": 5, "type": C.EVENT_ROAD_BLOCK, "target": 999})
    failures = validate_circuit(broken).failures
    assert any("not drivable" in f for f in failures) and any("simple path" in f for f in failures)
    broken.main_route = list(circuit.main_route)
    failures = validate_circuit(broken).failures
    assert len(failures) == 4 and any("detour must" in f for f in failures)
    assert any("shortcut 0 is not a shortcut" in f for f in failures)
    assert any("road_block targets missing road 999" in f for f in failures)

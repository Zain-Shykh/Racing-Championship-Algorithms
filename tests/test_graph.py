import pathlib

import pytest

from smart_racing import config
from smart_racing.core import cost
from smart_racing.core.graph import (BLOCKED, CHECKPOINT, FINISH, OPEN, RESTRICTED, START,
                                     TrackGraph)
from smart_racing.core.models import ChampionshipEntry, Event, Racer, RaceResult
from tests.helpers import make_graph


def road():
    g = TrackGraph()
    g.add_vertex(1, 0, 0)
    g.add_vertex(2, 30, 40)
    g.add_edge(7, 1, 2, distance=50, base_time=10, fuel_cost=10, difficulty=2)
    return g


def test_adjacency_undirected_and_directed():
    g = make_graph([1, 2, 3], [(1, 2), (1, 3)])
    g.add_edge(10, 3, 2, 1.0, directed=True)
    assert [(e.id, w) for e, w in g.neighbors(1)] == [(1, 2), (2, 3)]
    assert [(e.id, w) for e, w in g.neighbors(3)] == [(2, 1), (10, 2)]
    assert [(e.id, w) for e, w in g.neighbors(2)] == [(1, 1)]           # wrong way on 10
    assert [(e.id, w) for e, w in g.incident(2)] == [(1, 1), (10, 3)]   # still listed


def test_neighbors_ascending_edge_id_whatever_insertion_order():
    g = make_graph([1, 2, 3, 4], [])
    for edge_id, other in ((9, 2), (3, 3), (5, 4)):
        g.add_edge(edge_id, 1, other, 1.0)
    assert [e.id for e, _ in g.neighbors(1)] == [3, 5, 9]
    assert [e.id for e in g.edges()] == [3, 5, 9]


def test_invalid_construction_rejected():
    g = make_graph([1, 2], [(1, 2)])
    with pytest.raises(ValueError):
        g.add_vertex(1)
    with pytest.raises(ValueError):
        g.add_edge(1, 1, 2, 1.0)
    with pytest.raises(ValueError):
        g.add_edge(2, 1, 99, 1.0)
    with pytest.raises(ValueError):
        g.add_edge(2, 1, 2, -1.0)
    with pytest.raises(ValueError):
        g.add_edge(2, 1, 2, 1.0, difficulty=6)
    with pytest.raises(ValueError):
        g.add_effect(1, "x", "meteor")


def test_block_and_unblock_without_rebuild():
    g = road()
    edge = g.edge(7)
    assert edge.status == OPEN
    g.block_edge(7)
    assert edge.status == BLOCKED and list(g.neighbors(1)) == []
    assert [e.id for e in g.edges()] == [7]          # still visible to the UI/validator
    assert g.unblock_edge(7) is True
    assert g.unblock_edge(7) is False
    assert edge.status == OPEN and [w for _, w in g.neighbors(1)] == [2]


def test_effective_values_from_effects():
    g = road()
    edge = g.edge(7)
    assert edge.effective_fuel == pytest.approx(10 * 1.1)
    g.add_effect(7, "ev1", config.EFFECT_OIL)
    assert edge.status == RESTRICTED
    assert edge.effective_difficulty == 4
    assert edge.effective_time == pytest.approx(15)
    assert edge.effective_fuel == pytest.approx(10 * 1.3)
    assert edge.obstacle_penalty == 1.0
    assert [w for _, w in g.neighbors(1)] == [2]     # restricted stays traversable


def test_difficulty_bump_capped_at_five():
    g = make_graph([1, 2], [])
    g.add_edge(1, 1, 2, 1.0, difficulty=4)
    g.add_effect(1, "oil", config.EFFECT_OIL)
    assert g.edge(1).effective_difficulty == 5


def test_overlapping_effects_expire_independently():
    g = road()
    edge = g.edge(7)
    g.add_effect(7, "oil-1", config.EFFECT_OIL)
    g.add_effect(7, "speed-2", config.EFFECT_SPEED)
    g.add_effect(7, "oil-3", config.EFFECT_OIL)
    assert (edge.effective_difficulty, edge.time_multiplier, edge.obstacle_penalty) == (4, 1.5, 1.0)

    g.remove_effect(7, "oil-1")                       # the second oil spill is still there
    assert (edge.effective_difficulty, edge.obstacle_penalty) == (4, 1.0)
    g.remove_effect(7, "oil-3")                       # only the speed restriction remains
    assert (edge.effective_difficulty, edge.time_multiplier, edge.obstacle_penalty) == (2, 1.5, 0.5)
    assert edge.status == RESTRICTED

    g.add_effect(7, "block-4", config.EFFECT_BLOCK)
    g.add_effect(7, "block-5", config.EFFECT_BLOCK)
    g.remove_effect(7, "block-4")
    assert edge.status == BLOCKED                     # the other block is still active
    g.remove_effect(7, "block-5")
    assert edge.status == RESTRICTED
    g.remove_effect(7, "speed-2")
    assert edge.status == OPEN and edge.effective_time == 10


def test_service_vertex_activation_and_lookups():
    g = TrackGraph()
    g.add_vertex(1, type=START)
    g.add_vertex(2, type=CHECKPOINT, checkpoint_order=2)
    g.add_vertex(3, type=CHECKPOINT, checkpoint_order=1)
    g.add_vertex(4, type=FINISH)
    g.add_vertex(5, 3, 4, type="FuelStation")
    g.set_vertex_active(5, False)
    assert g.vertex(5).active is False
    assert (g.start.id, g.finish.id) == (1, 4)
    assert [v.id for v in g.checkpoints()] == [3, 2]
    assert g.straight_line(1, 5) == 5
    assert g.vertex(2).is_mandatory and not g.vertex(5).is_mandatory


def test_cost_formula_and_presets():
    edge = road().edge(7)          # D=0.5, T=1, F=1.1, R=0.25, O=0
    assert cost.cost_components(edge) == pytest.approx((0.5, 1.0, 1.1, 0.25, 0.0))
    assert cost.edge_cost(edge, "Balanced") == pytest.approx(2.85)
    assert cost.make_cost_fn("Speed")(edge) == pytest.approx(0.25 + 3 + 0.275 + 0.125)
    assert cost.make_cost_fn((1, 0, 0, 0, 0))(edge) == pytest.approx(0.5)
    assert set(config.COST_PRESETS) == {"Balanced", "Speed", "Economy", "Safety"}
    with pytest.raises(ValueError):
        cost.make_cost_fn((1, 1, 1, 1, -1))


def test_cost_follows_effects_and_route_summary():
    g = road()
    fn = cost.make_cost_fn("Safety")
    before = fn(g.edge(7))
    g.add_effect(7, 1, config.EFFECT_SPEED)
    assert fn(g.edge(7)) == pytest.approx(before + 0.5 * 0.5 + 3 * 0.5)
    summary = cost.route_summary(g, [7], fn)
    assert summary == pytest.approx({"distance": 50, "time": 15, "fuel": 11, "cost": fn(g.edge(7))})


def test_records():
    racer = Racer(1, "Ada", is_human=True)
    assert (racer.fuel, racer.nitro_charges, racer.next_checkpoint) == (100.0, 1, 1)
    event = Event(5, config.EVENT_OIL_SPILL, 12.0, 3, 9, target=7, duration=20.0)
    assert event.key == (12.0, 3, 9) and event.cancelled is False
    assert RaceResult(1, 1, 1, 80.0, 38.5).points_awarded == 0
    assert ChampionshipEntry(1).total_points == 0
    assert config.POINTS_TABLE == (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)


def test_no_forbidden_imports():
    root = pathlib.Path(__file__).resolve().parent.parent / "smart_racing"
    for path in list(root.glob("core/*.py")) + list(root.glob("algorithms/*.py")):
        source = path.read_text()
        for name in ("heapq", "networkx", "pygame", "PriorityQueue"):
            assert f"import {name}" not in source and f"from {name}" not in source, (path, name)

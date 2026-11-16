import math
import random

import pytest

from smart_racing import config
from smart_racing.algorithms.astar import astar, min_cost_ratio
from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dijkstra import dijkstra
from smart_racing.core.cost import distance_cost, make_cost_fn, time_cost
from smart_racing.core.graph import TrackGraph
from tests.helpers import make_graph, st_example


def both(g, s, t, cost_fn=distance_cost):
    d, a = dijkstra(g, s, t, cost_fn), astar(g, s, t, cost_fn)
    assert d.found == a.found
    assert a.cost == pytest.approx(d.cost)
    for res in (d, a):
        if res.found:
            assert res.path[0] == s and res.path[-1] == t
            assert len(res.edge_path) == len(res.path) - 1
            assert sum(cost_fn(g.edge(e)) for e in res.edge_path) == pytest.approx(res.cost)
    return d, a


def brute_force(g, s, t, cost_fn):
    """Cheapest simple path by exhaustive search."""
    best = math.inf

    def walk(u, seen, total):
        nonlocal best
        if u == t:
            best = min(best, total)
            return
        for edge, w in g.neighbors(u):
            if w not in seen:
                walk(w, seen | {w}, total + cost_fn(edge))

    walk(s, {s}, 0.0)
    return best


def random_graph(rng, n, m, zero_weights=False):
    g = TrackGraph()
    for v in range(n):
        g.add_vertex(v, rng.uniform(0, 100), rng.uniform(0, 100))
    for edge_id in range(m):
        u, v = rng.sample(range(n), 2)
        distance = 0.0 if zero_weights and rng.random() < 0.3 else rng.uniform(1, 150)
        g.add_edge(edge_id, u, v, distance, base_time=rng.uniform(0.5, 20),
                   fuel_cost=rng.uniform(0.5, 15), difficulty=rng.randint(1, 5),
                   directed=rng.random() < 0.3)
    return g


def test_st_example_weighted_route_differs_from_bfs():
    g = st_example()
    d, a = both(g, 0, 3)
    assert d.cost == 6 and d.path == [0, 1, 2, 3] == a.path
    assert bfs(g, 0, 3).path == [0, 3]


def test_source_equals_target():
    d, a = both(st_example(), 2, 2)
    assert d.found and d.cost == 0 and d.path == [2] and d.edge_path == []
    assert a.path == [2] and d.expanded == a.expanded == 1


def test_unreachable_target_is_clean():
    g = make_graph([1, 2, 3, 4], [(1, 2), (3, 4)])
    for res in both(g, 1, 4):
        assert not res.found and res.cost == math.inf and res.path == [] and res.edge_path == []
    one_way = make_graph([1, 2], [(1, 2)], directed=True)
    assert not dijkstra(one_way, 2, 1).found


def test_blocked_edge_and_immediate_recalculation():
    g = st_example()
    assert both(g, 0, 3)[0].edge_path == [2, 3, 4]
    g.block_edge(3)                                   # route edge closes
    d, a = both(g, 0, 3)
    assert d.edge_path == a.edge_path == [1] and d.cost == 10
    g.block_edge(1)
    assert not both(g, 0, 3)[0].found
    g.unblock_edge(3)
    assert both(g, 0, 3)[0].cost == 6


def test_recalculation_after_cost_change():
    g = TrackGraph()
    for vid, x in ((1, 0), (2, 50), (3, 100)):
        g.add_vertex(vid, x, 0)
    g.add_vertex(4, 50, 40)
    g.add_edge(1, 1, 2, 50, base_time=5)
    g.add_edge(2, 2, 3, 50, base_time=5)
    g.add_edge(3, 1, 4, 64, base_time=6)
    g.add_edge(4, 4, 3, 64, base_time=6)
    assert both(g, 1, 3, time_cost)[0].edge_path == [1, 2]
    g.add_effect(1, "oil", config.EFFECT_OIL)          # 5 s -> 7.5 s
    d, a = both(g, 1, 3, time_cost)
    assert d.edge_path == a.edge_path == [3, 4] and d.cost == 12
    g.remove_effect(1, "oil")
    assert both(g, 1, 3, time_cost)[0].edge_path == [1, 2]


def test_equal_cost_paths_are_deterministic():
    g = make_graph([(1, 0, 0), (2, 1, 1), (3, 1, -1), (4, 2, 0)],
                   [(1, 3, 5), (1, 2, 5), (3, 4, 5), (2, 4, 5)])
    d, a = both(g, 1, 4)
    assert d.cost == 10
    assert d.path == dijkstra(g, 1, 4).path == [1, 2, 4]     # lower vertex id settles first
    assert a.path == astar(g, 1, 4).path


def test_zero_weight_edges():
    g = make_graph([(1, 0, 0), (2, 10, 0), (3, 20, 0), (4, 30, 0)],
                   [(1, 2, 0), (2, 3, 0), (3, 4, 0), (1, 4, 1)])
    d, a = both(g, 1, 4)
    assert d.cost == 0 and d.path == a.path == [1, 2, 3, 4]
    assert a.heuristic_ratio == 0                     # h = 0: A* falls back to Dijkstra
    assert a.expanded == d.expanded


def test_negative_cost_rejected():
    g = st_example()
    with pytest.raises(ValueError):
        dijkstra(g, 0, 3, lambda e: -1.0)
    with pytest.raises(ValueError):
        astar(g, 0, 3, lambda e: -1.0)


def test_dijkstra_without_target_gives_full_distance_map():
    g = make_graph([1, 2, 3, 4, 5], [(1, 2, 4), (1, 3, 1), (3, 2, 2), (2, 4, 5)])
    res = dijkstra(g, 1)
    assert res.dist == {1: 0, 3: 1, 2: 3, 4: 8} and not res.found
    assert res.path_to(4) == ([1, 3, 2, 4], [2, 3, 4])
    assert res.path_to(5) == ([], [])


def test_counters_and_observer():
    g = st_example()
    for search in (dijkstra, astar):
        steps = []
        res = search(g, 0, 3, observer=steps.append)
        assert res.expanded == sum(s["type"] == "expand" for s in steps) > 0
        assert res.relaxed == sum(s["type"] == "relax" and s["improved"] for s in steps) > 0
        assert res.heap_ops >= res.expanded + res.relaxed and res.heap_comparisons > 0
        assert res.edges_examined >= res.relaxed
        assert steps[-1] == {"type": "done", "found": True, "path": res.path,
                             "edge_path": res.edge_path, "cost": res.cost}
        assert search(g, 0, 3).path == res.path       # observer does not change the result


def test_heuristic_ratio_skips_blocked_and_coincident_edges():
    g = make_graph([(1, 0, 0), (2, 10, 0), (3, 10, 0), (4, 20, 0)],
                   [(1, 2, 20), (2, 3, 0), (3, 4, 5), (1, 4, 30)])
    assert min_cost_ratio(g, distance_cost) == 0.5    # edge 3: 5 / 10; edge 2 is skipped
    g.block_edge(3)
    assert min_cost_ratio(g, distance_cost) == 1.5
    assert min_cost_ratio(make_graph([1], []), distance_cost) == 0.0


def test_astar_expands_no_more_than_dijkstra_on_a_grid():
    n = 15
    vid = lambda r, c: r * n + c
    edges = [(vid(r, c), vid(r, c + 1), 1) for r in range(n) for c in range(n - 1)]
    edges += [(vid(r, c), vid(r + 1, c), 1) for r in range(n - 1) for c in range(n)]
    g = make_graph([(vid(r, c), c, r) for r in range(n) for c in range(n)], edges)
    d, a = both(g, vid(7, 0), vid(7, 14))
    assert d.cost == 14 and a.expanded < d.expanded


@pytest.mark.parametrize("seed", range(40))
def test_dijkstra_and_astar_match_brute_force(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 8)
    g = random_graph(rng, n, rng.randint(1, 14), zero_weights=seed % 4 == 0)
    preset = list(config.COST_PRESETS)[seed % 4]
    for cost_fn in (distance_cost, make_cost_fn(preset)):
        for target in range(1, n):
            expected = brute_force(g, 0, target, cost_fn)
            d, a = both(g, 0, target, cost_fn)
            assert d.found == (expected < math.inf)
            assert d.cost == pytest.approx(expected)
            assert a.cost == pytest.approx(expected)


@pytest.mark.parametrize("seed", range(10))
def test_astar_matches_dijkstra_on_larger_graphs_with_events(seed):
    rng = random.Random(100 + seed)
    g = random_graph(rng, 60, 180)
    for edge_id in rng.sample(range(180), 30):
        g.add_effect(edge_id, "ev", rng.choice(list(config.EDGE_EFFECTS)))
    for preset in config.COST_PRESETS:
        for _ in range(5):
            s, t = rng.sample(range(60), 2)
            both(g, s, t, make_cost_fn(preset))


def test_presets_choose_different_routes():
    g = TrackGraph()
    for vid, x, y in ((1, 0, 0), (2, 50, 30), (3, 50, -30), (4, 100, 0)):
        g.add_vertex(vid, x, y)
    g.add_edge(1, 1, 2, 60, base_time=4, fuel_cost=12, difficulty=4)    # fast, thirsty, hard
    g.add_edge(2, 2, 4, 60, base_time=4, fuel_cost=12, difficulty=4)
    g.add_edge(3, 1, 3, 60, base_time=9, fuel_cost=4, difficulty=1)     # slow, frugal, easy
    g.add_edge(4, 3, 4, 60, base_time=9, fuel_cost=4, difficulty=1)
    routes = {p: both(g, 1, 4, make_cost_fn(p))[0].edge_path for p in config.COST_PRESETS}
    assert routes["Speed"] == [1, 2]
    assert routes["Economy"] == routes["Safety"] == [3, 4]

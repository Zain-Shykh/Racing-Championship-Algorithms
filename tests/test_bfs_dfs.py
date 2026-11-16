import pytest

from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import (connected_components, dead_ends, dfs,
                                         enumerate_paths, find_cycle)
from smart_racing.core.graph import CHECKPOINT, DEAD_END, FINISH, START, TrackGraph
from tests.helpers import make_graph, st_example


def circuit():
    """S(1) - A(2) - C(3) - F(4), spur A - D(5) - E(6), loop C - G(7) - H(8) - C,
    and an island 9 - 10."""
    g = TrackGraph()
    for vid, kind in ((1, START), (2, "Intersection"), (3, CHECKPOINT), (4, FINISH),
                      (5, "Intersection"), (6, DEAD_END), (7, "Intersection"),
                      (8, "Intersection"), (9, "Intersection"), (10, "Intersection")):
        g.add_vertex(vid, type=kind)
    for i, (u, v) in enumerate([(1, 2), (2, 3), (3, 4), (2, 5), (5, 6), (3, 7), (7, 8),
                                (8, 3), (9, 10)], start=1):
        g.add_edge(i, u, v, 1.0)
    return g


# --- BFS ------------------------------------------------------------------------
def test_bfs_single_vertex():
    g = make_graph([1], [])
    res = bfs(g, 1, 1)
    assert res.found and res.path == [1] and res.edge_path == []
    assert bfs(g, 1).reachable == {1}


def test_bfs_minimum_edges_st_example():
    res = bfs(st_example(), 0, 3)
    assert res.found and res.path == [0, 3] and res.edge_path == [1]
    assert res.dist[3] == 1


def test_bfs_minimum_edge_count_on_branching_cyclic_graph():
    # ring of 6 plus chord 1-4; BFS depths must equal the true hop counts
    g = make_graph(range(1, 7), [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 1), (1, 4)])
    res = bfs(g, 1)
    assert res.dist == {1: 0, 2: 1, 6: 1, 4: 1, 3: 2, 5: 2}
    assert res.order == [1, 2, 6, 4, 3, 5]
    assert res.visited == 6 and res.edges_examined == 14
    assert bfs(g, 1, 3).path == [1, 2, 3]            # ascending edge id tie-break


def test_bfs_unreachable_and_disconnected():
    g = circuit()
    res = bfs(g, 1, 9)
    assert not res.found and res.path == [] and res.edge_path == []
    assert bfs(g, 1).reachable == {1, 2, 3, 4, 5, 6, 7, 8}
    assert bfs(g, 1).path_to(10) == ([], [])


def test_bfs_respects_direction_and_blocks():
    g = make_graph([1, 2, 3], [(1, 2), (2, 3)], directed=True)
    assert bfs(g, 1, 3).path == [1, 2, 3]
    assert not bfs(g, 3, 1).found
    g.block_edge(2)
    assert not bfs(g, 1, 3).found
    g.unblock_edge(2)
    assert bfs(g, 1, 3).found


def test_bfs_unknown_vertex_raises():
    with pytest.raises(KeyError):
        bfs(make_graph([1], []), 1, 99)


def test_bfs_observer_steps():
    steps = []
    res = bfs(st_example(), 0, 3, observer=steps.append)
    assert steps[0] == {"type": "visit", "vertex": 0, "depth": 0, "frontier": []}
    assert steps[1] == {"type": "examine", "edge": 1, "from": 0, "to": 3,
                        "discovered": True, "depth": 1}
    assert steps[-1]["type"] == "done" and steps[-1]["path"] == res.path
    assert sum(s["type"] == "visit" for s in steps) == res.visited
    assert sum(s["type"] == "examine" for s in steps) == res.edges_examined


# --- DFS traversal ---------------------------------------------------------------
def test_dfs_order_and_counters():
    res = dfs(circuit(), 1)
    assert res.order == [1, 2, 3, 4, 7, 8, 5, 6]
    assert res.postorder == [4, 8, 7, 3, 6, 5, 2, 1]
    assert res.visited == 8 and res.edges_examined == 16
    assert res.parent[8] == (7, 7) and res.parent[1] is None
    assert res.reachable == {1, 2, 3, 4, 5, 6, 7, 8}


def test_dfs_single_vertex_and_observer():
    steps = []
    res = dfs(make_graph([1], []), 1, observer=steps.append)
    assert res.order == [1]
    assert [s["type"] for s in steps] == ["visit", "backtrack"]


def test_dfs_deep_path_does_not_recurse():
    n = 5000
    g = make_graph(range(n), [(i, i + 1) for i in range(n - 1)])
    assert dfs(g, 0).order == list(range(n))
    assert not find_cycle(g).has_cycle
    assert enumerate_paths(g, 0, n - 1, max_length=n).paths == [list(range(n))]


# --- cycles ------------------------------------------------------------------------
def assert_valid_cycle(g, cycle):
    assert len(cycle) >= 2 and cycle[0] == cycle[-1]
    used = set()
    for u, w in zip(cycle, cycle[1:]):
        edge = next(e for e, x in g.neighbors(u) if x == w and e.id not in used)
        used.add(edge.id)


def test_cycle_detected_in_undirected_graph():
    g = circuit()
    res = find_cycle(g)
    assert res.has_cycle and set(res.cycle) == {3, 7, 8}
    assert_valid_cycle(g, res.cycle)


def test_no_cycle_in_tree_single_vertex_or_after_block():
    assert not find_cycle(make_graph([1], [])).has_cycle
    assert not find_cycle(make_graph([1, 2, 3, 4], [(1, 2), (2, 3), (2, 4)])).has_cycle
    g = circuit()
    g.block_edge(7)
    res = find_cycle(g)
    assert not res.has_cycle and res.cycle == []


def test_two_way_road_alone_is_not_a_cycle_but_parallel_roads_are():
    assert not find_cycle(make_graph([1, 2], [(1, 2)])).has_cycle
    g = make_graph([1, 2], [(1, 2), (1, 2)])
    assert find_cycle(g).cycle == [1, 2, 1]


def test_directed_cycles():
    dag = make_graph([1, 2, 3], [(1, 2), (2, 3), (1, 3)], directed=True)
    assert not find_cycle(dag).has_cycle
    ring = make_graph([1, 2, 3], [(1, 2), (2, 3), (3, 1)], directed=True)
    res = find_cycle(ring)
    assert res.has_cycle
    assert_valid_cycle(ring, res.cycle)
    back_and_forth = make_graph([1, 2], [(1, 2), (2, 1)], directed=True)
    assert find_cycle(back_and_forth).has_cycle


def test_mixed_cycle_found_whatever_the_edge_order():
    # two-way 1-2, one-way 1->3 and 3->2: the cycle 1->3->2->1 uses all three
    for order in ([(1, 2, False), (1, 3, True), (3, 2, True)],
                  [(1, 3, True), (3, 2, True), (1, 2, False)]):
        g = make_graph([1, 2, 3], [])
        for i, (u, v, directed) in enumerate(order, start=1):
            g.add_edge(i, u, v, 1.0, directed=directed)
        res = find_cycle(g)
        assert res.has_cycle and set(res.cycle) == {1, 2, 3}
        assert_valid_cycle(g, res.cycle)
    # one-way edges that only lead away never close a cycle
    g = make_graph([1, 2, 3], [])
    g.add_edge(1, 1, 2, 1.0)
    g.add_edge(2, 1, 3, 1.0, directed=True)
    g.add_edge(3, 2, 3, 1.0, directed=True)
    assert not find_cycle(g).has_cycle


# --- components ----------------------------------------------------------------------
def test_connected_components():
    g = circuit()
    res = connected_components(g)
    assert res.components == [[1, 2, 3, 4, 5, 6, 7, 8], [9, 10]]
    assert res.count == 2 and res.component_of[10] == 1
    g.block_edge(4)
    assert connected_components(g).components == [[1, 2, 3, 4, 7, 8], [5, 6], [9, 10]]
    assert connected_components(make_graph([1], [])).components == [[1]]


def test_components_ignore_direction():
    g = make_graph([1, 2, 3], [(2, 1), (2, 3)], directed=True)
    assert connected_components(g).components == [[1, 2, 3]]


# --- dead ends -----------------------------------------------------------------------
def test_dead_end_spur_detected_loop_is_not():
    res = dead_ends(circuit())
    assert res.dead_ends == [5, 6]       # the spur; 7 and 8 loop back without reversing
    assert res.states > 0


def test_no_dead_end_on_plain_route_and_mandatory_excluded():
    g = TrackGraph()
    for vid, kind in ((1, START), (2, "Intersection"), (3, FINISH), (4, CHECKPOINT)):
        g.add_vertex(vid, type=kind)
    g.add_edge(1, 1, 2, 1.0)
    g.add_edge(2, 2, 3, 1.0)
    g.add_edge(3, 2, 4, 1.0)             # checkpoint on a spur is mandatory, not a dead end
    assert dead_ends(g).dead_ends == []


def test_one_way_trap_is_dead_end_and_block_creates_one():
    g = make_graph([1, 2, 3, 4, 5], [(1, 2), (2, 3), (2, 4), (4, 3)])
    g.add_edge(9, 2, 5, 1.0, directed=True)          # one-way into a cul-de-sac
    assert dead_ends(g, start=1, finish=3).dead_ends == [5]
    g.block_edge(4)                                   # 4 now only connects back to 2
    assert dead_ends(g, start=1, finish=3).dead_ends == [4, 5]


# --- path enumeration ------------------------------------------------------------------
def test_enumerate_paths_st_example_and_exclude_main():
    g = st_example()
    res = enumerate_paths(g, 0, 3)
    assert res.paths == [[0, 3], [0, 1, 2, 3]]
    assert res.edge_paths == [[1], [2, 3, 4]]
    assert not res.route_limit_hit and not res.length_limit_hit
    alternatives = enumerate_paths(g, 0, 3, exclude=[1])
    assert alternatives.paths == [[0, 1, 2, 3]]


def test_enumerate_paths_limits():
    # 6 stacked diamonds: 2^6 = 64 simple paths of 12 edges
    edges = []
    for i in range(6):
        a, top, bottom, b = 3 * i, 3 * i + 1, 3 * i + 2, 3 * i + 3
        edges += [(a, top), (a, bottom), (top, b), (bottom, b)]
    g = make_graph(range(19), edges)
    assert len(enumerate_paths(g, 0, 18, max_routes=1000).paths) == 64
    limited = enumerate_paths(g, 0, 18, max_routes=5)
    assert len(limited.paths) == 5 and limited.route_limit_hit
    short = enumerate_paths(g, 0, 18, max_routes=1000, max_length=11)
    assert short.paths == [] and short.length_limit_hit
    assert all(len(p) <= 3 for p in enumerate_paths(g, 0, 3, max_length=2).edge_paths)


def test_enumerate_paths_are_simple_and_terminate_on_cycles():
    g = make_graph(range(1, 6), [(a, b) for a in range(1, 6) for b in range(a + 1, 6)])
    res = enumerate_paths(g, 1, 5, max_routes=1000)
    assert len(res.paths) == 16                      # 1 + 3 + 6 + 6 in K5
    assert all(len(set(p)) == len(p) for p in res.paths)
    assert len({tuple(p) for p in res.paths}) == 16


def test_enumerate_paths_unreachable_and_trivial():
    g = circuit()
    assert enumerate_paths(g, 1, 9).paths == []
    assert enumerate_paths(g, 1, 1).paths == [[1]]

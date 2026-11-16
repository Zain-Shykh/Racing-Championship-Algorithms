import itertools
import random

import pytest

from smart_racing.algorithms.mst import UnionFind, kruskal


def brute_force_mst_weight(vertices, edges):
    """Cheapest set of |V|-1 edges that connects every vertex, or None."""
    best = None
    for subset in itertools.combinations(edges, len(vertices) - 1):
        sets = UnionFind(vertices)
        if all(sets.union(u, v) for _, u, v, _ in subset):      # acyclic with V-1 edges = spanning tree
            weight = sum(e[3] for e in subset)
            best = weight if best is None else min(best, weight)
    return best


def test_small_known_graph():
    edges = [(1, "a", "b", 4), (2, "b", "c", 1), (3, "a", "c", 3), (4, "c", "d", 2), (5, "b", "d", 5)]
    res = kruskal("abcd", edges)
    assert [e[0] for e in res.edges] == [2, 4, 3]
    assert res.total_weight == 6 and res.is_spanning_tree and res.components == 1
    assert res.unions == 3 and res.finds >= 6 and res.comparisons > 0


def test_matches_brute_force_on_random_graphs():
    rng = random.Random(5)
    trees = 0
    for _ in range(150):
        n = rng.randint(2, 6)
        vertices = list(range(n))
        pairs = [p for p in itertools.combinations(vertices, 2) if rng.random() < 0.7]
        edges = [(i, u, v, rng.randint(1, 9)) for i, (u, v) in enumerate(pairs)]
        res = kruskal(vertices, edges)
        expected = brute_force_mst_weight(vertices, edges)
        assert res.is_spanning_tree == (expected is not None)
        assert len(res.edges) == n - res.components == res.unions
        if res.is_spanning_tree:
            trees += 1
            assert res.total_weight == expected
    assert 30 < trees < 150


def test_disconnected_input_gives_a_forest():
    res = kruskal([1, 2, 3, 4, 5], [(1, 1, 2, 3.0), (2, 2, 3, 1.0), (3, 1, 3, 2.0), (4, 4, 5, 7.0)])
    assert not res.is_spanning_tree and res.components == 2
    assert [e[0] for e in res.edges] == [2, 3, 4] and res.total_weight == 10.0


def test_equal_weights_break_ties_by_edge_id():
    square = [(4, 0, 1, 1), (3, 1, 2, 1), (2, 2, 3, 1), (1, 3, 0, 1)]
    steps = []
    res = kruskal(range(4), square, steps.append)
    assert [e[0] for e in res.edges] == [1, 2, 3]
    assert res.edges_examined == 3                     # stops once the tree is complete
    assert [s["accepted"] for s in steps[:-1]] == [True, True, True] and steps[-1]["type"] == "done"
    assert kruskal(range(4), square[::-1]).edges == res.edges


def test_degenerate_inputs():
    assert kruskal([7], []).is_spanning_tree and kruskal([7], []).edges == []
    assert not kruskal([], []).is_spanning_tree
    loops = kruskal([1, 2], [(1, 1, 1, 0), (2, 1, 2, 5), (3, 1, 2, 5)])
    assert [e[0] for e in loops.edges] == [2] and loops.is_spanning_tree
    with pytest.raises(ValueError):
        kruskal([1, 2], [(1, 1, 3, 1)])


def test_union_find():
    sets = UnionFind(range(6))
    assert sets.union(0, 1) and sets.union(2, 3) and sets.union(1, 3) and not sets.union(0, 2)
    assert sets.find(0) == sets.find(3) != sets.find(4)
    assert sets.unions == 3 and sets.finds == 8 + 3

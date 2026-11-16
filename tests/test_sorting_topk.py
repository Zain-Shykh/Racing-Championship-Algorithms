import math
import random
import sys

import pytest

from smart_racing.algorithms.sorting import championship_less, heap_sort, merge_sort, quick_sort
from smart_racing.algorithms.topk import top_k
from smart_racing.core.models import ChampionshipEntry as Entry

SORTS = (merge_sort, quick_sort, heap_sort)


def key(e):
    """Independent statement of SPEC 4.7 used only to check the comparator."""
    return (-e.total_points, -e.wins, e.sum_of_finish_positions, e.best_fastest_lap, e.racer_id)


def random_entries(rng, n, spread):
    """Smaller `spread` = more duplicate field values; racer ids stay unique."""
    ids = list(range(1, n + 1))
    rng.shuffle(ids)
    return [Entry(i, rng.randint(0, spread), rng.randint(0, 3), rng.randint(3, 3 + spread),
                  rng.choice([math.inf, 60.0, 61.5, 70.25])) for i in ids]


def datasets():
    rng = random.Random(42)
    base = random_entries(rng, 200, 60)
    ranked = sorted(base, key=key)
    return {
        "empty": [],
        "singleton": [Entry(1, 10)],
        "random": base,
        "sorted": ranked,
        "reverse": ranked[::-1],
        "duplicates": random_entries(rng, 300, 2),
        "id_tie_break": [Entry(i, 25, 1, 4, 61.5) for i in (5, 2, 9, 1, 7)],
    }


def test_comparator_follows_every_tie_break_level():
    best = Entry(9, 50, 2, 6, 60.0)
    worse = [Entry(1, 49, 9, 1, 1.0), Entry(1, 50, 1, 1, 1.0), Entry(1, 50, 2, 7, 1.0),
             Entry(1, 50, 2, 6, 60.5), Entry(10, 50, 2, 6, 60.0)]
    for other in worse:
        assert championship_less(best, other) and not championship_less(other, best)
    assert not championship_less(best, best)
    assert championship_less(Entry(1, 5, 0, 3, 70.0), Entry(2, 5, 0, 3))    # no lap time ranks last


@pytest.mark.parametrize("name", datasets())
def test_three_sorts_agree(name):
    data = datasets()[name]
    before = list(data)
    expected = sorted(data, key=key)
    for sort in SORTS:
        res = sort(data)
        assert res.items == expected, sort.__name__
        assert res.items is not data and data == before         # new list, input untouched
        assert (res.comparisons > 0) == (len(data) > 1)


def test_final_racer_id_tie_break():
    data = datasets()["id_tie_break"]
    for sort in SORTS:
        assert [e.racer_id for e in sort(data).items] == [1, 2, 5, 7, 9]
    assert [e.racer_id for e in top_k(data, 2).items] == [1, 2]


def test_merge_sort_is_stable_and_sorts_accept_any_less():
    rng = random.Random(8)
    records = [(rng.randint(0, 5), i) for i in range(400)]      # (key, original position)
    by_key = lambda a, b: a[0] < b[0]
    assert merge_sort(records, by_key).items == sorted(records, key=lambda r: r[0])
    for sort in SORTS:
        assert [r[0] for r in sort(records, by_key).items] == sorted(r[0] for r in records)
        assert sort(records, lambda a, b: a > b).items == sorted(records, reverse=True)


def test_comparison_counts_are_n_log_n():
    rng = random.Random(1)
    n = 2000
    values = [rng.random() for _ in range(n)]
    bound = 4 * n * math.log2(n)
    for sort in SORTS:
        for data in (values, sorted(values), sorted(values, reverse=True), [v > 0.5 for v in values]):
            assert n - 1 <= sort(data, lambda a, b: a < b).comparisons < bound


@pytest.mark.parametrize("shape", ["sorted", "reverse", "duplicates", "all_equal"])
def test_quick_sort_large_input_without_deep_recursion(shape):
    n = 100_000
    data = {"sorted": list(range(n)), "reverse": list(range(n, 0, -1)),
            "duplicates": [i % 7 for i in range(n)], "all_equal": [3] * n}[shape]
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(200)          # any per-element recursion would fail here
    try:
        res = quick_sort(data, lambda a, b: a < b)
    finally:
        sys.setrecursionlimit(limit)
    assert res.items == sorted(data)
    assert res.comparisons < 4 * n * math.log2(n)


def test_observer_reports_comparisons():
    steps = []
    data = datasets()["id_tie_break"]
    for sort in SORTS:
        steps.clear()
        res = sort(data, observer=steps.append)
        assert sum(s["type"] == "compare" for s in steps) == res.comparisons
        assert steps[-1]["type"] == "done" and steps[-1]["items"] == res.items


@pytest.mark.parametrize("name", datasets())
def test_top_k_equals_prefix_of_full_sort(name):
    data = datasets()[name]
    full = merge_sort(data).items
    n = len(data)
    for k in {0, 1, n // 2, n, n + 5}:
        res = top_k(data, k)
        assert res.items == full[:k], k
        assert res.k == k and len(res.items) == min(k, n)


def test_top_k_edge_cases_and_cost():
    data = datasets()["random"]
    assert top_k(data, -3).items == [] and top_k([], 4).items == []
    small, large = top_k(data, 3), top_k(data, len(data))
    assert small.comparisons < large.comparisons < merge_sort(data).comparisons * 4
    assert small.comparisons < merge_sort(data).comparisons     # O(n log k) beats a full sort for small k
    steps = []
    top_k(data, 3, observer=steps.append)
    assert sum(s["type"] == "offer" for s in steps) == len(data) and steps[-1]["type"] == "done"


def test_top_k_matches_stable_sort_for_non_total_orders():
    rng = random.Random(4)
    records = [(rng.randint(0, 4), i) for i in range(200)]
    by_key = lambda a, b: a[0] < b[0]
    for k in (1, 7, 60, 200):
        assert top_k(records, k, by_key).items == merge_sort(records, by_key).items[:k]

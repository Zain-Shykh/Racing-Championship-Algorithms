import random

import pytest

from smart_racing.algorithms.knapsack import (Item, knapsack_dp, knapsack_exhaustive,
                                              knapsack_greedy)

SUPPLIED = [Item(1, 6, 30, "A"), Item(2, 5, 24, "B"), Item(3, 5, 24, "C")]
# Team-created cases where greedy is strictly worse: (items, budget, greedy, optimum).
TEAM_CASES = [
    ([Item(1, 6, 12), Item(2, 5, 9), Item(3, 5, 9)], 10, 12, 18),
    ([Item(1, 10, 60), Item(2, 20, 100), Item(3, 30, 120)], 50, 160, 220),
]


def check_feasible(res, items, budget):
    by_id = {item.id: item for item in items}
    assert len(set(res.selected)) == len(res.selected)
    assert res.total_cost == sum(by_id[i].cost for i in res.selected) <= budget
    assert res.total_benefit == pytest.approx(sum(by_id[i].benefit for i in res.selected))


def test_supplied_example():
    greedy, dp = knapsack_greedy(SUPPLIED, 10), knapsack_dp(SUPPLIED, 10)
    assert (greedy.selected, greedy.total_benefit) == ([1], 30)
    assert (dp.selected, dp.total_benefit, dp.total_cost) == ([2, 3], 48, 10)
    assert dp.states == 3 * 11 and dp.table[3][10] == 48
    assert knapsack_exhaustive(SUPPLIED, 10).total_benefit == 48


@pytest.mark.parametrize("items, budget, greedy_value, optimum", TEAM_CASES)
def test_team_cases_where_greedy_is_strictly_worse(items, budget, greedy_value, optimum):
    assert knapsack_greedy(items, budget).total_benefit == greedy_value
    assert knapsack_dp(items, budget).total_benefit == optimum
    assert knapsack_exhaustive(items, budget).total_benefit == optimum
    assert greedy_value < optimum


def test_dp_equals_exhaustive_on_random_instances():
    rng = random.Random(7)
    for _ in range(200):
        items = [Item(i, rng.randint(0, 12), rng.randint(0, 40)) for i in range(rng.randint(0, 9))]
        budget = rng.randint(0, 30)
        dp, brute, greedy = (f(items, budget) for f in (knapsack_dp, knapsack_exhaustive, knapsack_greedy))
        for res in (dp, brute, greedy):
            check_feasible(res, items, budget)
        assert dp.total_benefit == brute.total_benefit >= greedy.total_benefit
        assert dp.states == len(items) * (budget + 1) and brute.states == 2 ** len(items)


def test_zero_cost_pickups():
    items = [Item(1, 0, 5), Item(2, 0, 0), Item(3, 4, 8), Item(4, 0, 7)]
    for budget in (0, 4):
        greedy, dp = knapsack_greedy(items, budget), knapsack_dp(items, budget)
        expected = [1, 4] if budget == 0 else [1, 3, 4]
        assert greedy.selected == dp.selected == expected   # the zero-benefit item is never taken
        assert dp.total_cost == (0 if budget == 0 else 4)


def test_greedy_order_and_tie_break():
    steps = []
    items = [Item(3, 2, 10), Item(1, 2, 10), Item(2, 4, 20), Item(9, 0, 1), Item(5, 1, 1)]
    res = knapsack_greedy(items, 5, steps.append)
    considered = [(s["item"], s["picked"]) for s in steps if s["type"] == "consider"]
    # zero-cost first, then equal ratios by lower id; item 2 no longer fits, item 5 still does
    assert considered == [(9, True), (1, True), (2, False), (3, True), (5, True)]
    assert res.selected == [1, 3, 5, 9] and res.states == 5
    assert steps[-1]["type"] == "done"


def test_edge_cases_and_validation():
    assert knapsack_dp([], 10).selected == [] and knapsack_greedy([], 10).total_benefit == 0
    too_big = [Item(1, 11, 99)]
    assert knapsack_dp(too_big, 10).selected == knapsack_greedy(too_big, 10).selected == []
    for bad_items, bad_budget in (([Item(1, -1, 2)], 5), ([Item(1, 1.5, 2)], 5), (SUPPLIED, -1),
                                  ([Item(1, 1, 1), Item(1, 2, 2)], 5)):
        for solver in (knapsack_dp, knapsack_greedy, knapsack_exhaustive):
            with pytest.raises(ValueError):
                solver(bad_items, bad_budget)
    with pytest.raises(ValueError):
        knapsack_exhaustive([Item(i, 1, 1) for i in range(30)], 5)


def test_dp_observer_shows_table_fill_and_traceback():
    steps = []
    res = knapsack_dp(SUPPLIED, 10, steps.append)
    cells = [s for s in steps if s["type"] == "cell"]
    assert len(cells) == res.states
    assert all(res.table[s["i"]][s["b"]] == s["value"] for s in cells)
    trace = [s for s in steps if s["type"] == "trace"]
    assert [(s["item"], s["taken"]) for s in trace] == [(3, True), (2, True), (1, False)]
    assert steps[-1] == {"type": "done", "selected": [2, 3], "cost": 10, "benefit": 48, "states": 33}

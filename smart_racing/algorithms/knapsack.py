"""0/1 knapsack: table DP with reconstruction, greedy ratio heuristic and an
exhaustive search used as the correctness oracle (Project.md 5.3 Problem A)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from smart_racing.algorithms.sorting import merge_sort

Observer = Callable[[dict], None]

EXHAUSTIVE_MAX_ITEMS = 22      # 2^22 subsets is the most the oracle will enumerate


@dataclass(frozen=True)
class Item:
    id: int
    cost: int                  # non-negative integer in the caller's scaled unit
    benefit: float
    name: str = ""


@dataclass
class KnapsackResult:
    algorithm: str
    budget: int
    selected: list[int] = field(default_factory=list)   # item ids, ascending
    total_cost: int = 0
    total_benefit: float = 0
    states: int = 0            # DP cells filled / greedy items considered / subsets examined
    # DP only: table[i][b] = best benefit using the first i items within budget b.
    table: list[list[float]] | None = None


def _check(items: Sequence[Item], budget: int) -> None:
    if not isinstance(budget, int) or budget < 0:
        raise ValueError(f"budget must be a non-negative integer, got {budget!r}")
    for item in items:
        if not isinstance(item.cost, int) or item.cost < 0:
            raise ValueError(f"item {item.id}: cost must be a non-negative integer, got {item.cost!r}")
    if len({item.id for item in items}) != len(items):
        raise ValueError("item ids must be unique")


def _finish(res: KnapsackResult, chosen: list[Item], observer: Observer | None) -> KnapsackResult:
    ids = [item.id for item in chosen]
    res.selected = merge_sort(ids, lambda a, b: a < b).items
    res.total_cost = sum(item.cost for item in chosen)
    res.total_benefit = sum(item.benefit for item in chosen)
    if observer:
        observer({"type": "done", "selected": res.selected, "cost": res.total_cost,
                  "benefit": res.total_benefit, "states": res.states})
    return res


def knapsack_dp(items: Sequence[Item], budget: int, observer: Observer | None = None) -> KnapsackResult:
    """Optimal 0/1 knapsack by bottom-up table DP.

    State: `dp[i][b]` = best total benefit using only the first `i` items with
    total cost at most `b`. Base case `dp[0][b] = 0`. Recurrence
    `dp[i][b] = max(dp[i-1][b], dp[i-1][b - c_i] + v_i if c_i <= b)`; the item is
    taken only on strict improvement. Reconstruction walks from `dp[m][B]` up:
    item `i` was taken exactly when `dp[i][b] != dp[i-1][b]`.

    Time O(m * B), space O(m * B) (the table is kept for the traceback).
    Pseudo-polynomial: B is a numeric value, not an input length.
    """
    _check(items, budget)
    res = KnapsackResult("dp", budget)
    m = len(items)
    dp: list[list[float]] = [[0] * (budget + 1) for _ in range(m + 1)]
    for i, item in enumerate(items, start=1):
        prev, row = dp[i - 1], dp[i]
        for b in range(budget + 1):
            best, take = prev[b], False
            if item.cost <= b and prev[b - item.cost] + item.benefit > best:
                best, take = prev[b - item.cost] + item.benefit, True
            row[b] = best
            res.states += 1
            if observer:
                observer({"type": "cell", "i": i, "b": b, "item": item.id, "value": best, "take": take})
    chosen = []
    b = budget
    for i in range(m, 0, -1):
        item = items[i - 1]
        taken = dp[i][b] != dp[i - 1][b]
        if observer:
            observer({"type": "trace", "i": i, "b": b, "item": item.id, "taken": taken})
        if taken:
            chosen.append(item)
            b -= item.cost
    res.table = dp
    return _finish(res, chosen, observer)


def knapsack_greedy(items: Sequence[Item], budget: int, observer: Observer | None = None) -> KnapsackResult:
    """Greedy benefit/cost heuristic. Feasible, not guaranteed optimal.

    1. Items with benefit <= 0 are never taken (this covers zero-cost
       zero-benefit items: they change nothing).
    2. Zero-cost items with positive benefit are taken first, in id order.
    3. The rest are ordered by ratio benefit/cost descending, ties by lower id,
       and taken in that order whenever they still fit; an item that does not
       fit is skipped and the scan continues.

    Ratios are compared by cross-multiplication, so no rounding is involved.
    Time O(m log m) for the hand-written merge sort, space O(m).
    """
    _check(items, budget)
    res = KnapsackResult("greedy", budget)

    def better(a: Item, b: Item) -> bool:
        if (a.cost == 0) != (b.cost == 0):
            return a.cost == 0
        left, right = a.benefit * b.cost, b.benefit * a.cost
        return left > right or (left == right and a.id < b.id)

    order = merge_sort([item for item in items if item.benefit > 0], better).items
    chosen = []
    remaining = budget
    for item in order:
        res.states += 1
        fits = item.cost <= remaining
        if fits:
            chosen.append(item)
            remaining -= item.cost
        if observer:
            observer({"type": "consider", "item": item.id, "cost": item.cost, "benefit": item.benefit,
                      "ratio": item.benefit / item.cost if item.cost else None,
                      "picked": fits, "remaining": remaining})
    return _finish(res, chosen, observer)


def knapsack_exhaustive(items: Sequence[Item], budget: int, observer: Observer | None = None) -> KnapsackResult:
    """Try every subset. The oracle for small instances only.

    Time O(m * 2^m), space O(m). Refuses more than `EXHAUSTIVE_MAX_ITEMS` items.
    """
    _check(items, budget)
    m = len(items)
    if m > EXHAUSTIVE_MAX_ITEMS:
        raise ValueError(f"exhaustive search is limited to {EXHAUSTIVE_MAX_ITEMS} items, got {m}")
    res = KnapsackResult("exhaustive", budget)
    best_mask, best = 0, 0
    for mask in range(1 << m):
        res.states += 1
        cost = benefit = 0
        for i in range(m):
            if mask >> i & 1:
                cost += items[i].cost
                benefit += items[i].benefit
        if cost <= budget and benefit > best:
            best_mask, best = mask, benefit
            if observer:
                observer({"type": "improve", "items": [items[i].id for i in range(m) if mask >> i & 1],
                          "cost": cost, "benefit": benefit})
    return _finish(res, [items[i] for i in range(m) if best_mask >> i & 1], observer)

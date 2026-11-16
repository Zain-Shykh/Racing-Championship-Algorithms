"""The championship comparator and three hand-written comparison sorts.

Every sort takes any strict `less(a, b)` ("a ranks before b"), returns a new
list and counts comparator calls. No `sorted()` / `list.sort()` anywhere.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from smart_racing.core.models import ChampionshipEntry

Observer = Callable[[dict], None]
Less = Callable[[Any, Any], bool]
QUICK_SORT_SEED = 0            # fixed seed for pivot positions: same input, same run


def championship_less(a: ChampionshipEntry, b: ChampionshipEntry) -> bool:
    """True when `a` ranks strictly ahead of `b` (SPEC 4.7, Project.md 4.6).

    Higher points, then more wins, then lower sum of finish positions, then
    lower best fastest lap, then lower racer id. A total order when racer ids
    are unique. This is the only ordering used by the sorts and by top-k. O(1).
    """
    return ((-a.total_points, -a.wins, a.sum_of_finish_positions, a.best_fastest_lap, a.racer_id)
            < (-b.total_points, -b.wins, b.sum_of_finish_positions, b.best_fastest_lap, b.racer_id))


@dataclass
class SortResult:
    algorithm: str
    items: list            # new list, best first
    comparisons: int       # comparator calls


def counted(less: Less, observer: Observer | None = None) -> tuple[Less, list[int]]:
    """Wrap `less` so calls are counted in the returned one-element list and
    reported to the observer as `compare` steps."""
    count = [0]

    def lt(a: Any, b: Any) -> bool:
        count[0] += 1
        result = less(a, b)
        if observer:
            observer({"type": "compare", "a": a, "b": b, "less": result})
        return result

    return lt, count


def _finish(algorithm: str, items: list, count: list[int], observer: Observer | None) -> SortResult:
    if observer:
        observer({"type": "done", "items": list(items), "comparisons": count[0]})
    return SortResult(algorithm, items, count[0])


def merge_sort(items: Iterable, less: Less = championship_less,
               observer: Observer | None = None) -> SortResult:
    """Bottom-up merge sort. Stable: on a tie the left (earlier) element wins.

    Time O(n log n) in every case, O(n) extra space, no recursion.
    """
    a = list(items)
    lt, count = counted(less, observer)
    n, width = len(a), 1
    while width < n:
        out: list = []
        for lo in range(0, n, 2 * width):
            mid, hi = min(lo + width, n), min(lo + 2 * width, n)
            i, j = lo, mid
            while i < mid and j < hi:
                if lt(a[j], a[i]):       # strictly less only, so ties keep input order
                    out.append(a[j])
                    j += 1
                else:
                    out.append(a[i])
                    i += 1
            out.extend(a[i:mid])
            out.extend(a[j:hi])
        if observer:
            observer({"type": "pass", "width": width, "items": list(out)})
        a, width = out, 2 * width
    return _finish("merge_sort", a, count, observer)


def quick_sort(items: Iterable, less: Less = championship_less,
               observer: Observer | None = None) -> SortResult:
    """Quick sort with a median-of-three pivot and three-way partitioning.

    Pivot: the median of three elements at pseudo-random positions of the
    range, drawn from `random.Random(QUICK_SORT_SEED)` created per call, so the
    run is deterministic and no fixed input shape (sorted, reverse-sorted,
    organ-pipe) is a bad case. Fixed positions such as first/middle/last are
    not used because the three-way partition reorders the "greater" side and
    that makes them degrade to O(n^2) on already sorted input.
    Partition: Dijkstra's three-way scheme (`< pivot | == pivot | > pivot`), so
    elements equal to the pivot are never processed again and duplicate-heavy
    input is fast. Ranges are kept on an explicit stack with the larger side
    deferred, so the stack holds O(log n) ranges and Python's recursion limit
    is never involved.

    Time O(n log n) expected, O(n^2) worst case (vanishingly unlikely),
    O(n) for the copy plus O(log n) stack. Not stable.
    """
    a = list(items)
    lt, count = counted(less, observer)
    pick = random.Random(QUICK_SORT_SEED).randint
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        while lo < hi:
            x, pivot, z = a[pick(lo, hi)], a[pick(lo, hi)], a[pick(lo, hi)]
            if lt(pivot, x):
                x, pivot = pivot, x
            if lt(z, pivot):                      # now x <= pivot; median is max(x, z)
                pivot = x if lt(z, x) else z
            i, k, j = lo, lo, hi                  # a[lo:i] < pivot, a[i:k] == pivot, a[j+1:hi+1] > pivot
            while k <= j:
                if lt(a[k], pivot):
                    a[i], a[k] = a[k], a[i]
                    i += 1
                    k += 1
                elif lt(pivot, a[k]):
                    a[k], a[j] = a[j], a[k]
                    j -= 1
                else:
                    k += 1
            if observer:
                observer({"type": "partition", "lo": lo, "hi": hi, "pivot": pivot,
                          "equal": (i, j), "items": list(a)})
            if i - lo < hi - j:                   # continue with the smaller side
                stack.append((j + 1, hi))
                hi = i - 1
            else:
                stack.append((lo, i - 1))
                lo = j + 1
    return _finish("quick_sort", a, count, observer)


def heap_sort(items: Iterable, less: Less = championship_less,
              observer: Observer | None = None) -> SortResult:
    """Heap sort: build a heap with the last-ranked element at the root, then
    repeatedly swap the root to the end of the shrinking prefix.

    Time O(n log n) in every case, in place on the copy (O(1) auxiliary).
    Not stable.
    """
    a = list(items)
    lt, count = counted(less, observer)

    def sift_down(i: int, size: int) -> None:
        while True:
            last = i
            for child in (2 * i + 1, 2 * i + 2):
                if child < size and lt(a[last], a[child]):
                    last = child
            if last == i:
                return
            a[i], a[last] = a[last], a[i]
            i = last

    n = len(a)
    for i in range(n // 2 - 1, -1, -1):
        sift_down(i, n)
    for end in range(n - 1, 0, -1):
        a[0], a[end] = a[end], a[0]
        if observer:
            observer({"type": "extract", "position": end, "item": a[end]})
        sift_down(0, end)
    return _finish("heap_sort", a, count, observer)

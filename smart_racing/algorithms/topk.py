"""Top-k retrieval with a size-k heap built on the hand-written MinHeap."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from smart_racing.algorithms.heap import MinHeap
from smart_racing.algorithms.sorting import Less, championship_less, counted

Observer = Callable[[dict], None]


@dataclass
class TopKResult:
    items: list            # the best min(k, n) items, best first
    k: int
    comparisons: int       # comparator calls
    heap_ops: int          # heap pushes + pops


def top_k(items: Iterable, k: int, less: Less = championship_less,
          observer: Observer | None = None) -> TopKResult:
    """Best `k` items in ranking order, equal to the first k of a stable full sort.

    The heap holds the best k items seen so far with the worst of them at the
    root. A new item enters only if it ranks strictly ahead of that root, and
    then replaces it with one sift. Items the comparator cannot separate are
    ordered by input position, so the result matches `merge_sort(items)[:k]`
    for any comparator.

    Time O(n log k), space O(k). `k <= 0` gives an empty list, `k > n` all items.
    """
    lt, count = counted(less)

    def worse(x: tuple, y: tuple) -> bool:      # heap order on (input index, item): worst first
        if lt(y[1], x[1]):
            return True
        if lt(x[1], y[1]):
            return False
        return x[0] > y[0]

    heap = MinHeap(worse)
    for index, item in enumerate(items if k > 0 else ()):
        if len(heap) < k:
            heap.push((index, item))
            kept = True
        else:
            kept = lt(item, heap.peek()[0][1])
            if kept:
                heap.replace((index, item))
        if observer:
            observer({"type": "offer", "index": index, "item": item, "kept": kept,
                      "worst_kept": heap.peek()[0][1]})
    out = []
    while heap:
        out.append(heap.pop()[0][1])
    out.reverse()                               # popped worst first
    res = TopKResult(out, k, count[0], heap.ops)
    if observer:
        observer({"type": "done", "items": list(out), "comparisons": res.comparisons})
    return res

"""Hand-written binary min-heap (no heapq)."""
from __future__ import annotations

from typing import Any, Callable


class MinHeap:
    """Array-backed binary min-heap of `(key, payload)` entries.

    Keys are any mutually comparable values (numbers, tuples). An optional
    `less(a, b)` replaces `<` on keys. Entries with equal keys leave in
    insertion order, and payloads are never compared, so behaviour is fully
    deterministic.

    push, pop and replace are O(log n); peek and len are O(1); space is O(n).
    Counters: `pushes`, `pops`, `comparisons` (key comparisons), `swaps`.
    """

    def __init__(self, less: Callable[[Any, Any], bool] | None = None) -> None:
        self._items: list[tuple[Any, int, Any]] = []   # (key, sequence, payload)
        self._less = less
        self._sequence = 0
        self.pushes = self.pops = self.comparisons = self.swaps = 0

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    @property
    def ops(self) -> int:
        """Number of push and pop operations performed."""
        return self.pushes + self.pops

    def push(self, key: Any, payload: Any = None) -> None:
        self.pushes += 1
        self._items.append((key, self._sequence, payload))
        self._sequence += 1
        self._sift_up(len(self._items) - 1)

    def peek(self) -> tuple[Any, Any]:
        if not self._items:
            raise IndexError("peek from an empty heap")
        key, _, payload = self._items[0]
        return key, payload

    def pop(self) -> tuple[Any, Any]:
        """Remove and return the smallest `(key, payload)`."""
        if not self._items:
            raise IndexError("pop from an empty heap")
        self.pops += 1
        key, _, payload = self._items[0]
        last = self._items.pop()
        if self._items:
            self._items[0] = last
            self._sift_down(0)
        return key, payload

    def replace(self, key: Any, payload: Any = None) -> tuple[Any, Any]:
        """Pop the smallest entry and push a new one with a single sift."""
        if not self._items:
            raise IndexError("replace on an empty heap")
        self.pops += 1
        self.pushes += 1
        old_key, _, old_payload = self._items[0]
        self._items[0] = (key, self._sequence, payload)
        self._sequence += 1
        self._sift_down(0)
        return old_key, old_payload

    def _before(self, i: int, j: int) -> bool:
        a, b = self._items[i], self._items[j]
        self.comparisons += 1
        if self._less is None:
            if a[0] == b[0]:
                return a[1] < b[1]
            return a[0] < b[0]
        if self._less(a[0], b[0]):
            return True
        if self._less(b[0], a[0]):
            return False
        return a[1] < b[1]

    def _swap(self, i: int, j: int) -> None:
        self.swaps += 1
        self._items[i], self._items[j] = self._items[j], self._items[i]

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if not self._before(i, parent):
                break
            self._swap(i, parent)
            i = parent

    def _sift_down(self, i: int) -> None:
        size = len(self._items)
        while True:
            smallest = i
            for child in (2 * i + 1, 2 * i + 2):
                if child < size and self._before(child, smallest):
                    smallest = child
            if smallest == i:
                return
            self._swap(i, smallest)
            i = smallest

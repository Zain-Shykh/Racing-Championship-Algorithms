import random

import pytest

from smart_racing.algorithms.heap import MinHeap


def drain(heap):
    out = []
    while heap:
        out.append(heap.pop())
    return out


def test_empty_heap():
    heap = MinHeap()
    assert len(heap) == 0 and not heap
    for call in (heap.pop, heap.peek, lambda: heap.replace(1)):
        with pytest.raises(IndexError):
            call()


def test_pops_in_sorted_order():
    rng = random.Random(1)
    values = [rng.randint(0, 50) for _ in range(300)]
    heap = MinHeap()
    for v in values:
        heap.push(v, f"p{v}")
    assert heap.peek()[0] == min(values) and len(heap) == 300
    assert [k for k, _ in drain(heap)] == sorted(values)


def test_tuple_keys_like_event_queue():
    heap = MinHeap()
    for key in [(5.0, 2, 0), (5.0, 1, 1), (1.0, 6, 2), (5.0, 1, 3)]:
        heap.push(key, key[2])
    assert [p for _, p in drain(heap)] == [2, 1, 3, 0]


def test_equal_keys_are_fifo_and_payloads_never_compared():
    heap = MinHeap()
    for i in range(20):
        heap.push(i % 2, {"n": i})                 # dicts are not orderable
    assert [p["n"] for _, p in drain(heap)] == list(range(0, 20, 2)) + list(range(1, 20, 2))


def test_custom_less_gives_max_heap():
    heap = MinHeap(less=lambda a, b: a > b)
    for v in [3, 9, 1, 9, 4]:
        heap.push(v)
    assert [k for k, _ in drain(heap)] == [9, 9, 4, 3, 1]


def test_replace_keeps_k_largest():
    heap = MinHeap()
    values = [7, 2, 9, 4, 11, 5, 1, 8]
    for v in values[:3]:
        heap.push(v)
    for v in values[3:]:
        if v > heap.peek()[0]:
            heap.replace(v)
    assert [k for k, _ in drain(heap)] == [8, 9, 11]


def test_counters_and_log_bound():
    heap = MinHeap()
    n = 1024
    for v in range(n, 0, -1):                      # worst case for sift-up
        heap.push(v)
    assert heap.pushes == n and heap.comparisons <= n * 10
    drain(heap)
    assert (heap.pops, heap.ops) == (n, 2 * n)
    assert heap.comparisons <= n * 10 + 2 * n * 10 and heap.swaps > 0


def test_deterministic_counters():
    def run():
        rng = random.Random(7)
        heap = MinHeap()
        for _ in range(200):
            heap.push((rng.randint(0, 5), rng.randint(0, 5)))
            if rng.random() < 0.3:
                heap.pop()
        return drain(heap), heap.comparisons, heap.swaps
    assert run() == run()

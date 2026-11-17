"""Experiment 4: the race event priority queue (Project.md section 7).

Run alone: `.venv/bin/python -m smart_racing.experiments.exp4_event_queue [--quick]`
"""
from __future__ import annotations

import math
import random

from smart_racing import config as C
from smart_racing.algorithms.heap import MinHeap
from smart_racing.core.graph import FUEL_STATION, NITRO_PICKUP, TrackGraph
from smart_racing.engine.events import EventQueue
from smart_racing.experiments import common as X

SIZES = [1000, 3000, 10000, 30000]
QUICK_SIZES = [100, 300]
RING = 64                          # roads 1..64 on a ring of 64 vertices
STATIONS = list(range(0, RING, 8))
PICKUP = 5                         # an inactive nitro pickup
# These three event types are never rejected on a valid target, so every live
# event is applied and `EventQueue.applied` is the complete pop order.
TYPES = (C.EVENT_OIL_SPILL, C.EVENT_SPEED_RESTRICTION, C.EVENT_STATION_OUTAGE)
SCENARIOS = ("distinct_times", "equal_times", "one_time_one_priority", "cancellations", "expirations")
CANCEL_SHARE = 0.3


def ring() -> TrackGraph:
    g = TrackGraph()
    for v in range(RING):
        kind = FUEL_STATION if v in STATIONS else NITRO_PICKUP if v == PICKUP else "Intersection"
        g.add_vertex(v, 100 * math.cos(2 * math.pi * v / RING), 100 * math.sin(2 * math.pi * v / RING),
                     kind, active=v != PICKUP)
    for v in range(RING):
        g.add_edge(v + 1, v, (v + 1) % RING, 10.0, is_shortcut=v == 0)
    return g


def make_specs(scenario: str, n: int, seed: str) -> tuple[list[tuple], set[int]]:
    """n events as (type, time, target, duration), and the positions to cancel."""
    rng = random.Random(seed)
    if scenario == "equal_times":
        times = [float(rng.randrange(10)) for _ in range(n)]          # 10 timestamps: priority and sequence ties
    elif scenario == "one_time_one_priority":
        times = [5.0] * n                                              # only the sequence differs
    else:
        times = [0.01 * i for i in range(n)]                           # all different, random order
        rng.shuffle(times)
    specs = []
    for t in times:
        kind = C.EVENT_OIL_SPILL if scenario == "one_time_one_priority" else rng.choice(TYPES)
        target = rng.choice(STATIONS) if kind == C.EVENT_STATION_OUTAGE else rng.randint(1, RING)
        specs.append((kind, t, target, None if scenario == "expirations" else math.inf))
    cancel = set(rng.sample(range(n), int(CANCEL_SHARE * n))) if scenario == "cancellations" else set()
    return specs, cancel


def insert(queue: EventQueue, specs: list[tuple]) -> EventQueue:
    for kind, t, target, duration in specs:
        queue.schedule(kind, t, target, duration)
    return queue


def heap_counts(heap: MinHeap, before=(0, 0, 0, 0)) -> dict:
    now = (heap.pushes, heap.pops, heap.comparisons, heap.swaps)
    names = ("heap_pushes", "heap_pops", "heap_comparisons", "heap_swaps")
    return {name: a - b for name, a, b in zip(names, now, before)}


def snapshot(heap: MinHeap) -> tuple:
    return heap.pushes, heap.pops, heap.comparisons, heap.swaps


def check_queue(scenario: str, queue: EventQueue, events: list, cancel: set[int]) -> None:
    """Pop order against (trigger_time, priority, insertion_sequence), computed
    here from the three fields with Python's sort, independently of the heap."""
    def key(e):
        return e.trigger_time, e.priority, e.insertion_sequence

    n = len(events)
    live = [e for i, e in enumerate(events) if i not in cancel]
    popped = [record.event for record in queue.applied]
    assert not queue.rejected and len(queue) == 0 and not queue.heap
    assert [key(e) for e in popped] == sorted(key(e) for e in popped)        # applied in key order
    assert not any(e.cancelled for e in popped)
    originals = [e for e in popped if e.type != C.EVENT_EXPIRE]
    assert [e.event_id for e in originals] == [e.event_id for e in sorted(live, key=key)]
    expiries = [e for e in popped if e.type == C.EVENT_EXPIRE]
    if scenario == "expirations":
        assert len(expiries) == n and queue.heap.pops == 2 * n
        wanted = sorted((e.trigger_time + C.EVENT_DURATION[e.type], e.priority, e.target) for e in events)
        assert sorted((e.trigger_time, e.priority, e.target) for e in expiries) == wanted
        assert all(not edge.effects for edge in queue.graph.edges())        # every effect was removed
        assert all(queue.graph.vertex(v).active for v in STATIONS)
    else:
        assert not expiries
        assert queue.heap.pops == n            # lazy deletion: cancelled entries are popped and skipped
        assert len(popped) == n - len(cancel)


def priority_check() -> list[dict]:
    """One event of every type at the same timestamp, scheduled in reverse
    priority order, plus two same-priority pairs: the pop order must follow
    priority, then insertion sequence."""
    queue = EventQueue(ring())
    order = [(C.EVENT_NITRO_SPAWN, PICKUP), (C.EVENT_STATION_OUTAGE, 8), (C.EVENT_SPEED_RESTRICTION, 3),
             (C.EVENT_OIL_SPILL, 4), (C.EVENT_SHORTCUT_CLOSE, 1), (C.EVENT_ROAD_BLOCK, 2),
             (C.EVENT_ROAD_BLOCK, 6), (C.EVENT_OIL_SPILL, 7)]
    for kind, target in order:
        queue.schedule(kind, 7.0, target, math.inf)
    late = queue.schedule(C.EVENT_ROAD_BLOCK, 3.0, 9, math.inf)       # earlier time, scheduled last
    doomed = queue.schedule(C.EVENT_ROAD_BLOCK, 1.0, 10, math.inf)
    assert queue.cancel(doomed.event_id) and not queue.cancel(doomed.event_id)
    done = queue.pop_due(math.inf)
    got = [(r.event.trigger_time, r.event.type, r.event.target) for r in done]
    assert got == [(3.0, C.EVENT_ROAD_BLOCK, 9), (7.0, C.EVENT_ROAD_BLOCK, 2), (7.0, C.EVENT_ROAD_BLOCK, 6),
                   (7.0, C.EVENT_SHORTCUT_CLOSE, 1), (7.0, C.EVENT_OIL_SPILL, 4), (7.0, C.EVENT_OIL_SPILL, 7),
                   (7.0, C.EVENT_SPEED_RESTRICTION, 3), (7.0, C.EVENT_STATION_OUTAGE, 8),
                   (7.0, C.EVENT_NITRO_SPAWN, PICKUP)], got
    assert not queue.rejected and late.event_id == done[0].event.event_id
    return [{"pop_position": i, "trigger_time": r.event.trigger_time, "priority": r.event.priority,
             "insertion_sequence": r.event.insertion_sequence, "type": r.event.type,
             "target": r.event.target} for i, r in enumerate(done, start=1)]


def run(cfg: X.Config) -> str:
    raw: list[dict] = []
    sizes = QUICK_SIZES if cfg.quick else SIZES
    for scenario in SCENARIOS:
        for n in sizes:
            specs, cancel = make_specs(scenario, n, f"{cfg.seed}-{scenario}-{n}")
            fields = {"scenario": scenario, "events": n, "cancelled": len(cancel)}

            # the real EventQueue ---------------------------------------------------
            def loaded():
                queue = insert(EventQueue(ring()), specs)
                events = queue.pending()                 # untimed; n live events in key order
                events.sort(key=lambda e: e.event_id)    # back to scheduling order
                for i in cancel:
                    queue.cancel(events[i].event_id)
                return queue, events, snapshot(queue.heap)

            X.record(raw, cfg, {**fields, "structure": "event_queue", "operation": "insert"},
                     lambda queue: insert(queue, specs), lambda queue: heap_counts(queue.heap),
                     setup=lambda: EventQueue(ring()))

            def drain(arg):
                arg[0].pop_due(math.inf)
                return arg

            queue, events, before = X.record(
                raw, cfg, {**fields, "structure": "event_queue", "operation": "extract"}, drain,
                lambda arg: heap_counts(arg[0].heap, arg[2]), setup=loaded)
            check_queue(scenario, queue, events, cancel)

            if scenario != "distinct_times":
                continue
            # the bare MinHeap on the same keys (no event application) ---------------
            keys = [e.key for e in events]

            def push_all(heap):
                for k in keys:
                    heap.push(k)
                return heap

            def pop_all(arg):
                heap, out = arg[0], []
                while heap:
                    out.append(heap.pop()[0])
                return heap, arg[1], out

            X.record(raw, cfg, {**fields, "structure": "min_heap", "operation": "insert"},
                     push_all, heap_counts, setup=MinHeap)

            def full_heap():
                heap = push_all(MinHeap())
                return heap, snapshot(heap)

            heap, before, out = X.record(
                raw, cfg, {**fields, "structure": "min_heap", "operation": "extract"}, pop_all,
                lambda arg: heap_counts(arg[0], arg[1]), setup=full_heap)
            assert out == sorted(keys)
    order_rows = priority_check()
    X.write_csv(cfg.out / "exp4_order_check.csv", order_rows)

    summary = X.save_tables(cfg, "exp4", raw)
    for row in summary:
        ops = row["heap_pushes"] if row["operation"] == "insert" else row["heap_pops"]
        row["us_per_heap_op"] = row["median_ms"] * 1000.0 / ops
        row["comparisons_per_heap_op"] = row["heap_comparisons"] / ops
    X.write_csv(cfg.out / "exp4_summary.csv", summary)

    fig, (left, right) = X.new_axes("Experiment 4: event queue", "n (events scheduled)",
                                    "median time per heap operation (microseconds)", ncols=2)
    index = 0
    for structure in ("event_queue", "min_heap"):
        for operation in ("insert", "extract"):
            rows = X.pick(summary, scenario="distinct_times", structure=structure, operation=operation)
            X.series(left, [r["events"] for r in rows], [r["us_per_heap_op"] for r in rows], index,
                     f"{structure} {operation}")
            index += 1
    left.set_title("Scenario distinct_times: time per operation", fontsize=10)
    for i, scenario in enumerate(SCENARIOS):
        rows = X.pick(summary, scenario=scenario, structure="event_queue", operation="extract")
        X.series(right, [r["events"] for r in rows], [r["comparisons_per_heap_op"] for r in rows], i, scenario)
    ns = [r["events"] for r in X.pick(summary, scenario="distinct_times", structure="event_queue", operation="extract")]
    right.plot(ns, [2 * math.log2(n) for n in ns], color="#6b6a63", linestyle="--", linewidth=1,
               label="2 log2 n (sift-down bound)")
    right.set_title("EventQueue extraction: key comparisons per pop", fontsize=10)
    right.set_ylabel("heap comparisons per pop")
    for ax in (left, right):
        ax.set_xscale("log")
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8)
    X.save_fig(fig, cfg, "exp4_event_queue.png")

    columns = ["scenario", "events", "cancelled", "operation", "heap_pushes", "heap_pops",
               "heap_comparisons", "heap_swaps", "mean_ms", "median_ms", "stdev_ms", "us_per_heap_op",
               "comparisons_per_heap_op"]
    queue_rows = X.pick(summary, structure="event_queue")
    heap_rows = X.pick(summary, structure="min_heap", scenario="distinct_times")

    def cell(scenario, operation, n, column, structure="event_queue"):
        return X.pick(summary, scenario=scenario, structure=structure, operation=operation, events=n)[0][column]

    lo, hi = sizes[0], sizes[-1]
    lines = "\n".join(
        f"- {s}: comparisons per pop {cell(s, 'extract', lo, 'comparisons_per_heap_op'):.1f} at n = {lo:,} and "
        f"{cell(s, 'extract', hi, 'comparisons_per_heap_op'):.1f} at n = {hi:,} (2 log2 n = "
        f"{2 * math.log2(lo):.1f} and {2 * math.log2(hi):.1f}); comparisons per push "
        f"{cell(s, 'insert', lo, 'comparisons_per_heap_op'):.2f} and {cell(s, 'insert', hi, 'comparisons_per_heap_op'):.2f}; "
        f"time per pop {cell(s, 'extract', lo, 'us_per_heap_op'):.2f} and {cell(s, 'extract', hi, 'us_per_heap_op'):.2f} "
        f"microseconds." for s in SCENARIOS)
    return f"""## Experiment 4: event priority queue

**Objective.** Measure insertion and extraction on the gameplay event queue
(`engine/events.py: EventQueue`, built on `algorithms/heap.py: MinHeap`) as the number of events
grows, and verify that events leave in (trigger_time, priority, insertion_sequence) order with
equal timestamps, priority ties, sequence ties, cancellations and expirations.

**Environment.** {X.env_line(cfg)}

**Input generation.** Track: a ring of {RING} vertices and {RING} two-way roads with {len(STATIONS)} fuel stations.
Events from `random.Random("{cfg.seed}-<scenario>-<n>")`: type drawn from oil spill (priority 3),
speed restriction (4) and station outage (5), which are never rejected on a valid target, so
every live event is applied and the applied list is the full pop order. Scenarios:
`distinct_times` n different timestamps in random order, no expiry; `equal_times` only 10
different timestamps, so priority and then sequence decide; `one_time_one_priority` all oil
spills at t = 5, so only the insertion sequence decides; `cancellations` = distinct times with
{CANCEL_SHARE:.0%} of the events cancelled before extraction; `expirations` = distinct times with the default
durations (20 s, 15 s, 30 s), so each applied event schedules an expiry during extraction.

**Dataset sizes.** n in {sizes} scheduled events per scenario.

**Procedure.** Insert: a new `EventQueue` on a new track is created outside the timed call; the
timed call schedules the n events (`schedule`), so it includes creating each `Event` record and
the heap push, not queue construction. Extract: the queue is filled (and cancellations applied)
outside the timed call; the timed call is `pop_due(inf)`, which pops every entry and applies each
live event to the track, so it includes event application and, in `expirations`, the n extra
pushes and pops of the expiries. To separate the heap from event handling, the keys of
`distinct_times` are also pushed to and popped from a bare `MinHeap`. Checks after timing: the applied events are in
ascending (time, priority, sequence) order and equal the list obtained by sorting the live events
with Python's sort on those three fields; no cancelled event is applied; with cancellations all n
entries are still popped (lazy deletion); with expirations there is exactly one expiry per event
at trigger + duration with the same priority and target, and afterwards no road carries an
effect and every station is active; the bare heap returns its keys in sorted order. A fixed case
(`exp4_order_check.csv`) schedules one event of each of the six types plus two same-priority
pairs at one timestamp in reverse priority order, an earlier event last and a cancelled event,
and requires the exact pop order. All checks passed.

**Metrics.** Runtime (ms) and time per heap operation; heap pushes, pops, key comparisons and
swaps during the timed call.

**Results.** Raw runs: `exp4_raw.csv`; aggregates: `exp4_summary.csv`; fixed order case:
`exp4_order_check.csv`; chart: `exp4_event_queue.png`. EventQueue:

{X.md_table(queue_rows, columns)}

Bare MinHeap on the keys of `distinct_times`:

{X.md_table(heap_rows, columns)}

**Interpretation.** Pop order was correct in every scenario and size. Counters:

{lines}

Comparisons per pop grew by a roughly constant amount each time n was multiplied, and stayed
below 2 log2 n, as O(log n) extraction predicts. Comparisons per push stayed small and nearly
constant at every n: a push only climbs while the new key is smaller than its parent. When keys
arrive in increasing order (`one_time_one_priority`, where only the sequence grows) that never
happens: one comparison and no swap per push. So the O(log n) bound for insertion is a worst
case that these inputs do not reach. Cancelled events are still popped: `cancellations` shows the same number of
pops as `distinct_times` for the same n. `expirations` performs 2n pops and n extra pushes
during extraction. On `distinct_times` at n = {hi:,} the real queue needed
{cell('distinct_times', 'extract', hi, 'us_per_heap_op'):.2f} microseconds per pop and {cell('distinct_times', 'insert', hi, 'us_per_heap_op'):.2f} per insertion against {cell('distinct_times', 'extract', hi, 'us_per_heap_op', 'min_heap'):.2f} and
{cell('distinct_times', 'insert', hi, 'us_per_heap_op', 'min_heap'):.2f} for the bare heap on the same keys (identical comparison counts): the difference is
the cost of creating the event record and of applying the event to the track.

**Limitations.** Three of the six event types in the timed scenarios (the others can be
rejected, which would hide part of the pop order; all six are covered by the fixed case).
Extraction is one batch `pop_due(inf)`, while a race pops a few events per tick. One event list
per (scenario, n). Per-operation times of a few microseconds are sensitive to interpreter and
cache effects. Lazy cancellation keeps dead entries in the heap; their memory cost is not measured.

**Conclusion.** The event queue released events in exact (trigger_time, priority,
insertion_sequence) order under ties, cancellations and expirations. Its comparison counts per
extraction grew logarithmically with n and insertion stayed near constant on these inputs.
"""


if __name__ == "__main__":
    X.main(run, __doc__)

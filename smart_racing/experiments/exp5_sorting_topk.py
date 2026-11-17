"""Experiment 5: merge, quick and heap sort, and size-k heap top-k
(Project.md section 7).

Run alone: `.venv/bin/python -m smart_racing.experiments.exp5_sorting_topk [--quick]`
"""
from __future__ import annotations

import math
import random

from smart_racing.algorithms.sorting import championship_less, heap_sort, merge_sort, quick_sort
from smart_racing.algorithms.topk import top_k
from smart_racing.core.models import ChampionshipEntry
from smart_racing.experiments import common as X

SORTS = {"merge_sort": merge_sort, "quick_sort": quick_sort, "heap_sort": heap_sort}
SHAPES = ("random", "sorted", "reverse_sorted", "duplicate_heavy")
SIZES = [1000, 2500, 5000, 10000, 20000, 50000]
TOPK_SIZES = [2000, 10000]
QUICK_SIZES = [50, 200]


def rank_key(e: ChampionshipEntry) -> tuple:
    """The ranking of Project.md 4.6 written as a sort key. Used only to build
    the reference order with Python's sort, independently of the algorithms."""
    return -e.total_points, -e.wins, e.sum_of_finish_positions, e.best_fastest_lap, e.racer_id


def entries(shape: str, n: int, seed: str) -> list[ChampionshipEntry]:
    rng = random.Random(seed)
    if shape == "duplicate_heavy":      # 12 distinct key combinations: most pairs fall to the racer id
        out = [ChampionshipEntry(i, rng.choice([0, 25, 50]), rng.choice([0, 1]), 10, rng.choice([70.0, 80.0]))
               for i in range(1, n + 1)]
    else:
        out = [ChampionshipEntry(i, rng.randint(0, 780), rng.randint(0, 30), rng.randint(30, 300),
                                 round(rng.uniform(60.0, 120.0), 3)) for i in range(1, n + 1)]
    rng.shuffle(out)
    if shape in ("sorted", "reverse_sorted"):
        out.sort(key=rank_key, reverse=shape == "reverse_sorted")     # input preparation, not ranking code
    return out


def ids(items) -> list[int]:
    return [e.racer_id for e in items]


def check_ranking(items, reference) -> None:
    assert ids(items) == ids(reference)
    assert all(championship_less(a, b) and not championship_less(b, a) for a, b in zip(items, items[1:]))


def run(cfg: X.Config) -> str:
    raw: list[dict] = []
    sizes = QUICK_SIZES if cfg.quick else SIZES
    for shape in SHAPES:
        for n in sizes:
            data = entries(shape, n, f"{cfg.seed}-{shape}-{n}")
            before = ids(data)
            reference = sorted(data, key=rank_key)
            for name, sort in SORTS.items():                      # same list object for the three sorts
                result = X.record(
                    raw, cfg, {"part": "sort", "shape": shape, "n": n, "k": "", "algorithm": name,
                               "n_log2_n": n * math.log2(n)},
                    lambda sort=sort: sort(data), lambda r: {"comparisons": r.comparisons})
                check_ranking(result.items, reference)
            assert ids(data) == before                            # sorts leave the input untouched

    topk_sizes = QUICK_SIZES[-1:] if cfg.quick else TOPK_SIZES
    for n in topk_sizes:
        data = entries("random", n, f"{cfg.seed}-topk-{n}")
        reference = sorted(data, key=rank_key)
        fields = {"part": "topk", "shape": "random", "n": n}
        for name, sort in SORTS.items():
            result = X.record(raw, cfg, {**fields, "k": n, "algorithm": name, "n_log2_n": n * math.log2(n)},
                              lambda sort=sort: sort(data), lambda r: {"comparisons": r.comparisons})
            check_ranking(result.items, reference)
        for k in sorted({1, 3, 10, 100, n // 10, n // 2, n - 10, n}):
            result = X.record(raw, cfg, {**fields, "k": k, "algorithm": "top_k", "n_log2_n": n * math.log2(n)},
                              lambda k=k: top_k(data, k),
                              lambda r: {"comparisons": r.comparisons, "heap_ops": r.heap_ops})
            assert ids(result.items) == ids(reference[:k])        # top-k = first k of the full ranking
            assert ids(result.items) == ids(merge_sort(data).items[:k])
    one = [ChampionshipEntry(7, 10)]                              # edge cases, untimed
    assert all(ids(sort(one).items) == [7] and not sort([]).items for sort in SORTS.values())
    assert ids(top_k(one, 3).items) == [7] and top_k(one, 0).items == []

    summary = X.save_tables(cfg, "exp5", raw)
    for row in summary:
        row["comparisons_per_n_log2_n"] = row["comparisons"] / row["n_log2_n"]
    X.write_csv(cfg.out / "exp5_summary.csv", summary)

    fig, axes = X.plt.subplots(1, 4, figsize=(16, 4.4), sharey=True)
    for ax, shape in zip(axes, SHAPES):
        for i, name in enumerate(SORTS):
            rows = X.pick(summary, part="sort", shape=shape, algorithm=name)
            X.series(ax, [r["n_log2_n"] for r in rows], [r["median_ms"] for r in rows], i, name)
        ax.set_title(shape, fontsize=10)
        ax.set_xlabel("n x log2(n)")
        ax.grid(True, color="#e3e2dc", linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("median runtime (ms)")
    axes[0].legend()
    fig.suptitle(f"Experiment 5: sort runtime against the n log n term, n = {sizes[0]:,} to {sizes[-1]:,} entries",
                 fontsize=12)
    X.save_fig(fig, cfg, "exp5_sorts.png")

    n_top = topk_sizes[-1]
    fig, (left, right) = X.new_axes(f"Experiment 5: size-k heap top-k against full sorting, n = {n_top:,} random entries",
                                    "k (entries requested, log scale)", "median runtime (ms)", ncols=2)
    tk = X.pick(summary, part="topk", n=n_top, algorithm="top_k")
    for ax, column in ((left, "median_ms"), (right, "comparisons")):
        X.series(ax, [r["k"] for r in tk], [r[column] for r in tk], 0, "top_k (size-k heap)")
        for i, name in enumerate(SORTS, start=1):
            full = X.pick(summary, part="topk", n=n_top, algorithm=name)[0]
            ax.axhline(full[column], color=X.COLORS[i], linestyle="--", linewidth=1.5, label=f"{name} (full sort)")
        ax.set_xscale("log")
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8)
    left.set_title("Runtime", fontsize=10)
    right.set_title("Comparator calls", fontsize=10)
    right.set_ylabel("comparisons")
    X.save_fig(fig, cfg, "exp5_topk.png")

    top_n = sizes[-1]
    columns = ["shape", "n", "algorithm", "comparisons", "comparisons_per_n_log2_n", "mean_ms", "median_ms", "stdev_ms"]
    sort_rows = X.pick(summary, part="sort")
    growth = []
    for name in SORTS:
        rows = X.pick(sort_rows, shape="random", algorithm=name)
        lo, hi = rows[0], rows[-1]
        growth.append(
            f"- {name}: n log2 n grew {hi['n_log2_n'] / lo['n_log2_n']:.1f}x, comparisons "
            f"{hi['comparisons'] / lo['comparisons']:.1f}x ({lo['comparisons']:,} to {hi['comparisons']:,}), median time "
            f"{hi['median_ms'] / lo['median_ms']:.1f}x ({lo['median_ms']:.2f} ms to {hi['median_ms']:.1f} ms); comparisons per "
            f"n log2 n between {min(r['comparisons_per_n_log2_n'] for r in rows):.2f} and "
            f"{max(r['comparisons_per_n_log2_n'] for r in rows):.2f}.")
    shapes_text = []
    for shape in SHAPES:
        rows = {r["algorithm"]: r for r in X.pick(sort_rows, shape=shape, n=top_n)}
        fastest = min(rows.values(), key=lambda r: r["median_ms"])
        shapes_text.append(
            f"- {shape}: " + ", ".join(f"{name} {r['comparisons']:,} comparisons / {r['median_ms']:.1f} ms"
                                        for name, r in rows.items()) + f". Lowest median time: {fastest['algorithm']}.")
    def pct(shape):
        count = {sh: X.pick(sort_rows, shape=sh, n=top_n, algorithm="merge_sort")[0]["comparisons"]
                 for sh in (shape, "random")}
        return 100.0 * count[shape] / count["random"]

    merge_full = X.pick(summary, part="topk", n=n_top, algorithm="merge_sort")[0]
    faster = [r["k"] for r in tk if r["median_ms"] < merge_full["median_ms"]]
    fewer = [r["k"] for r in tk if r["comparisons"] < merge_full["comparisons"]]
    return f"""## Experiment 5: sorting and top-k

**Objective.** Compare the gameplay ranking sorts (`algorithms/sorting.py`: `merge_sort`,
`quick_sort`, `heap_sort`) on runtime and comparison count for four input shapes, and compare
full sorting with the size-k heap `algorithms/topk.py: top_k` for small k and k close to n. All
of them use the one comparator `championship_less`.

**Environment.** {X.env_line(cfg)}

**Input generation.** `ChampionshipEntry` lists from `random.Random("{cfg.seed}-<shape>-<n>")` with
unique racer ids 1..n. `random`: points 0..780, wins 0..30, sum of positions 30..300, best lap
60..120 s (3 decimals), shuffled. `sorted`: the same kind of list already in ranking order.
`reverse_sorted`: in reverse ranking order. `duplicate_heavy`: points from (0, 25, 50), wins from
(0, 1), one sum of positions and two lap times, so only 12 distinct key combinations exist and
most comparisons are decided by the final racer-id tie-break. Top-k uses a separate random list.

**Dataset sizes.** Sorts: n in {sizes} for each of the 4 shapes. Top-k: n in {topk_sizes} with
k in (1, 3, 10, 100, n/10, n/2, n - 10, n).

**Procedure.** The three sorts receive the same list object (they return a new list and do not
modify the input, which is checked). The timed call is the whole sort or `top_k` call, including
the copy of the input list each sort makes and, for top-k, building the heap and emitting the k
results in order. After timing: each ranking must equal the reference order built with Python's
`sorted` on the ranking written as a key tuple, and every adjacent pair must satisfy
`championship_less(a, b)` and not `championship_less(b, a)`; each top-k result must equal the
first k entries of the reference and of `merge_sort`. Single-element and empty inputs are checked
untimed. All checks passed.

**Metrics.** Runtime (ms), comparator calls (`comparisons`), and for top-k heap operations.

**Results.** Raw runs: `exp5_raw.csv`; aggregates: `exp5_summary.csv`; charts: `exp5_sorts.png`,
`exp5_topk.png`. Sorts at n = {top_n:,}:

{X.md_table([r for r in sort_rows if r["n"] == top_n], columns)}

Sorts on random input at every n:

{X.md_table(X.pick(sort_rows, shape="random"), columns)}

Top-k and full sorts on the same random lists:

{X.md_table(X.pick(summary, part="topk"), ["n", "k", "algorithm", "comparisons", "heap_ops", "mean_ms", "median_ms", "stdev_ms"])}

**Interpretation.** All three sorts produced the same ranking on every input, and it matched the
reference. Growth on random input:

{chr(10).join(growth)}

For each sort the comparison count divided by n log2 n stayed within the narrow range shown,
which is what an O(n log n) comparison count looks like over this range; runtime grew by a similar
factor (merge and heap sort somewhat more than n log2 n, quick sort about the same). By input shape at n = {top_n:,}:

{chr(10).join(shapes_text)}

Merge sort needed fewer comparisons on sorted and reverse-sorted input ({pct('sorted'):.0f}% and
{pct('reverse_sorted'):.0f}% of its random-input count), because each merge exhausts one run early; heap sort's
count changed little with input order. Quick sort did not degrade on sorted or reverse-sorted
input (median of three pseudo-random positions as pivot). On duplicate-heavy input its count was
about the same as on random input: the racer-id tie-break makes every pair of entries distinct
under the comparator, so the three-way partition finds no run of equal entries to skip.
Top-k at n = {n_top:,}: it used fewer comparisons than a full merge sort
({merge_full['comparisons']:,}) for k in {fewer} and had a lower median time than merge sort ({merge_full['median_ms']:.1f} ms)
for k in {faster}. For small k the heap is cheap because most entries are rejected after one
comparison with the worst kept entry; for k close to n it is more expensive than sorting, since
every heap step calls the comparator up to twice per level to settle ties by input position.

**Limitations.** n up to {top_n:,} only, to keep the full run short in pure Python (the sorts
handle larger inputs). One list per (shape, n). Runtime includes the Python-level comparator
call, which dominates; a different comparator would shift all three sorts. The quick sort worst
case O(n^2) is not exercised, because the pivot positions are pseudo-random.

**Conclusion.** Merge, quick and heap sort agree with each other and with the common comparator
on all shapes, with comparison counts that track n log n. A size-k heap is the cheaper way to get
the leaders when k is small relative to n, and a full sort is cheaper when k approaches n.
"""


if __name__ == "__main__":
    X.main(run, __doc__)

"""Experiment 3: 0/1 knapsack by DP, greedy ratio and exhaustive search
(Project.md section 7).

Run alone: `.venv/bin/python -m smart_racing.experiments.exp3_knapsack [--quick]`
"""
from __future__ import annotations

import random

from smart_racing.algorithms.knapsack import Item, knapsack_dp, knapsack_exhaustive, knapsack_greedy
from smart_racing.experiments import common as X

ALGORITHMS = {"dp": knapsack_dp, "greedy": knapsack_greedy, "exhaustive": knapsack_exhaustive}

# name -> (budget, [(cost, benefit)]); item ids are 1, 2, 3, ... in list order.
NAMED = {
    "brief A/B/C": (10, [(6, 30), (5, 24), (5, 24)]),
    "team 1: small best-ratio item blocks the big one": (10, [(1, 2), (10, 10)]),
    "team 2: one ratio leader wastes budget": (12, [(5, 10), (4, 7), (4, 7), (4, 7)]),
    "team 3: classic 10/20/30": (50, [(10, 60), (20, 100), (30, 120)]),
}
SMALL_M = [8, 12, 16, 18]                  # exhaustive search is feasible
SCALE_M = [25, 50, 100, 200, 400]
SCALE_B = [250, 500, 1000, 2000, 4000]


def random_items(m: int, max_cost: int, seed: str) -> list[Item]:
    rng = random.Random(seed)
    return [Item(i, rng.randint(1, max_cost), rng.randint(10, 100)) for i in range(1, m + 1)]


def counters(r) -> dict:
    return {"benefit": r.total_benefit, "total_cost": r.total_cost, "n_selected": len(r.selected),
            "states": r.states, "selected": " ".join(map(str, r.selected))}


def check(items, budget, results: dict) -> None:
    by_id = {item.id: item for item in items}
    for r in results.values():                                  # every answer is feasible and consistent
        assert len(set(r.selected)) == len(r.selected)
        assert r.total_cost == sum(by_id[i].cost for i in r.selected) <= budget
        assert r.total_benefit == sum(by_id[i].benefit for i in r.selected)
    assert results["greedy"].total_benefit <= results["dp"].total_benefit
    assert results["dp"].states == len(items) * (budget + 1)
    if "exhaustive" in results:
        assert results["dp"].total_benefit == results["exhaustive"].total_benefit
        assert results["exhaustive"].states == 2 ** len(items)


def gap(dp_benefit: float, greedy_benefit: float) -> float:
    return 100.0 * (dp_benefit - greedy_benefit) / dp_benefit if dp_benefit else 0.0


def run(cfg: X.Config) -> str:
    raw: list[dict] = []
    comparison: list[dict] = []

    def measure(part, case, items, budget, names):
        results = {}
        for name in names:                                       # same item list and budget for all
            results[name] = X.record(
                raw, cfg, {"part": part, "case": case, "items": len(items), "budget": budget,
                           "algorithm": name},
                lambda fn=ALGORITHMS[name]: fn(items, budget), counters)
        check(items, budget, results)
        dp, greedy = results["dp"], results["greedy"]
        comparison.append({
            "part": part, "case": case, "items": len(items), "budget": budget,
            "dp_benefit": dp.total_benefit, "greedy_benefit": greedy.total_benefit,
            "exhaustive_benefit": results["exhaustive"].total_benefit if "exhaustive" in results else "",
            "greedy_gap_pct": gap(dp.total_benefit, greedy.total_benefit),
            "dp_selected": " ".join(map(str, dp.selected)) if len(items) <= 20 else f"{len(dp.selected)} items",
            "greedy_selected": " ".join(map(str, greedy.selected)) if len(items) <= 20 else f"{len(greedy.selected)} items",
            "dp_states": dp.states})
        return results

    for case, (budget, pairs) in NAMED.items():
        items = [Item(i, c, b) for i, (c, b) in enumerate(pairs, start=1)]
        results = measure("named", case, items, budget, ALGORITHMS)
        assert results["greedy"].total_benefit < results["dp"].total_benefit      # strictly worse
    for m in ([6, 8] if cfg.quick else SMALL_M):
        items = random_items(m, 30, f"{cfg.seed}-small-{m}")
        measure("small", f"random m={m}", items, sum(item.cost for item in items) // 2, ALGORITHMS)
    for m in ([10, 20] if cfg.quick else SCALE_M):
        for budget in ([50, 100] if cfg.quick else SCALE_B):
            # costs up to 4B/m: the item costs sum to about twice the budget
            items = random_items(m, max(2, 4 * budget // m), f"{cfg.seed}-scale-{m}-{budget}")
            measure("scale", f"random m={m} B={budget}", items, budget, ("dp", "greedy"))

    # Untimed sweep: DP against exhaustive search and the greedy gap on many small instances.
    rng = random.Random(cfg.seed)
    sweep = []
    for i in range(30 if cfg.quick else 500):
        m = rng.randint(4, 12)
        items = random_items(m, 30, f"{cfg.seed}-sweep-{i}")
        budget = rng.randint(10, max(10, sum(item.cost for item in items) * 2 // 3))
        results = {name: fn(items, budget) for name, fn in ALGORITHMS.items()}
        check(items, budget, results)
        sweep.append({"instance": i, "items": m, "budget": budget,
                      "dp_benefit": results["dp"].total_benefit,
                      "exhaustive_benefit": results["exhaustive"].total_benefit,
                      "greedy_benefit": results["greedy"].total_benefit,
                      "greedy_gap_pct": gap(results["dp"].total_benefit, results["greedy"].total_benefit)})

    summary = X.save_tables(cfg, "exp3", raw)
    for row in comparison:
        for name in ALGORITHMS:
            found = X.pick(summary, part=row["part"], case=row["case"], algorithm=name)
            row[f"{name}_median_ms"] = found[0]["median_ms"] if found else ""
    X.write_csv(cfg.out / "exp3_comparison.csv", comparison)
    X.write_csv(cfg.out / "exp3_sweep.csv", sweep)

    fig, (left, right) = X.new_axes("Experiment 3: knapsack runtime", "DP states = m x (B + 1)",
                                    "DP median runtime (ms)", ncols=2)
    scale = X.pick(summary, part="scale", algorithm="dp")
    for i, m in enumerate(sorted({r["items"] for r in scale})):
        rows = X.pick(scale, items=m)
        X.series(left, [r["states"] for r in rows], [r["median_ms"] for r in rows], i, f"m = {m} items")
    left.set_title("DP runtime against the O(m B) term", fontsize=10)
    left.legend(fontsize=8)
    for i, name in enumerate(ALGORITHMS):
        rows = X.pick(summary, part="small", algorithm=name)
        X.series(right, [r["items"] for r in rows], [r["median_ms"] for r in rows], i, name)
    right.set_yscale("log")
    right.set_xlabel("m (items), budget = half the total cost")
    right.set_ylabel("median runtime (ms, log scale)")
    right.set_title("Small instances: exhaustive is 2^m", fontsize=10)
    right.legend()
    X.save_fig(fig, cfg, "exp3_runtime.png")

    named = X.pick(comparison, part="named")
    fig, ax = X.new_axes("Experiment 3: greedy against the DP optimum on the named cases",
                         "case", "total benefit")
    xs = range(len(named))
    ax.bar([x - 0.2 for x in xs], [r["dp_benefit"] for r in named], 0.38, color=X.COLORS[0], label="DP (optimal)")
    ax.bar([x + 0.2 for x in xs], [r["greedy_benefit"] for r in named], 0.38, color=X.COLORS[1], label="greedy")
    for x, r in zip(xs, named):
        ax.text(x - 0.2, r["dp_benefit"], f"{r['dp_benefit']:g}", ha="center", va="bottom", fontsize=9)
        ax.text(x + 0.2, r["greedy_benefit"], f"{r['greedy_benefit']:g}\n(gap {r['greedy_gap_pct']:.0f}%)",
                ha="center", va="bottom", fontsize=9)
    ax.set_xticks(list(xs), [r["case"].split(":")[0] for r in named])
    ax.set_ylim(top=max(r["dp_benefit"] for r in named) * 1.2)
    ax.grid(axis="x", visible=False)
    ax.legend()
    X.save_fig(fig, cfg, "exp3_greedy_gap.png")

    worse = [r for r in sweep if r["greedy_gap_pct"] > 0]
    scale_cmp = X.pick(comparison, part="scale")
    scale_worse = [r for r in scale_cmp if r["greedy_gap_pct"] > 0]
    per_state = [r["median_ms"] * 1e6 / r["states"] for r in scale]
    lo, hi = min(scale, key=lambda r: r["states"]), max(scale, key=lambda r: r["states"])
    small_ex = X.pick(summary, part="small", algorithm="exhaustive")
    small_dp = X.pick(summary, part="small", algorithm="dp")
    fastest = sum(1 for r in comparison if r["greedy_median_ms"] == min(
        r[f"{name}_median_ms"] for name in ALGORITHMS if r[f"{name}_median_ms"] != ""))
    items_text = "\n".join(
        f"- {case}: budget {budget}, items (cost, benefit) = {pairs}" for case, (budget, pairs) in NAMED.items())
    return f"""## Experiment 3: DP and greedy knapsack

**Objective.** Compare the gameplay 0/1 knapsack solvers (`algorithms/knapsack.py`:
`knapsack_dp`, `knapsack_greedy`, `knapsack_exhaustive`) on benefit, selected items, runtime and
state count; confirm DP against exhaustive search on small instances; measure how far greedy
falls short.

**Environment.** {X.env_line(cfg)}

**Input generation.** Named cases (item ids 1, 2, 3, ... in the order listed):

{items_text}

Random instances use `random.Random("{cfg.seed}-<part>-<parameters>")`, integer benefit 10..100.
Small part: integer cost 1..30, budget = half the total cost. Scale part: integer cost 1..4B/m,
so the costs sum to about twice the budget and the budget always binds. Sweep (untimed):
{len(sweep)} instances with 4 to 12 items, cost 1..30 and a random budget up to two thirds of the
total cost.

**Dataset sizes.** Named: 2 to 4 items. Small: m in {sorted({r['items'] for r in small_ex})} with all three
algorithms. Scale: m in {sorted({r['items'] for r in scale})} x B in {sorted({r['budget'] for r in scale})} with DP and greedy
(exhaustive search is refused above 22 items and would need 2^m subsets).

**Procedure.** All algorithms of a configuration receive the same item list and budget. The
timed call is the whole solver call: for DP it includes allocating the (m + 1) x (B + 1) table,
filling it and the traceback; for greedy the ratio sort; for exhaustive all 2^m subsets. After
timing: every selection is checked to be within budget and to add up to the reported cost and
benefit, DP benefit = exhaustive benefit wherever exhaustive ran, greedy benefit <= DP benefit,
and greedy is strictly worse on every named case. All checks passed.

**Metrics.** Total benefit, selected item ids, total cost, runtime (ms), state count (DP: table
cells filled = m (B + 1); greedy: items considered; exhaustive: subsets = 2^m), greedy optimality
gap = (DP benefit - greedy benefit) / DP benefit.

**Results.** Raw runs: `exp3_raw.csv`; aggregates: `exp3_summary.csv`; side by side:
`exp3_comparison.csv`; sweep: `exp3_sweep.csv`; charts: `exp3_runtime.png`, `exp3_greedy_gap.png`.

Named cases:

{X.md_table(named, ["case", "budget", "dp_benefit", "dp_selected", "greedy_benefit", "greedy_selected", "exhaustive_benefit", "greedy_gap_pct", "dp_states"])}

Small random instances (all three algorithms):

{X.md_table(X.pick(comparison, part="small"), ["items", "budget", "dp_benefit", "greedy_benefit", "exhaustive_benefit", "greedy_gap_pct", "dp_states", "dp_median_ms", "greedy_median_ms", "exhaustive_median_ms"])}

Scale part (DP and greedy):

{X.md_table(scale_cmp, ["items", "budget", "dp_benefit", "greedy_benefit", "greedy_gap_pct", "dp_states", "dp_median_ms", "greedy_median_ms"])}

**Interpretation.** DP matched exhaustive search on all {len(named) + len(small_ex)} timed instances where
exhaustive ran and on all {len(sweep)} sweep instances. Greedy was strictly worse on the supplied
example (30 against 48) and on the three team-created cases, with gaps of
{", ".join(f"{r['greedy_gap_pct']:.1f}%" for r in named)}. In the sweep greedy was suboptimal in {len(worse)} of
{len(sweep)} instances ({100 * len(worse) / len(sweep):.1f}%); over those the mean gap was
{sum(r['greedy_gap_pct'] for r in worse) / max(1, len(worse)):.2f}% and the largest {max((r['greedy_gap_pct'] for r in sweep), default=0):.2f}%. In the scale part it was
suboptimal in {len(scale_worse)} of {len(scale_cmp)} configurations, largest gap
{max(r['greedy_gap_pct'] for r in scale_cmp):.2f}%: with many small items relative to the budget the gap is small, the
large gaps come from few items of similar ratio that do not pack. DP runtime followed its state
count: from {lo['states']:,} states ({lo['median_ms']:.2f} ms) to {hi['states']:,} states ({hi['median_ms']:.1f} ms),
a {hi['states'] / lo['states']:.0f}x increase in states and {hi['median_ms'] / lo['median_ms']:.0f}x in time, between {min(per_state):.0f} and
{max(per_state):.0f} ns per state over all {len(scale)} configurations, which is consistent with O(m B). The work
grows with the numeric value of the budget, not with the length of the input (the rows for one m
show it), which is what pseudo-polynomial means. Exhaustive search went from {small_ex[0]['median_ms']:.3f} ms at m = {small_ex[0]['items']} to
{small_ex[-1]['median_ms']:.1f} ms at m = {small_ex[-1]['items']} ({small_ex[-1]['states']:,} subsets), while DP on the same
instances took {small_dp[0]['median_ms']:.3f} ms to {small_dp[-1]['median_ms']:.3f} ms. Greedy had the lowest median time in
{fastest} of the {len(comparison)} configurations.

**Limitations.** Benefits and costs are independent uniform integers, a distribution on which
ratio greedy is known to do well; the gap figures describe these inputs, not a worst case (the
named cases show the gap can be large). One instance per (m, B). The DP keeps the full table for
reconstruction, so memory also grows as m x B (not measured here). Exhaustive search only up to m = {small_ex[-1]['items']}.

**Conclusion.** DP returned the optimal benefit in every verified instance at a cost
proportional to m x B. Greedy is far cheaper and usually close on random inputs, but it is not
optimal: it lost {named[0]['greedy_gap_pct']:.1f}% on the brief's example and up to {max(r['greedy_gap_pct'] for r in named):.1f}% on the
team-created cases.
"""


if __name__ == "__main__":
    X.main(run, __doc__)

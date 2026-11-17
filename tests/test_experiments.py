"""Phase 7: every experiment runs in its quick configuration, its built-in
correctness assertions hold, and it writes raw data, a summary and charts."""
import csv

import pytest

from smart_racing.experiments import common as X
from smart_racing.experiments import exp4_event_queue, run_all

RUNS = 5
HEADINGS = ("**Objective.**", "**Environment.**", "**Input generation.**", "**Dataset sizes.**",
            "**Procedure.**", "**Metrics.**", "**Results.**", "**Interpretation.**",
            "**Limitations.**", "**Conclusion.**")


@pytest.fixture(scope="module")
def quick(tmp_path_factory):
    """One quick run of everything; an experiment raises if one of its checks fails."""
    out = tmp_path_factory.mktemp("results")
    return out, run_all.run_all(X.Config(quick=True, runs=RUNS, out=out))


def rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("name, charts, counters", [
    ("exp1", ["exp1_runtime.png"], ["visited", "edges_examined"]),
    ("exp2", ["exp2_astar_vs_dijkstra.png", "exp2_runtime_growth.png"],
     ["expanded", "relaxed", "heap_ops", "path_cost"]),
    ("exp3", ["exp3_runtime.png", "exp3_greedy_gap.png"], ["benefit", "selected", "states"]),
    ("exp4", ["exp4_event_queue.png"], ["heap_pushes", "heap_pops", "heap_comparisons"]),
    ("exp5", ["exp5_sorts.png", "exp5_topk.png"], ["comparisons"]),
])
def test_experiment_quick(quick, name, charts, counters):
    tmp_path, text = quick
    assert all(text.count(heading) == 5 for heading in HEADINGS)
    raw, summary = rows(tmp_path / f"{name}_raw.csv"), rows(tmp_path / f"{name}_summary.csv")
    assert len(raw) == RUNS * len(summary)                 # every timed run is stored
    assert {int(r["run"]) for r in raw} == set(range(1, RUNS + 1))
    assert all(float(r["time_ms"]) > 0 for r in raw)
    for column in counters + ["runs", "mean_ms", "median_ms", "stdev_ms"]:
        assert column in summary[0]
    assert all(int(r["runs"]) == RUNS for r in summary)
    for chart in charts:
        assert (tmp_path / chart).stat().st_size > 5000


def test_timing_helper_warms_up_and_keeps_setup_outside():
    calls = []
    times, result = X.time_runs(lambda arg: calls.append(arg) or arg, X.Config(runs=5, warmup=2),
                                setup=lambda: len(calls))
    assert len(times) == 5 and calls == list(range(7)) and result == 6


def test_seeded_generators_are_reproducible_and_admissible():
    a, b = X.grid_graph(6, 6, 3, wall=True), X.grid_graph(6, 6, 3, wall=True)
    assert [(e.src, e.dst, e.distance) for e in a.edges()] == [(e.src, e.dst, e.distance) for e in b.edges()]
    for g in (a, X.random_graph(80, 60, 5, components=3)):
        assert all(e.distance >= g.straight_line(e.src, e.dst) for e in g.edges())


def test_greedy_is_strictly_worse_on_named_cases(quick):
    tmp_path = quick[0]
    named = [r for r in rows(tmp_path / "exp3_comparison.csv") if r["part"] == "named"]
    assert len(named) >= 3 and named[0]["dp_benefit"] == "48" and named[0]["greedy_benefit"] == "30"
    assert all(float(r["greedy_benefit"]) < float(r["dp_benefit"]) == float(r["exhaustive_benefit"]) for r in named)


def test_run_all_quick_writes_summary_and_environment(quick):
    tmp_path, text = quick
    assert (tmp_path / "SUMMARY.md").read_text(encoding="utf-8") == text
    assert text.count("**Conclusion.**") == 5
    assert (tmp_path / "environment.json").exists()


def test_event_pop_order_follows_time_priority_sequence(quick):
    order = rows(quick[0] / "exp4_order_check.csv")
    keys = [(float(r["trigger_time"]), int(r["priority"]), int(r["insertion_sequence"])) for r in order]
    assert keys == sorted(keys) and len({r["priority"] for r in order}) == 6
    assert exp4_event_queue.priority_check()            # the assertions inside it hold


def test_astar_and_dijkstra_costs_agree_in_every_row(quick):
    cmp = rows(quick[0] / "exp2_comparison.csv")
    assert {r["relation"] for r in cmp} <= {"fewer", "equal", "more"}
    assert {"harbor_eight", "grand_ring", "serpent_pass"} <= {r["family"] for r in cmp}
    assert any(r["family"].startswith("generated") for r in cmp)
    summary = rows(quick[0] / "exp2_summary.csv")
    cost = {}
    for r in summary:
        cost.setdefault((r["family"], r["V"], r["cost_model"]), []).append(float(r["path_cost"]))
    assert all(len(c) == 2 and abs(c[0] - c[1]) <= 1e-9 * max(1.0, c[0]) for c in cost.values())

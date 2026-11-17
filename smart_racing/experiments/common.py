"""Shared helpers of the five experiments (Project.md section 7): fair timing,
seeded input generators, CSV and chart output, environment record.

Timing rule used everywhere: `warmup` untimed calls, then `runs` timed calls
with `time.perf_counter`, on the same input instance for competing algorithms.
The garbage collector is run once before each configuration and switched off
during each timed call. Input construction, correctness checks, file output and plotting happen
outside the timed call. Every algorithm is called with `observer=None`.
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from smart_racing.core.graph import TrackGraph  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "experiments" / "results"
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
SPEED = {1: 40.0, 2: 36.0, 3: 32.0}     # distance units per second by difficulty (docs/RULES.md)


@dataclass
class Config:
    quick: bool = False        # tiny sizes: a smoke run for tests
    runs: int = 5              # timed runs per configuration
    warmup: int = 1            # untimed runs before them
    seed: int = 2026
    out: Path = RESULTS


# --- timing -------------------------------------------------------------------
def time_runs(fn: Callable, cfg: Config, setup: Callable | None = None) -> tuple[list[float], Any]:
    """Milliseconds of each timed run and the last return value. `setup()`, when
    given, runs before every call outside the timed region and its value is
    passed to `fn` (used when a run consumes its input, such as a queue)."""
    times, result = [], None
    was_enabled = gc.isenabled()
    gc.collect()
    for i in range(cfg.warmup + cfg.runs):
        arg = setup() if setup else None
        gc.disable()
        try:
            start = time.perf_counter()
            result = fn(arg) if setup else fn()
            elapsed = time.perf_counter() - start
        finally:
            if was_enabled:
                gc.enable()
        if i >= cfg.warmup:
            times.append(elapsed * 1000.0)
    return times, result


def record(raw: list[dict], cfg: Config, fields: dict, fn: Callable,
           counters: Callable[[Any], dict] | None = None, setup: Callable | None = None) -> Any:
    """Time `fn` and append one raw row per timed run: the configuration
    `fields`, the run number, its time, and the counters read from the result."""
    times, result = time_runs(fn, cfg, setup)
    extra = counters(result) if counters else {}
    for run, ms in enumerate(times, start=1):
        raw.append({**fields, "run": run, "time_ms": ms, **extra})
    return result


def summarize(raw: list[dict]) -> list[dict]:
    """One row per configuration (all columns except run and time): number of
    runs, mean, median and sample standard deviation of the time."""
    groups: dict[tuple, list[float]] = {}
    for row in raw:
        key = tuple((k, v) for k, v in row.items() if k not in ("run", "time_ms"))
        groups.setdefault(key, []).append(row["time_ms"])
    return [{**dict(key), "runs": len(t), "mean_ms": statistics.fmean(t),
             "median_ms": statistics.median(t),
             "stdev_ms": statistics.stdev(t) if len(t) > 1 else 0.0} for key, t in groups.items()]


# --- output -------------------------------------------------------------------
def write_csv(path: Path, rows: list[dict]) -> None:
    columns: dict[str, None] = {}
    for row in rows:
        columns.update(dict.fromkeys(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, list(columns), restval="")
        writer.writeheader()
        writer.writerows(rows)


def save_tables(cfg: Config, name: str, raw: list[dict]) -> list[dict]:
    """Write `<name>_raw.csv` and `<name>_summary.csv`; return the summary rows."""
    summary = summarize(raw)
    write_csv(cfg.out / f"{name}_raw.csv", raw)
    write_csv(cfg.out / f"{name}_summary.csv", summary)
    return summary


def fmt(value: Any) -> str:
    if isinstance(value, float):
        if value != value or value in (math.inf, -math.inf):
            return str(value)
        if value == int(value) and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:,.3f}" if abs(value) < 100 else f"{value:,.1f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def md_table(rows: list[dict], columns: list[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(fmt(row.get(c, "")) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def pick(rows: list[dict], **where) -> list[dict]:
    return [r for r in rows if all(r.get(k) == v for k, v in where.items())]


def new_axes(title: str, xlabel: str, ylabel: str, ncols: int = 1, **kwargs):
    fig, axes = plt.subplots(1, ncols, figsize=(6.6 * ncols, 4.6), **kwargs)
    for ax in ([axes] if ncols == 1 else axes):
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, color="#e3e2dc", linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.suptitle(title, fontsize=12)
    return fig, axes


def save_fig(fig, cfg: Config, filename: str) -> None:
    fig.tight_layout()
    fig.savefig(cfg.out / filename, dpi=130)
    plt.close(fig)


def series(ax, x, y, index: int, label: str, **kwargs) -> None:
    ax.plot(x, y, color=COLORS[index % 8], marker=MARKERS[index % 8], markersize=5,
            linewidth=1.8, label=label, **kwargs)


def environment(cfg: Config) -> dict:
    cpu = platform.processor()
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            cpu = next(line.split(":", 1)[1].strip() for line in handle if line.startswith("model name"))
    except (OSError, StopIteration):
        pass
    try:
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (ValueError, OSError, AttributeError):
        ram_gb = None
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(), "machine": platform.machine(), "cpu": cpu,
        "logical_cpus": os.cpu_count(), "ram_gb": ram_gb,
        "python": sys.version.split()[0], "implementation": platform.python_implementation(),
        "matplotlib": matplotlib.__version__,
        "timer": "time.perf_counter", "gc": "collected once before each configuration, disabled during each timed call",
        "warmup_runs": cfg.warmup, "timed_runs": cfg.runs, "seed": cfg.seed, "quick": cfg.quick,
        "process": "single process, single thread, experiments run one after another",
    }


def write_environment(cfg: Config) -> dict:
    env = environment(cfg)
    cfg.out.mkdir(parents=True, exist_ok=True)
    (cfg.out / "environment.json").write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    return env


def env_line(cfg: Config) -> str:
    e = environment(cfg)
    return (f"{e['cpu']}, {e['logical_cpus']} logical CPUs, {e['ram_gb']} GB RAM, {e['os']}, "
            f"{e['implementation']} {e['python']}, one process and one thread. Timer "
            f"`time.perf_counter`; {cfg.warmup} warm-up call then {cfg.runs} timed calls per "
            f"configuration; garbage collector run once before each configuration and disabled during "
            f"each timed call; base seed {cfg.seed}. Full record: `environment.json`.")


def parse_args(description: str) -> Config:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--quick", action="store_true", help="tiny sizes, written to results/quick")
    parser.add_argument("--runs", type=int, default=5, help="timed runs per configuration (default 5)")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    a = parser.parse_args()
    out = a.out or (RESULTS / "quick" if a.quick else RESULTS)
    out.mkdir(parents=True, exist_ok=True)
    return Config(a.quick, a.runs, a.warmup, a.seed, out)


def main(run: Callable[[Config], str], description: str) -> None:
    """Entry point of a single experiment run on its own."""
    cfg = parse_args(description)
    write_environment(cfg)
    print(run(cfg))
    print(f"\nOutputs written to {cfg.out}")


# --- seeded graph generators ----------------------------------------------------
def random_graph(n: int, extra_edges: int, seed: int, components: int = 1) -> TrackGraph:
    """Two-way graph on `n` random points of a 1000 x 1000 square, built so its
    structure is known: vertex `i` belongs to block `i % components`; each block
    is joined by a random tree (every vertex to a random earlier one of its
    block) and then receives its share of `extra_edges` random roads inside the
    block. So it has exactly `components` components and a cycle exactly when
    `extra_edges > 0`. Edge distance = straight line x U(1.0, 1.3)."""
    rng = random.Random(seed)
    g = TrackGraph()
    for v in range(n):
        g.add_vertex(v, rng.uniform(0, 1000), rng.uniform(0, 1000))
    pairs = [(rng.randrange(v % components, v, components), v) for v in range(components, n)]
    while len(pairs) < n - components + extra_edges:
        u = rng.randrange(n)
        w = rng.randrange(u % components, n, components)
        if u != w:
            pairs.append((u, w))
    for edge_id, (u, w) in enumerate(pairs, start=1):
        g.add_edge(edge_id, u, w, g.straight_line(u, w) * rng.uniform(1.0, 1.3))
    return g


def grid_graph(rows: int, cols: int, seed: int, wall: bool = False) -> TrackGraph:
    """Jittered lattice with documented coordinates and costs. Vertex
    `r * cols + c` sits at `(100 c, 100 r)` moved by up to 30 in x and y.
    Two-way roads join 4-neighbours: distance = straight line x U(1.0, 1.2)
    (never below the straight line), difficulty 1..3, time = distance / speed
    of that difficulty, fuel = 0.05 x distance. With `wall`, no road crosses
    between columns `cols//2 - 1` and `cols//2` except in row 0."""
    rng = random.Random(seed)
    g = TrackGraph()
    for r in range(rows):
        for c in range(cols):
            g.add_vertex(r * cols + c, 100 * c + rng.uniform(-30, 30), 100 * r + rng.uniform(-30, 30))
    edge_id = 0
    for r in range(rows):
        for c in range(cols):
            u = r * cols + c
            for dr, dc in ((0, 1), (1, 0)):
                if r + dr >= rows or c + dc >= cols:
                    continue
                if wall and dc and c == cols // 2 - 1 and r > 0:
                    continue
                w = (r + dr) * cols + c + dc
                distance = g.straight_line(u, w) * rng.uniform(1.0, 1.2)
                difficulty = rng.randint(1, 3)
                edge_id += 1
                g.add_edge(edge_id, u, w, distance, distance / SPEED[difficulty], 0.05 * distance, difficulty)
    return g

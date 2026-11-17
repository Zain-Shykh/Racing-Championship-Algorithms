# Implementation Plan

Requirements: `Project.md`. Design decisions: `docs/SPEC.md`.

Each phase is handed to one sub-agent. The phase is done only when its
acceptance criteria hold and `.venv/bin/pytest -q` is green. After review the
phase is committed and pushed to `origin/main`.

| Phase | Title | Depends on | Status |
|---|---|---|---|
| 0 | Project setup and planning | - | done |
| 1 | Core model, heap and graph algorithms | 0 | done |
| 2 | Resource, MST, backtracking and sorting algorithms | 1 | done |
| 3 | Tracks, validator, generator and event system | 2 | done |
| 4 | Race engine, opponents and championship | 3 | done |
| 5 | GUI part 1: app shell, menu, explorer, racing screen | 4 | pending |
| 6 | GUI part 2: algorithm lab, dashboard, generator view | 5 | pending |
| 7 | Five experimental studies | 4 | done |
| 8 | Report, README, packaging and final QA | 6, 7 | pending |

---

## Phase 0 — Project setup and planning

**Description.** Read the brief, freeze open decisions, create the repository
skeleton and the virtualenv.

**Goal.** Every later phase can start from written rules instead of guesses.

**Objectives.** `docs/SPEC.md`, this plan, `CLAUDE.md`, `requirements.txt`,
`.gitignore`, empty package tree, `.venv` with pygame-ce, pytest, matplotlib.

**Acceptance criteria.**
- `.venv/bin/python -c "import pygame, matplotlib, pytest"` succeeds.
- Docs committed and pushed.

---

## Phase 1 — Core model, heap and graph algorithms

**Description.** The data model of Project.md section 3 and the algorithms of
Acts 1 and 2: `config.py`, `core/graph.py`, `core/models.py`, `core/cost.py`,
`algorithms/heap.py`, `bfs.py`, `dfs.py`, `dijkstra.py`, `astar.py`.

**Goal.** A tested, UI-free library that can model a circuit, change it
dynamically and answer every reachability and shortest-path question the game asks.

**Objectives.**
- `TrackGraph` with adjacency lists, directed and undirected edges, edge status,
  service-vertex activation and independent per-edge effects (SPEC 4.5), all
  without rebuilding the graph.
- Records `Racer`, `RaceResult`, `ChampionshipEntry`, `Event` with the fields of
  Project.md 3.2.
- Cost normalization and the four presets (SPEC 4.3).
- Hand-written `MinHeap` with counters and deterministic ordering.
- BFS: reachability, minimum-edge path. DFS: traversal, cycle detection,
  connected components, dead-end analysis, bounded simple-path enumeration
  (route-count and path-length limits).
- Dijkstra and A* (SPEC 4.4) with counters: expanded vertices, relaxed edges,
  heap operations, path cost.
- All algorithms follow SPEC section 3 (result dataclass, counters, `observer`).

**Acceptance criteria.**
- Tests cover single-vertex, disconnected, cyclic, branching, dead-end, directed
  and undirected graphs.
- BFS returns the minimum edge count, including the S-T example of Project.md 5.1.
- DFS detects a cycle and a dead end; unreachable targets return a clean
  "no path" result and never loop.
- Dijkstra is checked against a brute-force optimum on small random graphs.
- A* returns the same cost as Dijkstra on every tested graph.
- Covered: source = target, unreachable target, blocked edge, equal-cost paths,
  zero-weight edges, recalculation after a block or cost change.
- Overlapping effects on one edge: expiring one leaves the other active.
- No use of `heapq` or other forbidden library algorithms.

---

## Phase 2 — Resource, MST, backtracking and sorting algorithms

**Description.** The remaining stand-alone algorithms: `knapsack.py`,
`refuel.py`, `mst.py`, `backtracking.py`, `sorting.py`, `topk.py`.

**Goal.** All 12 mandatory algorithm families exist as tested library code.

**Objectives.**
- 0/1 knapsack DP with reconstruction and state counter; greedy ratio heuristic
  (zero-cost items first, tie-break by lower item id); exhaustive search.
- Refuelling DP of Project.md 5.3 Problem B with plan reconstruction and
  infeasibility reporting (SPEC 4.2 discretization).
- Kruskal with union-find; reports a spanning forest when the input is disconnected.
- Generic backtracking placement solver with pluggable constraints and pruning
  counters (used later for checkpoints, services, obstacles).
- The single championship comparator (SPEC 4.7); merge sort, quick sort
  (documented pivot, three-way partition), heap sort, each counting comparisons.
- Top-k with a size-k heap built on the Phase 1 `MinHeap`.

**Acceptance criteria.**
- DP equals exhaustive search on randomized small instances.
- The supplied example (A, B, C, budget 10) gives greedy 30 and DP 48; two more
  team-created cases where greedy is strictly worse are in the tests.
- Refuel DP: insufficient fuel, full tank, unavailable station, capacity limit
  and infeasible plan are tested; every returned plan replays as feasible.
- Kruskal total weight equals a brute-force MST on small graphs.
- Three sorts agree on empty, singleton, random, sorted, reverse-sorted and
  duplicate-heavy inputs, including a case decided by the racer-id tie-break.
- Top-k equals the first k of a full sort for k = 0, 1, mid, n and k > n.

---

## Phase 3 — Tracks, validator, generator and event system

**Description.** Track data and everything that changes the track: the three
circuits, `loader.py`, `validator.py`, `generator.py`, `engine/events.py`.

**Goal.** Three playable circuits on disk, a generator that makes new valid
ones, and a deterministic event queue that mutates the graph.

**Objectives.**
- Three hand-designed JSON circuits with different topologies, each meeting
  Project.md 4.1 (>= 10 ordered checkpoints, >= 2 shortcuts, a cycle, a dead
  end, several difficulty levels, fuel stations, nitro pickups, some one-way
  roads) plus a fixed main route, a fixed detour and a default event script.
- Validator: ordered checkpoint reachability, lap/return feasibility, at least
  two alternative start-finish routes, at least one feasible fuel plan, minimum
  counts. Returns a list of human-readable failures.
- Generator pipeline of Project.md 5.4: place vertices, candidate roads, Kruskal
  MST, extra edges, backtracking placement with documented pruning rules,
  validate, retry up to a limit. Seeded.
- `EventQueue` on `MinHeap`: scheduling, lazy cancellation, expiry scheduling,
  target validation, batch application of equal-time events (SPEC 4.5).
- `docs/RULES.md` started: frozen parameters and the pruning rules.

**Acceptance criteria.**
- All three circuits pass the validator; a test asserts the minimum counts.
- At least one circuit yields different routes under different presets.
- Validator rejects prepared invalid tracks (unreachable checkpoint, no return
  path, single route only, infeasible fuel) with the right reason.
- Generator output passes the validator for several seeds, and a test shows at
  least one rejected candidate with its reason.
- Events pop in `(trigger_time, priority, insertion_sequence)` order; simultaneous
  events, cancelled events, expiry, missing targets and overlapping effects are tested.

---

## Phase 4 — Race engine, opponents and championship

**Description.** The headless game: `engine/routing.py`, `resources.py`,
`opponents.py`, `race.py`, `championship.py`.

**Goal.** A complete championship can be simulated with no GUI, deterministically.

**Objectives.**
- Checkpoint-aware leg planner (current -> next checkpoint -> ... -> finish) on
  Dijkstra/A*, with rerouting when an active-route edge is blocked or re-costed.
- Resource planner: knapsack/greedy pickup recommendation and refuel DP plan
  for a route, never recommending an infeasible plan.
- `RaceEngine` on a fixed tick: movement along edges, fuel, nitro, stations,
  pickups, laps, events, recovery policy and DNF (SPEC 4.1 to 4.6).
- Player input API (choose next edge, nitro, refuel, autopilot) with no pygame dependency.
- The three opponents of Project.md 4.4, each with its blocked-road and refuel rule.
- Results, points, bonus, standings via merge sort; quick sort and heap sort
  selectable; live top-k (SPEC 4.7).
- `docs/RULES.md` completed, including where each algorithm is invoked in gameplay.

**Acceptance criteria.**
- Integration tests: complete race, multiple laps, ordered checkpoints enforced
  (skipping one does not complete the lap), DNF, road closure with rerouting
  mid-race, full three-race championship standings.
- Two runs with identical inputs give identical results.
- A closure that removes every route makes racers wait and then DNF; nothing hangs.
- Each opponent's distinguishing behaviour is asserted (fixed route, shortcut
  preference, minimum distance).
- All three sorts give the same standings; top-k equals the standings prefix.

---

## Phase 5 — GUI part 1: app shell, menu, explorer, racing screen

**Description.** The pygame application: `main.py`, `ui/app.py`, `widgets.py`,
`render.py`, screens Main Menu, Track Explorer / Route Planner, Racing Screen.

**Goal.** A person can start the program, inspect a circuit, compare routes and
drive a race against the three opponents.

**Objectives.**
- Screen manager, shared theme, buttons, panels, scalable graph renderer
  (vertex types, edge status, shortcuts, one-way arrows, difficulty colouring).
- Main Menu: Championship, Quick Race, Algorithm Lab, instructions, settings
  (laps, cost preset, simulation speed).
- Track Explorer: pick circuit, pick start/destination by click, BFS reachable
  checkpoints, unreachable report, DFS cycles/components/dead ends, bounded
  alternative paths, Dijkstra vs A* route with distance/time/cost, preset
  comparison, resource recommendation panel.
- Racing Screen: animated cars, checkpoints, fuel and nitro HUD, race clock,
  lap and position, event feed, visible road state changes, player controls
  (SPEC 4.8), pause.

**Acceptance criteria.**
- `python main.py` opens the menu; all three screens are reachable and return.
- A Quick Race can be played to completion on each circuit, by hand and on autopilot.
- A road closure during a race visibly changes the road and the player route.
- Headless smoke tests (`SDL_VIDEODRIVER=dummy`) construct every screen, pump
  frames and run a race to the end without exceptions.
- Screenshots of each screen are saved to `docs/screenshots/` and look correct.

---

## Phase 6 — GUI part 2: algorithm lab, dashboard, generator view

**Description.** Screens Algorithm Lab / Visualization and Championship
Dashboard, the championship flow between races, and the track-generator view.

**Goal.** All five required screens exist and every mandatory algorithm can be
seen working on live game data.

**Objectives.**
- Algorithm Lab: choose any of the 12 algorithms, run it on the current
  track/data through the **same function gameplay calls**, step forward/back,
  play/pause, live counters, short explanation and complexity.
- Championship flow: circuit order, results screen after each race, standings,
  champion announcement.
- Dashboard: race results, standings, per-racer statistics, sort-method switch
  (merge/quick/heap) showing identical rankings and comparison counts, top-k view.
- Generator view: generate a track from a seed, show MST backbone, extra edges,
  placements, validator verdict, rejected candidates with reasons; race on it.
- Multi-objective view: the four presets side by side on one circuit.

**Acceptance criteria.**
- A full three-race championship can be played from the menu to the champion screen.
- Lab imports its algorithms from `smart_racing.algorithms` only (no copies);
  a test asserts the Lab's registry points at those functions.
- Step-through works for all 12 algorithms and counters match a direct call.
- Headless smoke tests cover the new screens; screenshots saved.

---

## Phase 7 — Five experimental studies

**Description.** `smart_racing/experiments/`: the five studies of Project.md
section 7, using the gameplay implementations.

**Goal.** Reproducible raw measurements, tables and charts for the report.

**Objectives.**
- One script per experiment plus `run_all.py`; seeded input generation; warm-up
  then at least 5 timed runs; mean, median and standard deviation; correctness
  checks kept outside timed regions.
- Exp 1 BFS/DFS (sparse and dense, runtime, visited, edges examined).
  Exp 2 Dijkstra/A* (runtime, expanded, relaxed, heap ops, cost).
  Exp 3 DP/greedy/exhaustive (benefit, items, runtime, states, greedy-worse cases).
  Exp 4 event queue (insert/extract time, heap ops, ties, cancellations, expiries).
  Exp 5 sorting and top-k (four input shapes, comparisons, k small and k near n).
- Outputs: `experiments/results/*.csv`, `*.png`, and an environment record.

**Acceptance criteria.**
- `.venv/bin/python -m smart_racing.experiments.run_all` regenerates every CSV
  and chart in a few minutes with no manual steps.
- Each experiment asserts its correctness condition (BFS minimum edges, equal
  Dijkstra/A* cost, DP = exhaustive, heap order, sorts agree, top-k = prefix).
- Raw per-run measurements are stored, not only aggregates.

---

## Phase 8 — Report, README, packaging and final QA

**Description.** Technical report, user documentation, submission archive and a
last full check against the brief.

**Goal.** A submission-ready ZIP.

**Objectives.**
- `report/report.md` following Project.md 9.2 (ten sections), with pseudocode,
  correctness reasoning, complexity, integration map, test summary, the five
  experiments in the required format, limitations and acknowledgements; exported
  to `report/report.pdf`.
- `README.md`: install, run, controls, tests, experiments, project layout.
- `scripts/package.sh` (or `.py`) building `24I-XXXX_24I-YYYY_24I-ZZZZ_Section.zip`
  without `.venv`, caches or `.git`; group identity read from one place.
- Checklist audit of Project.md sections 1 to 9 with file references;
  fix anything missing.

**Acceptance criteria.**
- Fresh clone + README steps run the game and the tests.
- Full test suite green; report PDF opens and contains all ten sections and five experiments.
- Audit table shows every mandatory item satisfied or explicitly listed as a limitation.
- ZIP builds, is free of junk files, and unpacks to a runnable project.

# Smart Racing Championship — Technical Specification

Source of requirements: `Project.md` (the assignment brief). This file freezes the
design decisions the brief leaves open. If this file and `Project.md` disagree,
`Project.md` wins and this file must be corrected.

## 1. Stack

- Python 3.12, virtualenv in `.venv` (`.venv/bin/python`, `.venv/bin/pytest`).
- GUI: `pygame-ce` (imported as `pygame`). Charts for experiments: `matplotlib`.
- Tests: `pytest`. No other runtime dependencies without a strong reason.
- All 12 mandatory algorithms and the heap are implemented by hand. Do **not** use
  `heapq`, `sorted`/`list.sort` (for the ranking algorithms), `networkx`,
  `functools.lru_cache`-as-DP or any library implementation of a mandatory
  algorithm. `collections.deque` is allowed as the BFS queue.
- No machine learning, no randomness in opponents. Any randomness (track
  generation, experiment inputs) uses an explicit seeded `random.Random(seed)`.

## 2. Package layout

```
main.py                      entry point: python main.py
smart_racing/
  config.py                  every frozen constant in section 4
  core/
    graph.py                 Vertex, Edge, TrackGraph (adjacency lists, effects)
    models.py                Racer, RaceResult, ChampionshipEntry, Event
    cost.py                  normalization, weight presets, scalar edge cost
  algorithms/
    heap.py                  MinHeap (binary heap, counters)
    bfs.py  dfs.py           traversal, min-edge path, cycles, components, dead ends, bounded alt paths
    dijkstra.py  astar.py    shortest path with counters
    knapsack.py              0/1 knapsack DP, greedy ratio heuristic, exhaustive search
    refuel.py                refuelling DP
    mst.py                   Kruskal + union-find
    backtracking.py          constraint placement (checkpoints, services, obstacles)
    sorting.py               comparator, merge sort, quick sort, heap sort
    topk.py                  size-k heap top-k
  engine/
    events.py                EventQueue (MinHeap), effect application/expiry, lazy cancel
    routing.py               checkpoint-aware leg planner, rerouting
    resources.py             pickup/refuel recommendation using knapsack + refuel DP
    opponents.py             the three deterministic strategies
    race.py                  RaceEngine: fixed-tick simulation, laps, fuel, nitro, DNF
    championship.py          points, standings, tie-breaking
  tracks/
    data/*.json              the three hand-built circuits
    loader.py                JSON <-> TrackGraph
    validator.py             playability checks
    generator.py             MST backbone + extra edges + backtracking placement
  ui/
    app.py                   pygame app, screen manager
    screens/                 menu, explorer, race, lab, dashboard
    widgets.py  render.py    shared buttons/panels, graph drawing
  experiments/
    run_all.py  exp1..exp5   write CSV + PNG into experiments/results/
tests/                       pytest suites
docs/                        SPEC.md, IMPLEMENTATION_PLAN.md, RULES.md
report/                      report.md, figures, report.pdf
```

Dependency direction: `ui -> engine -> algorithms -> core`. `algorithms` and
`core` never import `pygame`. `engine` never imports `pygame`, so a whole race
can run headless in tests.

## 3. Algorithm conventions (this is what makes the Algorithm Lab honest)

The brief requires that the Algorithm Lab calls the **same implementation** that
gameplay uses. Therefore every algorithm:

1. Is a plain function in `smart_racing/algorithms/` with no UI or timing code.
2. Returns a result dataclass that includes its operation counters
   (for example `visited`, `edges_examined`, `expanded`, `relaxed`, `heap_ops`,
   `comparisons`, `states`), so experiments need no separate instrumented copy.
3. Accepts an optional `observer: Callable[[dict], None] | None = None`. When it
   is not `None` the algorithm calls it once per meaningful step with a small
   dict (`{"type": "visit", "vertex": 3, ...}`). The Lab records these steps and
   replays them. When `observer is None` there is no extra cost beyond one check.
4. Never reads global mutable state. Graph algorithms take the `TrackGraph` and,
   where relevant, a `cost_fn(edge) -> float`.

Graph algorithms iterate `graph.neighbors(u)`, which yields only currently
traversable `(edge, neighbour)` pairs: blocked edges and wrong-way one-way edges
are excluded. Iteration order is ascending edge id so results are deterministic.

## 4. Frozen game rules and parameters (`config.py`)

### 4.1 Circuit structure
- Each circuit has one `Start` vertex, one `Finish` vertex, at least 10 mandatory
  checkpoints with `checkpoint_order` 1..n, at least 2 shortcut edges, at least
  one cycle, at least one `DeadEnd` vertex, fuel stations and nitro pickups.
- A lap = visit checkpoints 1..n in order, then reach `Finish`. Arriving at
  `Finish` with all checkpoints done is the lap boundary. The next lap starts
  from `Finish` and again targets checkpoint 1 (the graph must contain a route
  from `Finish` back to checkpoint 1).
- Passing through a checkpoint out of order does not count. The racer must
  return to it later.
- Default laps per race: 2. Race time limit: 900 simulated seconds.

### 4.2 Fuel and nitro (identical for player and opponents)
- Tank 100 units, full at start. Edge fuel = `fuel_cost * (1.0 + 0.1 * (effective_difficulty - 1))`.
- Fuel is drained continuously along the edge. A racer may enter an edge only if
  current fuel covers the whole edge at the non-nitro rate; otherwise it stops.
- Fuel station: buy up to 40 units per stop, capped by tank capacity. Any positive
  purchase costs a fixed 3.0 s stop. Station must be `active`.
- Nitro: max 3 charges, start with 1. An active pickup gives +1 charge (not above 3).
  After collection the pickup deactivates and respawns after 25 s.
  One activation = 1.5x speed for 4 s and 2x fuel drain while active.
- DP discretization: `FUEL_SCALE = 10` (tenths of a unit). Leg demands are
  rounded **up** to a tenth, so a DP-feasible plan is always feasible in the engine.
  Purchases are considered in whole units (0..40) to bound the state space.

### 4.3 Route cost
`cost(e) = wD*D/Dref + wT*T/Tref + wF*F/Fref + wR*R + wO*O`

- `D` distance, `T` effective travel time, `F` effective fuel, `R = (effective_difficulty - 1) / 4`,
  `O` obstacle penalty in [0, 1] from active effects (oil spill 1.0, speed restriction 0.5, else 0).
- Reference values: `Dref = 100`, `Tref = 10`, `Fref = 10`. All weights >= 0.

| Preset | wD | wT | wF | wR | wO |
|---|---|---|---|---|---|
| Balanced | 1 | 1 | 1 | 1 | 1 |
| Speed | 0.5 | 3 | 0.25 | 0.5 | 0.5 |
| Economy | 0.5 | 0.5 | 3 | 0.5 | 0.5 |
| Safety | 0.5 | 0.5 | 0.5 | 3 | 3 |

The cost shown in the UI is exactly this function. At least one circuit must
produce different routes under different presets (covered by a test).

### 4.4 A* heuristic
`h(u) = straight_line(u, target) * r`, where `r` is the minimum over currently
traversable edges of `cost(e) / straight_line(e)`. Edges whose endpoints coincide
are skipped. If no valid positive ratio exists, `h = 0`. This heuristic is
admissible and consistent, so closed vertices are never reopened. `r` is
recomputed for every query because costs change with events.

### 4.5 Events
Min-heap key `(trigger_time, priority, insertion_sequence)`.

| Event | Priority | Effect | Duration |
|---|---|---|---|
| Road blockage | 1 | edge blocked | until a clear event |
| Shortcut open/close | 2 | shortcut edge open/blocked | until reversed |
| Oil spill | 3 | effective difficulty +2 (max 5), time x1.5 | 20 s |
| Speed restriction | 4 | time x1.5 | 15 s |
| Fuel station availability | 5 | station inactive | 30 s |
| Nitro booster | 6 | pickup active | until collected or 25 s |

- Every effect is stored independently on its target, keyed by event id. The
  effective edge state is recomputed from all active effects: blocked if any
  block effect is active; difficulty bump = maximum of active bumps; time
  multiplier = the largest (strictest) active multiplier. Status is `Restricted`
  while any oil or speed effect is active. Expiring one effect removes only that record.
- Temporary effects schedule their own expiry event at creation time.
- Cancellation is lazy: mark `cancelled`, skip when popped.
- An event with a missing target, or invalid in the current state, is rejected
  with a logged reason and has no effect.
- All events sharing a trigger time are applied in heap order, then routes are
  recalculated once for every racer whose remaining route is affected.

### 4.6 Recovery policy (same for every racer)
1. If the next edge of the route is blocked or the target is unreachable, re-plan
   from the current vertex.
2. If no route exists, wait at the current vertex. Waiting time counts as race
   time. Re-plan after every event batch.
3. If the racer lacks fuel for the next edge: refuel if standing on an active
   station; otherwise re-plan through the nearest reachable active station that
   fuel allows; otherwise wait if a pending event could change this.
4. The racer is DNF when it has waited 60 s continuously, or when it cannot move
   and no pending event can help. Time-limit expiry ends the race for everyone.

### 4.7 Ranking and scoring
- Finishers ranked by finish time, ties by lower racer id.
- Unfinished (time limit or DNF) ranked after finishers by laps completed desc,
  checkpoints completed desc, elapsed time asc, racer id asc.
- Points 25, 18, 15, 12, 10, 8, 6, 4, 2, 1 for finishers only. Unfinished and DNF
  racers receive 0 points. Bonus: +1 for the fastest lap of the race, awarded
  only to a finisher.
- Championship comparator (single function used by all three sorts and top-k):
  higher total points; then more wins; then lower sum of finish positions; then
  lower best fastest lap; then lower racer id.
- Championship = the three circuits in fixed order. Racers: 1 human + 3 opponents
  (the scoring table supports up to 10).

### 4.8 Player control
At a vertex the player picks the next outgoing edge (click or number key), or
leaves autopilot on to follow the recommended route. `Space` fires nitro. At an
active fuel station the player chooses how much to buy. The player is subject to
every rule above.

## 5. Determinism
The engine runs on a fixed simulation tick (`SIM_DT = 0.05` s). The UI feeds
real time into an accumulator; tests call `engine.run_to_completion()`. Given
the same track, event script and inputs, results are bit-identical.

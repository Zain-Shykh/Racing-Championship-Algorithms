# Rules decided during implementation

Decisions that `Project.md` and `docs/SPEC.md` leave open. One entry per decision.

## Phase 1

- **Dead end** (`algorithms/dfs.py: dead_ends`). "Reversing" means leaving a
  vertex by the edge just used to arrive. A vertex is a dead end when it is not
  Start, Finish or a Checkpoint, it can be driven to from the start without
  reversing, and from none of its arrival states can the finish be reached
  without reversing. So a spur is a dead end along its whole length, a loop
  hanging off the main road is not (the car can drive round it), and a vertex
  unreachable from the start is reported as disconnected, not as a dead end.
  The analysis uses the current graph state, so a blockage can create dead ends.
- **Cycle** (`find_cycle`). A closed walk that repeats no edge, respecting one-way
  roads. One two-way road used out and back is not a cycle; two parallel roads are.
- **Connected components** ignore road direction (weak connectivity) and treat
  blocked edges as absent.
- **Alternative routes** (`enumerate_paths`). Limits: at most
  `ALT_ROUTE_LIMIT = 10` routes and `ALT_PATH_MAX_EDGES = 40` edges per route.
  Paths come out in DFS order with ascending edge ids; the main route is excluded
  by passing its edge list.
- **Shortest-path ties.** Heap key is `(cost, vertex id)`; a parent is replaced
  only on strict improvement. BFS and DFS explore edges in ascending edge id.
- **Edge effects** are stored as `effect id -> kind` with kinds `block`, `oil`,
  `speed` (`config.EDGE_EFFECTS`). Obstacle penalty is the maximum over active
  effects. A closed shortcut is an ordinary `block` effect.
- **Heap ties.** Entries with equal keys leave the heap in insertion order.
- **Edge defaults.** `add_edge` uses `distance` for `base_time` and `fuel_cost`
  when they are omitted (used by tests and experiments, not by track files).

## Phase 2

- **Knapsack items** (`algorithms/knapsack.py`). Costs and the budget are
  non-negative integers in the caller's scaled unit; item ids are unique;
  anything else raises `ValueError`. The DP takes an item only on strict
  improvement and the traceback reads "taken" as `dp[i][b] != dp[i-1][b]`, so
  among equally good selections the result is deterministic. Selected ids are
  reported in ascending order.
- **Greedy knapsack.** Items with benefit <= 0 are never taken, which settles
  zero-cost zero-benefit items (they change nothing). Zero-cost items with
  positive benefit are taken first in id order. The rest go by benefit/cost
  descending, ties by lower item id, ratios compared by cross-multiplication.
  An item that does not fit is skipped and the scan continues with the next
  one (it does not stop at the first misfit).
- **Exhaustive knapsack** refuses more than 22 items (`EXHAUSTIVE_MAX_ITEMS`).
- **Refuel route model** (`algorithms/refuel.py`). A route is `m` stops plus
  the destination, given as `demands[j]` (fuel for the leg leaving stop `j`)
  and `available[j]`. A stop that is not a station, such as the racer's current
  vertex, is passed as unavailable. Nothing is bought at the destination.
- **Refuel rounding.** Demands round up to 1/`FUEL_SCALE`, starting fuel and
  tank capacity round down, purchases are whole units that fit in the DP's
  tank. The DP fuel is therefore never above the real fuel. The replay checker
  uses real fuel and caps the tank at capacity (SPEC 4.2 "capped by tank
  capacity"), so a purchase that would overfill by the rounding slack is legal.
- **Refuel objective and ties.** Minimum total stop time, which with a fixed
  stop time is the fewest paid stops. Among those plans the one arriving with
  the most fuel is returned: a stop costs the same whatever is bought, and
  spare fuel protects against a later reroute. Remaining ties are settled by
  the DP scan order (lower fuel state first, smaller purchase first, strict
  improvement only).
- **Refuel infeasibility.** `feasible=False`, empty `purchases`, `failed_leg` =
  the first leg no reachable state can cover, and a `reason` text. Start fuel
  outside `0..capacity`, negative demands or mismatched lengths raise `ValueError`.
- **Kruskal** (`algorithms/mst.py`). Edges are `(edge id, u, v, weight)` and
  are taken in ascending `(weight, edge id)` order using the project merge
  sort. Disconnected input returns a minimum spanning forest with
  `is_spanning_tree=False` and `components` > 1. An empty vertex set is not a
  spanning tree; a single vertex is. An edge naming an unknown vertex raises
  `ValueError`. Union-find uses union by rank and path compression.
- **Backtracking** (`algorithms/backtracking.py`). Variables are assigned in
  the given order and values tried in domain order (first solution wins).
  `nodes` counts candidate values tried, `prunes` counts candidates rejected by
  the consistency predicate plus branches cut by the pruning hook, `backtracks`
  counts assignments undone. `BACKTRACK_NODE_LIMIT = 200000` candidates; when
  it is hit the result has `limit_hit=True`, which means "gave up", not
  "proved impossible".
- **Quick sort pivot.** Median of three elements at pseudo-random positions
  from `random.Random(0)` created per call (deterministic). First/middle/last
  was rejected: after a three-way partition it needed about 34 million
  comparisons on 100 000 already sorted elements. Ranges live on an explicit
  stack, larger side deferred, so there is no recursion.
- **Sort and top-k counters.** `comparisons` is the number of comparator
  calls. Sorts return a new list and leave the input untouched.
- **Top-k ties.** Items the comparator cannot separate are ordered by input
  position, so `top_k(items, k)` equals `merge_sort(items)[:k]` for any
  comparator. `k <= 0` returns an empty list, `k > n` returns all items.
  `MinHeap` needed no change.
- **A racer with no lap time** keeps `best_fastest_lap = inf` and so loses the
  fastest-lap tie-break to any racer that has one.

## Phase 3

### Circuit files and built-in circuits
- **File format** (`tracks/loader.py`). One JSON object: `name`, `vertices`,
  `edges`, `main_route`, `detour`, `opponent_shortcuts`, `events`. Routes are
  vertex-id lists; `route_edges` turns one into edge ids by taking, per step,
  the lowest-id road that may be driven in that direction. Active edge effects
  are never saved: a file always holds the base track.
- **Lap shape.** Start and Finish are two vertices joined by a one-way road
  Finish -> Start, so the next lap is Finish -> Start -> checkpoint 1 and nobody
  can reach Finish backwards from Start.
- **Main route (Opponent 1)** is a simple path Start -> checkpoints in order ->
  Finish. **Detour** is one fixed path that leaves the main route at its first
  vertex and rejoins it at its last, with no mandatory vertex on the bypassed
  part. **Designated shortcuts (Opponent 2)** are shortcut roads joining two
  main-route vertices, forwards, that cut off no mandatory vertex.
- **Edge numbers.** Road length is the straight-line length times a curve
  factor of at least 1, rounded up, so `distance >= straight line` always
  (A* heuristic). Normal speed by difficulty 1..5 is 40/36/32/28/24 distance
  units per second. Shortcuts are short, fast (48), hard (difficulty 4 or 5)
  and thirsty, so Speed takes them while Economy and Safety do not.
- **Fuel tuning.** Least-fuel two-lap race: Harbor Eight about 96 units (no
  stop needed, but only just), Grand Ring about 130 (one stop), Serpent Pass
  about 151 (two stops). Fuel stations sit on the main route.
- **Nitro pickups.** Each circuit has two pickups that start active and one
  "booster" that starts inactive and is switched on by `nitro_spawn` events.
- **Event scripts** use every event type, start after 10 s and are spread over
  a normal race. At least one road blockage per circuit is on the main route
  inside the part the fixed detour bypasses.
- **Championship order**: `config.BUILTIN_CIRCUITS`.

### Validator (`tracks/validator.py`)
- **Thresholds** are keyword parameters with defaults from `config`: 10
  checkpoints, 2 shortcuts, 2 fuel stations, 2 nitro pickups, 1 one-way road,
  3 distinct difficulty levels ("several"), 2 Start-to-Finish routes, a dead end.
- **"Two alternative start-finish routes"** is read as: at least two distinct
  simple Start -> Finish paths (`enumerate_paths` with `max_routes=2`).
- **Dead end rule**: at least one vertex of type `DeadEnd` must be in the list
  the DFS dead-end analysis reports.
- **Fuel rule.** The race route is built leg by leg with Dijkstra on effective
  fuel (`checkpoint_route`), for `LAPS_PER_RACE` laps. The refuel DP then runs
  with one stop per visit to an active fuel station on that route. If that
  fails and a main route is known, the same DP is tried on the main route
  (later laps go Finish -> checkpoint 1 by least fuel and rejoin it). The rule
  is conservative: it can reject a track whose only feasible plan leaves both
  routes to reach a station, but it never accepts an unplayable one.
- `validate_circuit` adds checks of the main route, detour, designated
  shortcuts and event targets. A track is validated with no active effects.

### Generator (`tracks/generator.py`)
- **Pipeline.** (1) vertices on a `GEN_COLS x GEN_ROWS` lattice, each moved by
  at most `GEN_JITTER` of a cell; (2) candidate two-way roads = lattice sides
  plus one diagonal per cell, random length factor 1.0..1.3 and difficulty
  1..3, connectivity checked with DFS components before the MST; (3) Kruskal
  backbone, weight = road length; (4) `GEN_EXTRA_FRACTION` of the unused
  candidates added in seeded random order; (5) backtracking search for a closed
  main loop; (6) one-way roads; (7) backtracking placement; then
  `validate_circuit` with the default thresholds.
- **Retry limit**: `GEN_MAX_ATTEMPTS = 20` candidates per seed. Attempt `k` of
  seed `s` uses `random.Random(s * 1000 + k)`. Every refused candidate is kept
  in the report with its stage (`candidates`, `loop`, `placement`,
  `validation`) and reasons. Fuel per distance is drawn per attempt from
  `GEN_FUEL_RATE`; the top of that range is too thirsty for two stations, which
  is the usual validator rejection (for example seed 29, attempt 1).
- **Dead end.** One MST leaf is picked before extra roads are added and never
  receives one; it becomes the `DeadEnd` vertex.
- **Main loop search.** Variables are loop slots `0..L-1`, tried for
  `L = 20, 18, 16` with at most `GEN_LOOP_NODE_LIMIT` candidates each; a value
  must be unused and adjacent to the previous slot, and the last slot must be
  adjacent to the first. Slot 0 is Start, slot L-1 is Finish.
- **One-way roads** are added after the MST: the closing road becomes
  Finish -> Start and one extra (non-tree, off-loop) road gets a random
  direction. Neither can break reachability: every vertex stays joined to the
  loop by two-way tree roads and the loop stays drivable Start -> Finish.
  The validator still checks the directed graph.
- **Placement variables**, in order: 2 shortcuts, 2 fuel stations, 10
  checkpoints, 3 nitro pickups (the third is the inactive booster), 2 road
  closures, 1 oil-spill site, 1 speed-restriction site. Stations and
  checkpoints take loop positions, tried nearest-first to evenly spread
  targets. A shortcut is a candidate road, new or already built, joining two
  loop vertices 2 to `GEN_SHORTCUT_MAX_SKIP + 1` positions apart.
- **Pruning rules** (what is cut, and why nothing valid is lost):
  1. *Maximum degree.* A new shortcut road is refused if an endpoint already
     has `GEN_MAX_DEGREE` roads (the same cap applies when extra roads are
     added). Cuts junctions too crowded to draw or drive. Safe: the cap is a
     hard requirement, so no acceptable track contains such a road.
  2. *Fuel-station spacing.* The second station must be at least
     `GEN_STATION_MIN_GAP` loop positions from the first in both directions.
     Cuts layouts with both stations in one stretch, which leave the rest of
     the lap without fuel. Safe: spacing is a requirement of the placement.
  3. *Obstacle spacing.* Two obstacle sites may not share an endpoint. Cuts
     clusters that would close or slow every road at one junction at once.
     Safe: it only compares with sites already placed.
  4. *Critical bridge.* A road closure is never placed on a bridge (a road
     whose removal splits the graph, found by blocking it and counting DFS
     components). Cuts closures that would cut racers off from part of the
     track. Safe: such a script would be unplayable by definition. The first
     closure must also be a loop road with a directed bypass, which becomes
     the fixed detour.
  5. *Shortcut separation.* The second shortcut starts after the first ends,
     so they share no vertex and are not tried in both orders (symmetry).
  6. *Checkpoint order and room.* Checkpoint `k` goes after checkpoint `k-1`
     and never on a station or on a vertex a shortcut cuts off. Forward
     check: a branch is cut when fewer free later positions remain than
     checkpoints still to place. Safe: each needs its own later position.
  7. *Nitro spacing.* Pickups are at least `GEN_NITRO_MIN_HOPS` roads apart,
     not on a mandatory, station or dead-end vertex; off-loop vertices first.
  8. *Loop closure* (loop search). A branch is cut when the first vertex is
     more roads away than there are slots left. Safe: BFS hop count is a lower
     bound on the roads still needed.
- **Generated event script** is a fixed timetable (12 s to 165 s) filled with
  the placed sites; the first closure is on the main loop.

### Events (`engine/events.py`)
- **Validation happens when the event fires**, not when it is scheduled, since
  validity depends on the state at that time. Rejected events are kept in
  `EventQueue.rejected` with the reason and change nothing. An unknown event
  type is a programming error and raises `ValueError` at scheduling.
- **Invalid in the current state**: clearing a road with no active blockage;
  blocking a road already closed by a `road_block`; closing a road that is not
  a shortcut or is already closed; opening a shortcut that is not closed; an
  outage on a non-station; a nitro spawn on a non-pickup or an active pickup.
- **Road block and shortcut close are separate effects.** Both are `block`
  records; `road_clear` ends only road blocks and `shortcut_open` only
  shortcut closures, so a road hit by both stays blocked until both are undone.
- **Expiry.** A temporary effect schedules an `expire` event at
  `trigger_time + duration` with the priority of the event it undoes; it
  removes that one record. `duration=None` means the default of
  `EVENT_DURATION`; `math.inf` means no expiry. Ending an effect early (clear,
  open, nitro collected) cancels its pending expiry.
- **Fuel stations** stay inactive while any outage record is active, so
  overlapping outages compose like edge effects.
- **Nitro.** `nitro_spawn` activates an inactive pickup for 25 s.
  `collect_nitro` deactivates it, cancels that expiry and schedules a lasting
  respawn after `NITRO_RESPAWN_TIME` (SPEC 4.2).
- **Pending changes.** `has_pending_changes()` is true while any live
  (not cancelled, not yet fired) event remains, expiries included.
- **Batching.** `pop_due(now)` applies everything due in heap order, including
  expiries created during the call that are already due, and returns the
  applied records; the engine re-plans once after the call.

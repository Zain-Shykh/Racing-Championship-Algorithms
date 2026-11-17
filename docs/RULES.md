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
  Serpent Pass is the longest circuit, so in Phase 4 all its base times were
  multiplied by 0.75 (speeds 53/48/43/37/32, shortcuts 64) and its event times
  by the same factor, to keep a two-lap race under four minutes.
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

## Phase 4: the frozen rules as implemented

The numbers are in `config.py`; SPEC section 4 is the summary. This section
adds every decision the engine had to make. Code: `smart_racing/engine/`.

### Simulation (`race.py`)
- **Tick.** `SIM_DT = 0.05` s, clock = tick count x `SIM_DT`. One tick:
  (1) apply every event with `trigger_time <= clock` in heap order
  (`EventQueue.pop_due`); (2) one re-plan pass; (3) move every racer through
  the tick in racer-id order. `update(dt)` adds frame time to an accumulator
  and runs whole ticks; `run_to_completion()` ticks until the race is over.
  Both give identical results.
- **Exact times inside a tick.** A racer spends its 0.05 s piece by piece:
  finishing a road, a fuel stop and the next road each use their true share,
  so arrival, lap and finish times are exact and do not depend on tick size.
- **Movement.** On a road the progress fraction grows by
  `dt x nitro multiplier / effective_time`, with the road's *current*
  effective time, so an oil spill or speed restriction slows a car already on
  the road. A car on a road that gets blocked finishes that road.
- **Fuel.** A road may be entered only with fuel >= its effective fuel. That
  price is fixed at entry; an oil spill starting later does not raise it for
  a car already on the road, so no car can strand between two vertices.
  Fuel drains in proportion to progress, doubled while nitro is active.
- **Nitro.** One activation = 4 s at 1.5x speed and 2x fuel use. The 4 s run
  in race time (also during a stop). The player may fire whenever the car is
  racing, has a charge and no boost running. **Cut-out:** if the next piece of
  boosted driving would leave less fuel than the rest of the current road
  needs at the normal rate, the boost ends at once. The charge is spent.
- **Pickups.** Arriving at an active nitro pickup with fewer than 3 charges
  gives +1 charge through `EventQueue.collect_nitro` (pickup off, respawn
  after 25 s). With 3 charges the pickup is left alone. Two cars arriving in
  the same tick: the lower id is served first.
- **Fuel stations.** A stop buys 1..40 units, capped by tank room, takes 3 s,
  and the fuel is in the tank at the start of the stop. A racer may make
  several stops in a row at the same station; each is a separate 3 s stop of
  at most 40 units. The refuel DP models one purchase per visit, so its plans
  stay valid.
- **Checkpoints and laps.** Arriving at the checkpoint whose order equals
  `next_checkpoint` advances it. Arriving at any other checkpoint counts
  nothing. Arriving at Finish with all checkpoints done completes the lap;
  arriving at Finish early counts nothing. The race ends for a racer when it
  completes `laps` laps.
- **End of race.** When every racer is finished or DNF, or when the clock
  reaches `RACE_TIME_LIMIT` (900 s). Racers still running then keep status
  `racing`, have no finish time, and `end_time` = the limit.
- **Statuses:** `racing`, `waiting`, `refuelling`, `finished`, `dnf`.

### Re-planning
- After an event batch every active racer is re-planned once if (a) a road on
  its remaining route was blocked or re-costed, or (b) the batch reopened or
  restored any road (road clear, shortcut open, an oil/speed expiry), because
  a better route may now exist. A waiting racer tries again after every batch.
- A racer on a road is planned from the vertex it is driving to, with the
  checkpoint progress it will have there.
- At a vertex, a racer whose next road is no longer drivable re-plans first.
- A racer whose route is empty (after a manual move or a station detour)
  re-plans from its real progress, so no state can leave it without a route.
- `reroutes` counts changes of a non-empty route, including fuel detours.

### Recovery policy (identical for every racer, SPEC 4.6)
1. **Blocked next road or no route:** re-plan from the current vertex with the
   racer's own strategy.
2. **Still no drivable route:** wait at the vertex (`waiting`, reason
   "no open route") and try again after each event batch.
3. **Fuel.** Checked at every vertex before leaving. If the fuel cannot cover
   the next road, or it cannot cover the route to the next active station on
   it (the end of the race when there is none) *and* after the next road no
   station at all would be reachable, the racer leaves its route for the
   nearest reachable active station (least fuel to reach, Dijkstra on fuel;
   ties by lower id) and re-plans from there. A station that is out of
   service counts as reachable in the look-ahead, because outages are
   temporary. If no open station is reachable the racer drives to the nearest
   closed one, or stays if it is standing on one, and waits ("fuel station
   closed"); with no station in reach at all it waits where it is ("out of
   fuel").
4. **DNF** after 60 s of continuous waiting, or immediately when the racer
   must wait and the event queue holds no pending event (nothing can change).
   The wait counter restarts when the racer moves or refuels.
- **How time is counted.** Waiting and fuel stops are race time: the clock
  never stops for a racer. A DNF racer's elapsed time is the moment it was
  ruled out (`end_time`); it ranks by laps, checkpoints, that time, id.
- The policy cannot hang: a wait ends in a move, a DNF after at most 60 s, or
  the time limit.

### Player control (no pygame; SPEC 4.8)
- `set_autopilot`, `choose_edge`, `fire_nitro`, `refuel`; queries
  `legal_choices` (open, correctly directed, affordable roads, with the
  recommended one flagged) and `station_offer` (most units, recommended units).
- `choose_edge` is accepted only for a legal road. It may be given while still
  driving, for the vertex ahead, and is checked again on arrival. A chosen
  road overrides the recommended route once, also with autopilot on.
- **Autopilot on:** the player's car follows the recommended route (A* under
  the selected preset, plus knapsack pickups), buys what the refuel DP says
  and uses the automatic nitro rule. A race needs no input.
- **Autopilot off, no input:** at a vertex with more than one legal road, or
  at an active station, the car stands for `PLAYER_CHOICE_GRACE = 3 s`; then
  the recommended purchase and the recommended road are taken. At a vertex
  with a single legal road the car drives on without stopping. So an idle
  manual player still finishes, only slower. The grace is not "waiting": it
  never counts towards DNF. A player who picks a road explicitly gets no
  automatic purchase at that vertex and no automatic nitro.

### Opponents (`opponents.py`, Project.md 4.4)
All three are deterministic and obey the rules and recovery policy above.
- **Opponent 1, `fixed`.** Drives `main_route`; later laps go Finish ->
  checkpoint 1 by the shortest-distance road (Finish -> Start) and repeat it.
  Blocked road: if a road of the stretch that `detour` bypasses is blocked
  and every detour road is open, the detour replaces that stretch. Any other
  blockage: drive up to it and wait (recovery rule 2).
- **Opponent 2, `shortcut`.** The same lap with every designated shortcut
  (`opponent_shortcuts`) that is open put in place of the stretch it cuts
  off. A closed shortcut means the main-route stretch is used again; the
  choice is remade whenever the track changes. For other blockages it has
  Opponent 1's detour.
- **Opponent 3, `shortest`.** Checkpoint-aware Dijkstra on distance for the
  rest of the race; recomputed after every relevant event.
- **Off the lap** (after a fuel detour, or when a detour ends under it):
  Opponents 1 and 2 take the shortest-distance path to their next mandatory
  vertex and continue on their lap from there.
- **Refuelling (all three).** At an active station on the route an opponent
  fills up (min(40, whole units of tank room)) when the station is
  *eligible*: fuel below 25% of the tank, or fuel below what the route needs
  to the next active station (or the end) plus `REFUEL_SAFETY_MARGIN = 2`.
  The second condition was added because the bare 25% rule strands cars on
  the built-in circuits. Opponent 3's "nearest reachable station" is the
  first station on its route; when its route has none in range, recovery
  rule 3 sends it (like everyone) to the nearest reachable one.
- **Nitro (all automatic racers, autopilot included).** On entering a road,
  fire if a charge is held, no boost is running, the road has no oil or speed
  restriction, lasts at least 4 s, its effective difficulty is at most the
  racer's limit (`NITRO_AUTO_MAX_DIFFICULTY`: fixed 2, shortcut 3,
  shortest 1, autopilot 2), and fuel >= fuel to the next active station on
  the route (or its end) + the worst extra the boost can burn + the margin.
- **More racers.** `default_racers(n)` gives the player plus n opponents
  (n <= 9), strategies repeating fixed, shortcut, shortest. Racer ids are
  list positions; the player is 0.

### Routing (`routing.py`)
- One search per leg; a leg with no route gives `found=False` and names the
  target. The player's line uses A*, Opponent 3 Dijkstra. `RoutePlan` carries
  distance, time, fuel, the exact scalar cost and the summed search counters.
- A plan covers the whole rest of the race (all remaining laps).

### Resource planner (`resources.py`, Project.md 5.3)
- **Knapsack items** = optional service vertices for a given route and racer:
  active nitro pickups while a charge slot is free, and active fuel stations
  that are not on the route when the refuel DP finds no plan for the route.
- **Cost c_i** (integer) = extra travel time of the cheapest out-and-back
  loop from a route vertex to the pickup and back to the same vertex
  (two Dijkstra searches on effective time), in tenths of a second, rounded
  up (`PICKUP_COST_SCALE = 10`). A pickup on the route costs 0.
- **Budget B** = detour time the racer accepts for one plan, default
  `PICKUP_DETOUR_BUDGET = 6 s` -> 60. Only time is in the budget.
- **Benefit v_i**: nitro pickup = 20 (`PICKUP_NITRO_BENEFIT`: the 2.0 s one
  activation saves, in tenths); fuel station = min(40, fuel the route needs
  beyond the tank), in units.
- **Nitro capacity** is a second constraint, handled before the knapsack: only
  the cheapest (3 - charges) nitro items are offered. They all have the same
  benefit, so nothing better is lost.
- **Fuel** is a third resource and is not converted into the budget. The
  chosen loops are spliced into the route and the refuel DP runs on the
  result; while it is infeasible the thirstiest loop is dropped (nitro loops
  before stations). `PickupPlan.feasible` is the DP verdict for the returned
  route, so a recommendation never breaks tank or station rules.
- Never offered: an inactive pickup, a pickup with no path out and back, the
  current vertex.
- **DP and greedy** are both solved and returned. The player's autopilot
  applies the DP selection (`pickup_solver="dp"`, default) or the greedy one
  (`"greedy"`), or none (`None`). The choice is the **Pickup planner** setting of
  Quick Race (`Settings.pickup_solver`: dp, greedy, none), passed through
  `RaceScreen` and the championship flow to `create_race`. The autopilot keeps
  its latest `PickupPlan` (`Autopilot.last_picks`) and the Racing Screen's
  controls panel shows "Planner DP: DP x vs greedy y, n pickup(s)", so the
  two solvers' benefits are visible during play; the Explorer's resource tab
  shows the same comparison before the race. The fuel check above applies to
  either solver, so a greedy plan is also feasible (tested for both).
- **Refuel plan.** Stops = the current vertex (fuel on sale only if it is an
  active station) and each later visit to an active station on the route.
  The autopilot runs the DP with 2 units held back and buys its first
  purchase; if the DP finds no plan it fills up.

### Scoring and championship (`championship.py`)
- Classification: finishers by time then id; the rest by laps, checkpoints of
  the current lap, elapsed time, id (merge sort with one comparator).
- **Live order** uses the same comparator, with "planned time to the next
  mandatory vertex" in place of elapsed time for cars still running, and a
  DNF car behind a running car on equal laps and checkpoints.
  `live_top_k(k)` gets the leaders from the size-k heap.
- Points 25..1 to finishers only. **Fastest-lap bonus:** +1 to the finisher
  with the lowest lap time among finishers (ties: lower id); a lap set by a
  racer who did not finish earns nothing.
- A win is a first place with a finish time. `sum_of_finish_positions` uses
  the classification position, finished or not.
- Standings: merge sort by default, quick and heap sort on request, all with
  `championship_less`; `Championship.top(k)` uses the size-k heap. The
  champion is the leader after the last race.
- `create_race` loads a built-in circuit fresh for each race because events
  change the graph.

## Algorithm integration map

Every gameplay call goes to the one implementation in `smart_racing/algorithms/`.

| # | Algorithm | Function | Gameplay call sites |
|---|---|---|---|
| 1 | BFS | `bfs.bfs` | `tracks/validator.validate`: ordered checkpoint and lap-return reachability of every circuit that is loaded or generated; `tracks/generator`: hop bounds for loop-closure pruning. Track Explorer reachability (Phase 5). Championship briefing (`ui/screens/championship.scouting`): checkpoints reachable and fewest roads Start to Finish. Not called inside the per-tick race loop. |
| 2 | DFS | `dfs.dfs`, `find_cycle`, `connected_components`, `dead_ends`, `enumerate_paths` | `validator.validate`: cycle, dead end and two Start-Finish routes; `generator`: candidate-graph connectivity and the critical-bridge pruning rule. Explorer alternative routes (Phase 5). Championship briefing: cycle and dead ends of the circuit about to be raced. Not called inside the per-tick race loop. |
| 3 | Dijkstra | `dijkstra.dijkstra` | `engine/routing.plan_through` for Opponent 3 (`opponents.ShortestDistance.plan`, distance cost); `routing.nearest_station` (recovery rule 3, fuel cost); `opponents.FixedRoute.plan` (rejoining the lap); `resources.pickup_plan` (detour loops, time cost); `validator.checkpoint_route` (fuel rule). |
| 4 | A* | `astar.astar` | `routing.plan_through` for the player's recommended line (`opponents.Autopilot.plan`), at race start and at every re-plan in `race.RaceEngine._replan`; `routing.compare_presets` for the route comparison. |
| 5 | Dynamic programming | `knapsack.knapsack_dp`, `refuel.plan_refuel` | `resources.pickup_plan` (pickups added to the autopilot route); `resources.refuel_plan`, called by `Autopilot.refuel_amount` at every station and by `pickup_plan` as the fuel check; `validator.fuel_plan`. |
| 6 | Greedy | `knapsack.knapsack_greedy` | `resources.pickup_plan`: returned beside the DP for the recommendation panel and applied to the autopilot route when the Quick Race "Pickup planner" setting (or `create_race(pickup_solver="greedy")`) selects it; the Racing Screen shows both benefits. |
| 7 | Backtracking | `backtracking.solve` | `tracks/generator`: main-loop search and placement of shortcuts, stations, checkpoints, pickups and obstacle sites for generated circuits. |
| 8 | Kruskal (MST) | `mst.kruskal` | `tracks/generator`: road backbone of a generated circuit. |
| 9 | Heap / priority queue | `heap.MinHeap` | `engine/events.EventQueue` (every race event, popped by `RaceEngine.step`); frontier of Dijkstra and A*; `topk.top_k` in `RaceEngine.live_top_k` (running order) and `Championship.top` (standings). |
| 10 | Merge sort | `sorting.merge_sort` | `Championship.standings` (default); `RaceEngine.running_order` / `classification` (race positions and final result); edge order in Kruskal; item order in greedy knapsack. |
| 11 | Quick sort | `sorting.quick_sort` | `Championship.standings("quick")`, selectable on the dashboard. |
| 12 | Heap sort | `sorting.heap_sort` | `Championship.standings("heap")`, selectable on the dashboard. |

## Phase 6: GUI part 2 decisions
- **Lab replay.** `ui/lab_registry.py` maps each Lab name to the gameplay function (`ALGOS[name].fn is` the function
  in `smart_racing.algorithms`, `EventQueue` for the heap) and records its `observer` steps. The event heap has no
  observer, so the Lab drives the same `EventQueue` calls (schedule, cancel, pop_due) and records each one with a
  snapshot of the track effects. Counters shown live are rebuilt from the replayed steps; the rest appear at the last
  step and equal the result object's counters (tested against a direct call with no observer).
- **Lab data.** Graph searches: Start to checkpoint 6 of the chosen circuit (click to change). Knapsack: the brief's
  A/B/C example, two greedy traps, a random set, or the circuit's own pickup options (editable). Backtracking: fuel
  stations spaced along the main route (cyclic gap, off mandatory vertices). Kruskal: all roads weighted by length.
  Sorts: 12 or 24 sample entries or the current championship standings; the three sorts run side by side.
- **Championship flow.** `app.flow` holds the `Championship` and the phase (briefing, results, champion), so leaving a
  screen never loses progress; Esc/Back at a point with recorded races asks first, and "Championship" in the menu
  resumes it. A finished championship is replaced by a new one on the next menu click.
- **Dashboard data.** The championship in progress, a sample championship (three one-lap races run headless) or a
  200-entry sample field, which makes top-k against n visible. Sorts and top-k are `Championship.standings/top`.
- **Generator view** shows the accepted attempt's stages; rejected attempts appear as text with the validator's reasons.
  Saved circuits go to `~/.smart_racing/generated_seed<N>.json`.
- **Multi-objective** is the Explorer's Compare tab (three modes), with the weights table and the limits of one scalar.

## Audit additions (Project.md clause review, docs/AUDIT.md)

### Cost normalisation rationale (Project.md 3.3)
- Terms: `D/100`, `T/10`, `F/10` (reference values `DIST_REF`, `TIME_REF`,
  `FUEL_REF`), `R = (difficulty - 1)/4` and `O` (obstacle penalty) are already
  in [0, 1]. References are round numbers near the upper range of the
  built-in edges (distance 57 to 316, median 177; time 1.3 to 9.6, median 4.2;
  fuel 0.8 to 13, median 2.7), so the T, F, R, O terms are of order 0 to 1 and
  none of them is switched off by its unit. The distance term is the largest
  (median 1.8 against 0.4 for time and 0.3 for fuel): distance is the longest
  quantity in the data and Balanced keeps weight 1 on it as the brief's
  "moderate weights". The presets then tilt the weights: Speed raises wT to 3
  and cuts wF to 0.25, Economy raises wF to 3, Safety raises wR and wO to 3.
  All weights are >= 0, so every edge cost is >= 0 and Dijkstra applies.
- The cost shown to the player is `route_summary(...)["cost"]`, summed from the
  same `cost_fn` the search minimised. Different presets choose different
  routes: Speed and Economy differ on at least one circuit and Grand Ring gives at least three distinct routes
  (`tests/test_tracks.py::test_presets_choose_different_routes`).
- Limit: a weighted sum depends on the reference values and weights; changing
  them changes the winner, and it can miss Pareto-optimal routes.

### Backtracking: worst case and pruning (Project.md 5.4)
- With `n` variables and domains of size `d`, plain backtracking can try
  `O(d^n)` assignments (exponential), for example placing 10 ordered
  checkpoints, stations and pickups on a 20-vertex loop. The search is
  exhaustive only when no pruning applies and the node limit is not hit.
- Each pruning rule (see Generator) rejects a partial assignment as soon as a
  hard requirement is violated, so the whole subtree below it is skipped.
  Rules are safe because each tests a necessary condition of a valid track
  (a lower bound such as BFS hops, a spacing or degree cap, or "enough free
  positions remain"), never a preference. `nodes`, `prunes` and `backtracks`
  are counted; `GEN_LOOP_NODE_LIMIT` and the 20-attempt retry limit bound the
  work, and exceeding them ends the search with no solution (the generator then retries or rejects
  the candidate), never a hang.

### Lazy deletion trade-off (Project.md 4.5)
- Cancelling marks the event `cancelled` in O(1) and leaves it in the heap;
  `pop_due` discards it at the top. This is simpler than deleting from the
  middle of a binary heap (O(n) search or an index map), at the cost of
  cancelled entries using memory until they reach the top.

### Never frozen silently (Project.md 5.4)
- A racer cut off from the finish re-plans (rule 1), then waits with a
  visible reason ("no open route", "fuel station closed", "out of fuel"),
  and is DNF after 60 s or at once when no pending event can change the
  graph (rule 4). Waiting and DNF are written to the race log (`wait`, `dnf`
  entries with the reason) and shown in the event feed; the policy cannot hang
  (see Recovery policy).

### Where the knapsack and refuel DP are specified
- `knapsack_dp` docstring: state `dp[i][b]`, base case `dp[0][b] = 0`,
  recurrence, strict-improvement tie rule, traceback, O(mB) time and space,
  pseudo-polynomial in B. `plan_refuel` docstring: state `dp[j][f]`, base case,
  transition with `0 <= a <= min(max_purchase, capacity - f)`, rounding rules,
  unreachable states skipped, O(m C^2) with C in `FUEL_SCALE` units
  (`FUEL_SCALE = 10` multiplies the fuel axis, hence the state count, by 10;
  purchases are whole units to keep the inner loop at most 41 values).
  Replay in the engine: `test_recommended_pickup_and_refuel_plan_is_feasible_in_the_engine`
  runs the autopilot with each solver on every circuit and checks it finishes
  with non-negative fuel and no DNF.

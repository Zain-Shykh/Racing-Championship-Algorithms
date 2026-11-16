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

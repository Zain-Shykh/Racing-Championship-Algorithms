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

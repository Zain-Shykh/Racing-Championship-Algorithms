## CHAMPIONSHIP SMART RACING

## THE ALGORITHMIC RACING CHALLENGE

## Deadline: 05 December 2026, 11:59 PM


## 1. Project Instructions and Executive Summary

- Submit through Google Classroom. Upload one ZIP named using the registration numbers of the actual group members followed by the section 24I-XXXX_24I-YYYY_24I-ZZZZ_Section.zip

- Groups may contain up to three members. One member submits for the group. All members must contribute, understand the complete implementation, and attend the demonstration and viva.

- Submit a functional, executable application, source code, required assets, setup/run instructions, technical report and experimental results.

- Check the ZIP for missing files, corruption, and malware and submission errors. Copying code from other groups is prohibited. Acknowledge permitted third-party libraries/assets.

- Late submissions will not be accepted unless an official course policy states otherwise.

Smart Racing Championship is a 2D top-down racing game that demonstrates algorithms in a changing road network. Circuits contain intersections, checkpoints, alternative routes, shortcuts, fuel stations, nitro pickups and obstacles. The player plans routes, manages limited resources, responds to road events and competes against deterministic computer-controlled opponents.

This is an algorithms project, not primarily a graphics project. Assessment emphasizes correct problem modelling, algorithm implementation, integration into gameplay, complexity analysis, testing and measurable results. Machine learning and reinforcement learning are not used; opponents follow fixed, deterministic rules.

| Dimension | Minimum requirement |
| --- | --- |
| Playable circuits | 3 |
| Mandatory checkpoints | 10 per circuit |
| Shortcuts | 2 per circuit |
| Racers | 1 human player + at least 3 computer opponents |
| GUI screens | 5 (Section 2) |
| Mandatory algorithm families | 12 (Section 6) |
| Experimental studies | 5 (Section 7) |
| Advanced challenges | 3 (Section 8; extension/bonus) |
| Deliverables | Game, source code, visualization, report, experiments, demo and viva |

Design principle: every mandatory algorithm must have a functional role in the actual game. The Algorithm Lab must call the same algorithm implementation used by gameplay; a detached duplicate demonstration does not satisfy integration.

## 2. Game Concept, Modes and Screens

## 2.1 Game modes and required GUI screens

| Screen / mode | Required functionality | Algorithms / purpose |
| --- | --- | --- |
| 1. Main Menu | Start Championship, Quick Race or Algorithm Lab; show instructions/settings. | Navigation and configuration. |


## SMART RACING CHAMPIONSHIP | DESIGN AND ANALYSIS OF ALGORITHMS

| 2. Track Explorer / Route Planner | Display graph, reachable checkpoints, alternative paths, route costs and route comparison. | BFS, DFS, Dijkstra, A*. |
| --- | --- | --- |
| 3. Racing Screen | Display cars, roads, checkpoints, fuel, nitro, race time and dynamic events. | Routing, resource planning and event heap. |
| 4. Algorithm Lab / Visualization | Step through algorithms on the current track/data and show counters. | Same code as gameplay. |
| 5. Championship Dashboard | Race results, standings, statistics and top-k view. | Merge Sort, Quick Sort, Heap Sort, priority queue. |

The five screens may be arranged in a sensible navigation flow or combined visually, but all listed functions must be accessible.

## 2.2 Championship flow

- 1. Open the Main Menu and select Championship, Quick Race or Algorithm Lab.

- 2. Select a circuit, or follow the predefined championship circuit order.

- 3. Inspect the graph, compare route options and review resource recommendations.

- 4. Start the race. Cars follow valid graph edges; resources are consumed; events are processed; routes are recalculated after relevant graph changes.

- 5. Record results and award points after all racers finish or the time limit expires.

- 6. Update the leaderboard using the common comparator and sorting algorithms.

- 7. Repeat for each race; declare the champion after the final race.

## 2.3 Core loop and strategic decisions

Plan: BFS/DFS explore the circuit; Dijkstra/A* compare routes; DP/greedy recommend resource choices.

Race: the event heap processes scheduled changes; the graph is updated and routes are recalculated.

Review: sorting and top-k retrieval update standings.

- Compare a short, difficult route with a longer, safer route.

- Decide whether to use or save nitro.

- Determine whether a shortcut is worth its fuel/difficulty cost.

- Choose whether and where to refuel.

- Respond to a road closure by finding a valid alternative or applying the documented recovery rule.

## 3. Core Data Model

## 3.1 Track graph

Represent each circuit as G=(V,E). Intersections, checkpoints, start/finish points, fuel stations and nitro pickups are vertices; roads are edges. Use adjacency lists: O(V+E) memory and efficient neighbour


## SMART RACING CHAMPIONSHIP | DESIGN AND ANALYSIS OF ALGORITHMS

iteration for sparse road networks. An adjacency matrix uses O(V²) memory and is less suitable for sparse circuits.

| Vertex field | Meaning |
| --- | --- |
| id | Unique integer identifier. |
| x, y | Map coordinates; may be used by the A* heuristic. |
| type | Start, Finish, Checkpoint, Intersection, FuelStation, NitroPickup or DeadEnd. |
| checkpointOrder | Required order for a mandatory checkpoint; otherwise none. |
| active | Whether a service vertex is currently available. |

| Edge field | Meaning |
| --- | --- |
| id | Unique identifier; events refer to an edge by ID. |
| from, to | Endpoint vertices. |
| distance | Non-negative road length. |
| baseTime | Non-negative estimated travel time at normal speed. |
| fuelCost | Non-negative base fuel required to traverse the edge. |
| difficulty | Integer 1 (easy) to 5 (hard). |
| status | Open, Blocked or Restricted. |
| isShortcut | Whether the road is a designated shortcut. |
| directed | If false, traversable in both directions; if true, one-way. |

Dynamic updates must support blocking/unblocking edges and activating/deactivating service vertices without rebuilding the whole graph. Blocked edges are excluded from route searches. Restricted edges remain traversable but their effective time/cost must reflect the restriction.

## 3.2 Other records

| Record | Key fields |
| --- | --- |
| Racer | id, name, isHuman, strategyType, currentVertex, fuel, nitroCharges, lap, nextCheckpoint, totalTime |
| RaceResult | raceId, racerId, finishPosition, finishTime, fastestLap, bonusPoints, pointsAwarded |
| ChampionshipEntry | racerId, totalPoints, wins, sumOfFinishPositions, bestFastestLap |
| Event | eventId, type, triggerTime, priority, insertionSequence, targetEdgeOrVertex, duration, cancelled |


## 3.3 Route cost and normalization

Use a non-negative scalar edge cost so Dijkstra is applicable:

- D, T, F, R and O denote distance, travel time, fuel use, difficulty penalty and obstacle penalty. These attributes have different units/scales: normalize them using documented reference values before combining them. All weights must be non-negative. State the normalization, weights and rationale. The cost displayed to the player must be the same cost optimized by the algorithm.

| Preset | Emphasis |
| --- | --- |
| Balanced | Moderate normalized weights across all criteria. |
| Speed | High time weight; lower fuel weight. |
| Economy | High fuel weight. |
| Safety | High difficulty and obstacle weights. |

Demonstrate at least one circuit where different presets select different routes.

## 4. Game Rules and Mechanics

## 4.1 Racing environment

| Feature | Minimum requirement |
| --- | --- |
| Circuits | 3 different playable topologies. |
| Checkpoints | At least 10 mandatory checkpoints per circuit. |
| Intersections | Multiple intersections, alternative paths, at least one cycle and one dead end per circuit. |
| Shortcuts | At least 2 per circuit. |
| Road conditions | Several difficulty levels. |
| Services | Fuel stations and nitro pickups. |
| Dynamic elements | Obstacles and road closures. |
| Race structure | Multiple laps with mandatory checkpoint progression. |

## 4.2 Race rules

- 1. All racers start at the start vertex with full fuel and the configured initial nitro allocation.

- 2. A race uses a fixed number of laps (recommended: 2 or 3). A lap counts only after all mandatory checkpoints have been visited in the required order and the racer crosses the defined lap boundary.

- 3. Skipping a mandatory checkpoint does not complete the lap; the racer must return and visit it in order.

- 4. A shortcut may be used only while its edge is open and traversal is legal.

- 5. Cars must stay on valid graph edges.

- 6. A car without enough fuel for the next edge must stop. If no permitted refuelling/recovery route exists, it is DNF (Did Not Finish).


## SMART RACING CHAMPIONSHIP | DESIGN AND ANALYSIS OF ALGORITHMS

- 7. Finish order is based on finishing time; exact ties are broken by lower racer ID.

- 8. If a time limit is used, unfinished racers are ranked by laps completed, checkpoints completed, elapsed time, then racer ID. State consistently whether they receive points.

## 4.3 Fuel and nitro

| Parameter | Suggested default | Rule |
| --- | --- | --- |
| Maximum fuel | 100 units | Full tank at start. |
| Fuel per edge | fuelCost × difficulty multiplier | Multiplier = 1.0 + 0.1 × (difficulty − 1). |
| Fuel station | Up to 40 units per stop | A fixed stop time applies for any positive purchase. |
| Maximum nitro | 3 charges | Collected from active pickups; capacity cannot be exceeded. |
| Nitro effect | 1.5× speed for 4 seconds | One charge per activation. |
| Nitro fuel penalty | 2× fuel consumption while active | Apply to the affected route portion. |

The same rules apply to the player and opponents. Teams may tune values but must freeze and document them before testing. DP requires discrete resource states: if fuel or detour costs are fractional, define a scaling unit (for example, tenths of a unit) and explain its effect on state-space size.

## 4.4 Deterministic computer opponents

Opponents must behave identically given the same track, event sequence and starting conditions. No learning or machine learning is required.

| Opponent | Strategy | Blocked-road response Refuelling |   |
| --- | --- | --- | --- |
| 1 | Follow a fixed main route stored for the circuit. | Use a documented fixed detour; otherwise wait/recover. | First eligible station below 25% fuel. |
| 2 | Use a designated shortcut whenever open and legal. | Fall back to main route if shortcut closes. | First eligible station below 25% fuel. |
| 3 | Choose the available route with minimum total distance. | Recompute shortest- distance route. | Nearest reachable station on route below 25% fuel. |

All opponents must obey checkpoint order, fuel constraints and road boundaries. If no valid route exists, use the documented recovery policy. The recovery policy must be identical for all racers unless a rule explicitly states otherwise; record whether waiting, rerouting, or DNF is applied and how elapsed time is counted.


## 4.5 Race events and priority queue

Use a min-heap keyed by (triggerTime, priority, insertionSequence). Lower priority number fires first when trigger times tie; insertion sequence makes all ties deterministic.

| Event | Effect | Duration | Priority |
| --- | --- | --- | --- |
| Road blockage | Set edge Blocked; exclude from routing. | Until cleared | 1 |
| Shortcut open/close | Toggle shortcut Open/Blocked. | Until reversed | 2 |
| Oil spill | Increase effective difficulty/reduce speed. | About 20 sec | 3 |
| Speed restriction | Cap speed on an edge/region. | About 15 sec | 4 |
| Fuel station availability | Activate/deactivate station. | About 30 sec | 5 |
| Nitro booster | Activate pickup vertex. | Until collected or about 25 sec | 6 |

- Apply all events with the same trigger time in heap order before recalculating routes. For overlapping temporary effects, store each effect independently with its own expiry/event ID. Recompute the effective edge state from all currently active effects in a documented order (for example, maximum difficulty penalty and the strictest active speed cap). Expiring one effect must not erase another effect that is still active. Schedule expiry events deterministically.

- Cancellation uses lazy deletion: mark an event cancelled and ignore it when it reaches the heap top. Explain the simplicity/memory trade-off.

- Validate that an event target exists and that the event is valid in the current state.

- Temporary effects must have a clear/restore action. Explain how overlapping effects on the same edge are handled.

## 4.6 Championship scoring and tie-breaking

| Position | Points |
| --- | --- |
| 1st | 25 |
| 2nd | 18 |
| 3rd | 15 |
| 4th | 12 |
| 5th | 10 |
| 6th | 8 |
| 7th | 6 |
| 8th | 4 |
| 9th | 2 |
| 10th | 1 |


Implement the full table for up to ten racers. Define any bonus points before testing. When championship points tie, compare: (1) higher race wins; (2) lower sum of finishing positions; (3) lower best fastest-lap time; (4) lower racer ID. Lower lap time is better. This total order must be used by every sorting method and top-k retrieval.

## 5. The Five Acts

## 5.1 Act 1 — Circuit Explorer: BFS and DFS

- Use adjacency lists and allow selection of any start/destination vertex.

- Show reachable checkpoints and report unreachable destinations.

- Support cycles, dead ends, branching roads and disconnected sections.

- BFS finds a path with the minimum number of edges in an unweighted graph. It does not necessarily minimize distance, travel time or the weighted route cost.

- DFS supports traversal, cycle detection, connected components and dead-end analysis.

| Algorithm | Role | Structures | Complexity |
| --- | --- | --- | --- |
| BFS | Reachability and minimum-edge path. | Queue, visited, parent. | O(V+E) time; O(V) auxiliary space. |
| DFS | Traversal, cycles, components and dead ends. | Stack/recursion, visited/discovery arrays. | O(V+E) time; O(V) auxiliary space. |

Important correction: one DFS traversal is O(V+E), but enumerating all simple paths can be exponential in the worst case. If the alternative-route panel enumerates paths, impose and document a route-count or path-length limit. Define a dead end as a non-mandatory vertex from which the finish cannot be reached without reversing. Define an alternative route as a simple start-to-finish path differing from the selected main route by at least one edge.

Example: direct S–T has length 10; S–A–B–T has three edges of length 2. BFS chooses S–T (one edge), while the other path has distance 6. BFS minimizes edge count, not weighted distance.

- Test connected, disconnected, cyclic, branching and single-vertex graphs.

- Verify BFS returns minimum edge count.

- Show DFS detects a cycle and a dead end.

- Unreachable destinations must not crash or loop indefinitely.

## 5.2 Act 2 — Route Optimization: Dijkstra and A*

Compute routes between selected vertices and route legs through mandatory checkpoints in order.

Checkpoint-aware routing rule: the route planner must preserve checkpoint order. A practical implementation runs a shortest-path search from the racer's current vertex to the next required checkpoint, then repeats for subsequent checkpoints and the finish. After a closure or cost update, recompute from the current state. Do not let a route skip a mandatory checkpoint.


- Display distance, estimated time and the exact scalar cost optimized.

- Compare at least two candidate routes.

- Recalculate when an active-route edge is blocked or its cost changes.

| Algorithm | Role | Complexity |
| --- | --- | --- |
| Dijkstra | Optimal path for non-negative edge costs. | O((V+E) log V) with a suitable binary heap. |
| A* | Heuristic-guided optimal path search. | Worst case comparable to Dijkstra; practical performance depends on heuristic. |

A* heuristic must be admissible (never overestimate remaining optimal cost). For distance-only routing, Euclidean distance is admissible when each edge length is at least the straight-line distance between its endpoints. For the weighted scalar cost, multiply straight-line distance by a valid minimum edge-cost-per- distance ratio. If that ratio is zero or not a valid lower bound, use h=0 or another proven lower bound. For checkpoint-constrained racing, plan each leg to the next required checkpoint and update the racer's checkpoint-progress state; a shortest path directly to the finish is not sufficient when checkpoints remain.

A consistent heuristic satisfies h(u) ≤ cost(u,v)+h(v). With consistency, standard graph-search A* need not reopen closed vertices. With an admissible but inconsistent heuristic, reopening may be required to preserve optimality. State which case the implementation supports.

Test source=target, unreachable target, blocked edges, equal-cost paths, zero-weight edges, long routes and immediate recalculation. Record expanded vertices, relaxed edges, heap operations, final path cost and execution time. Do not require A* to expand fewer vertices in every test: depending on the heuristic, graph and tie-breaking, it may expand fewer, equal or more vertices than Dijkstra.

- Dijkstra must be optimal for all tested non-negative edge-cost graphs.

- A* must return the same optimal path cost when its heuristic and implementation satisfy the required conditions.

- Blocked edges are excluded; route recalculation uses the updated graph.

- Display/export the required counters for Experiment 2.

## 5.3 Act 3 — Fuel and Nitro: DP and Greedy

The resource planner recommends optional pickups and refuelling decisions. Its model must match the race engine's rules.

## Problem A: 0/1 Knapsack

For each pickup i, define integer cost cᵢ (for example, scaled detour fuel or time), benefit vᵢ, and total budget B. Each item can be selected at most once. Keep the interpretation of cᵢ explicit: a single scalar budget may represent a documented combined detour penalty, but it must not silently treat fuel, time and nitro as interchangeable physical resources.


Base case: dp[0][b]=0 for all b. For strictly positive costs, dp[i][0]=0. Recover selected items by tracing the table. Complexity is O(mB) time and O(mB) space with reconstruction; O(B) space is possible if only the value is required. This is pseudo-polynomial in numeric budget B.

## Problem B: Refuelling DP (recommended extension)

For a fixed route whose ordered stops are fuel stations 0…m−1 followed by the destination m, let dⱼ be the fuel required from stop j to stop j+1 and C the tank capacity. Define dp[j][f] as the minimum additional stop time on arrival at stop j with f discrete fuel units. At an available station j, consider buying a units subject to 0 ≤ a ≤ min(C−f, 40), where 40 is the stated maximum purchase per stop (adjust this bound if the team changes the game rule). At a non-station destination, no purchase is allowed. If f+a ≥ dⱼ, transition to dp[j+1][f+a−dⱼ]. Use stopTime(0)=0 and the documented fixed stop time for a>0. Initialize the first state using the racer's actual starting fuel. The destination is feasible if a reachable state arrives with non-negative fuel. Direct complexity is O(mC²) in the straightforward implementation; explain unreachable states and the chosen fuel unit.

## Greedy comparison

Greedy sorts by vᵢ/cᵢ and selects in order while items fit. Define handling of zero-cost items and deterministic ties. This heuristic is not guaranteed optimal for 0/1 Knapsack.

Greedy implementation detail: process zero-cost positive-benefit items before ratio sorting; define how zero-cost zero-benefit items are handled. For equal ratios, use a deterministic tie-break (for example, lower item ID). The greedy result is a feasible heuristic, not an optimality guarantee.

| Item | Cost | Benefit | Ratio |
| --- | --- | --- | --- |
| A | 6 | 30 | 5.0 |
| B | 5 | 24 | 4.8 |
| C | 5 | 24 | 4.8 |

For budget 10, greedy selects A for benefit 30; DP selects B+C for benefit 48. Students must create two further cases where greedy is worse and verify DP against exhaustive search on small instances.

Fuel, nitro and detour time are distinct resources. A single Knapsack budget is valid only if the team defines a defensible scalar cost. If multiple independent constraints are enforced, model the multi-constraint problem explicitly. The planner must never recommend a plan that violates the route, tank capacity, pickup availability or race rules.

- Document DP state, recurrence, base cases, transitions, reconstruction and complexity.

- Match exhaustive search on small cases.

- Provide at least two team-created greedy-suboptimal examples.

- Demonstrate that recommendations are feasible in gameplay.

*5.4 Act 4 — Dynamic Track, Heaps, MST and Backtracking*

| Technique | Role | Complexity |
| --- | --- | --- |


## SMART RACING CHAMPIONSHIP | DESIGN AND ANALYSIS OF ALGORITHMS

| Backtracking | Generate configurations satisfying track constraints. | Exponential worst case; pruning may reduce explored states. |
| --- | --- | --- |
| Prim or Kruskal | Build undirected MST backbone. | Prim binary heap O(E log V); Kruskal O(E log E) with union- find. |
| Min-heap priority queue | Schedule race events. | O(log n) insert/extract; O(1) peek. |
| Dijkstra or A* | Recompute after graph changes. See Act 2. |   |

Generation pipeline: place vertices; create candidate undirected roads; build an MST; add extra roads for cycles/alternatives/shortcuts; use backtracking to place checkpoints, services and obstacles; validate and retry up to a documented limit. The candidate undirected graph must be connected before an MST is computed; otherwise the result is a minimum spanning forest, not one spanning tree.

An MST backbone is undirected. Add one-way roads after constructing it, then validate directed reachability. An MST alone has no cycles or alternative paths; extra edges are necessary. A connected graph is not automatically playable: validation must confirm ordered checkpoint reachability, lap/return feasibility, at least two alternative start-finish routes where required, and at least one feasible fuel plan. If one-way roads are added, validate reachability in the resulting directed graph for every required checkpoint sequence and the return/lap transition.

Document pruning rules (fuel-station spacing, obstacle spacing, maximum degree, avoiding removal of critical bridge edges). Explain what each rule prunes and why it is safe. If an event disconnects a racer from the finish, find a valid alternative or apply a documented recovery rule such as waiting for a road to reopen. Never freeze silently.

- Generated tracks pass the validator; invalid tracks are rejected.

- Events are processed deterministically, including simultaneous and cancelled events.

- A road closure triggers route recalculation without restarting the race.

- Explain worst-case backtracking behaviour and pruning.

*5.5 Act 5 — Championship: Sorting and Top-k*

| Method | Role | Complexity / notes |
| --- | --- | --- |
| Merge Sort | Primary ranking. | O(n log n) all cases; O(n) extra space; stable. |
| Quick Sort | Alternative ranking. | O(n log n) average; O(n²) worst; state pivot/partition; three-way partition helps duplicates. |
| Heap Sort | Third ranking method. | O(n log n); in-place; not stable. |
| Priority queue | Top-k retrieval. | Size-k heap: O(n log k), O(k) space; or heapify O(n) then k extracts O(k log n). |


Compare top-k retrieval with full sorting for different n and k. All sorting methods and top-k must use the exact same total comparator from Section 4.6. Complete rankings must match exactly.

- Test random, sorted, reverse-sorted, duplicate-heavy and single-element inputs.

- All three sorting methods agree.

- Top-k equals the first k entries of a full sort.

- Include a case requiring the final racer-ID tie-breaker.

## 6. Mandatory Algorithm Checklist

| # | Algorithm / technique | Required use |
| --- | --- | --- |
| 1 | BFS | Reachability and minimum-edge-count path. |
| 2 | DFS | Traversal, cycles, components and bounded alternative-path search. |
| 3 | Dijkstra | Optimal path with non-negative scalar costs. |
| 4 | A* | Heuristic-guided optimal path. |
| 5 | Dynamic programming | 0/1 Knapsack and/or refuelling plan. |
| 6 | Greedy | Benefit-to-cost pickup selection heuristic. |
| 7 | Backtracking | Constraint-based track generation/placement. |
| 8 | Prim or Kruskal | Undirected MST backbone; implement one. |
| 9 | Heap / priority queue | Race-event scheduling and top-k retrieval. |
| 10 | Merge Sort | Primary championship ranking. |
| 11 | Quick Sort | Alternative ranking and comparison. |
| 12 | Heap Sort | Third ranking implementation. |

Implement either Prim or Kruskal, not necessarily both. A heap is a supporting data structure used in multiple features. The report must distinguish algorithms from supporting data structures.

## 7. Five Required Experimental Studies

Use multiple input sizes and repeat timing runs (recommended: at least five runs after warm-up). Keep runtime conditions consistent. Report mean and, where useful, median or standard deviation. Include operation counters where specified.

For fair timing, use the same machine, build mode, compiler/interpreter settings and input instances for competing algorithms. Exclude rendering, file I/O and artificial delays from algorithm timing. Report whether measurements include data-structure initialization. Keep correctness checks separate from timed runs, and publish the raw measurements so results can be reproduced.

## Experiment 1 — BFS and DFS

- Vary vertices/edges and include sparse and denser graphs.

- Record runtime, visited vertices and examined edges.

- Verify BFS minimum edge count and DFS cycle/component results.


- Discuss observed growth against O(V+E).

## Experiment 2 — Dijkstra and A*

- Use multiple circuits/graph sizes with documented coordinates and costs.

- Record runtime, expanded vertices, relaxed edges, heap operations and final path cost.

- Verify equal optimal costs when A* conditions hold.

- Discuss cases where A* expands fewer, equal or more vertices.

## Experiment 3 — DP and Greedy

- Vary item count and budget; include the supplied example.

- Record benefit, selected items, runtime and DP state count.

- Include at least two cases where greedy is strictly worse.

- Compare DP with exhaustive search on small instances.

## Experiment 4 — Event Priority Queue

- Vary event count; measure insertion/extraction time and heap operations.

- Test equal timestamps, priority and sequence ties, cancellations and expirations.

- Verify order against (triggerTime, priority, insertionSequence).

## Experiment 5 — Sorting and Top-k

- Compare Merge, Quick and Heap Sort on random, sorted, reverse-sorted and duplicate-heavy inputs.

- Vary n; report runtime and comparison counts if implemented.

- Compare full sorting with size-k heap retrieval for small k and k close to n.

- Verify all rankings and top-k outputs against the common comparator.

## Required experiment report format

For each experiment include objective, hardware/software environment, input-generation method, dataset sizes, procedure, metrics, result table/chart, interpretation, limitations and conclusion. Separate theoretical complexity from measured runtime; do not infer complexity from one timing result.

## 8. Three Advanced Challenges

These are extension/bonus tasks unless the instructor explicitly makes them compulsory.

## Challenge 1 — Automatic track generation

Generate a new circuit using an MST backbone, extra edges and constraint-based placement. Show at least one invalid candidate rejected by the validator and explain why.

## Challenge 2 — Multi-objective route planning

Compare routes under balanced, speed, economy and safety presets. Explain the limitation of combining objectives into one weighted scalar cost and show how changing weights changes the chosen route.


## Challenge 3 — Efficient live championship analytics

Implement live top-k retrieval using a heap, compare it with full sorting and display the top racers. Explain the effect of k relative to n.

## 9. Testing, Report and Deliverables

## 9.1 Minimum test coverage

- Graph: single vertex, disconnected, cyclic, branching, dead-end, directed and undirected cases.

- Routing: source=target, unreachable target, blocked edge, equal-cost paths, zero-weight edges and graph changes during race.

- Resources: insufficient fuel, full tank, unavailable station, capacity limit, zero-cost pickup and infeasible plan.

- Events: simultaneous events, deterministic ties, cancellation, expiration, missing targets and overlapping effects.

- Sorting: empty/singleton, random, sorted, reverse-sorted and duplicate-heavy records; same comparator.

- Integration: complete race, multiple laps, ordered checkpoints, DNF, road closure and championship standings.

## 9.2 Technical report structure

- 1. Title page: project, course, section, group members and registration numbers.

- 2. Introduction and problem statement.

- 3. System architecture and game flow.

- 4. Graph/data models, assumptions, cost normalization and game rules.

- 5. Algorithm design: pseudocode, data structures, correctness reasoning and complexity.

- 6. Integration: where each algorithm is invoked in gameplay.

- 7. Testing strategy, test cases and results.

- 8. Five experiments with tables/charts and interpretation.

- 9. Limitations, advanced challenges completed and future improvements.

- 10. Conclusion and references/acknowledgements for permitted external assets or libraries.

## 9.3 Final deliverables

- Executable game and source code.

- Required assets and README with installation/execution instructions.

- Technical report in PDF.

- Algorithm visualization integrated with the same implementations used in gameplay.

- Experimental results and raw measurements/result files.

- One ZIP archive using the required naming convention.

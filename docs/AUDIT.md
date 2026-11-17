# Audit of Project.md (sections 1 to 9)

Status: MET, PARTIAL, MISSING. "Was" shows the status before this audit's fixes. Tests are in `tests/`.
Items marked REPORT can only be closed in `report/` (not editable here); the text to paste is in the audit hand-off.

| Clause | Status | Was | Evidence |
|---|---|---|---|
| 1 Submit playable app, source, README, report, results | MET | MET | `main.py`, `README.md`, `experiments/results/`, `scripts/package.py` |
| 1 Group names, registration numbers, ZIP name, viva | NOT VERIFIABLE | - | placeholders in report title page; human task |
| 1 Algorithm Lab calls gameplay code | MET | MET | `ui/lab_registry.py`; `test_registry_is_the_gameplay_functions`, `test_lab_counters_equal_direct_call` |
| 1 Minimums: 3 circuits, 10 checkpoints, 2 shortcuts, 3+ opponents | MET | MET | `tests/test_tracks.py::test_circuit_passes_validator_and_meets_minimums`, `config.NUM_OPPONENTS` |
| 2.1 Five screens | MET | MET | `ui/screens/` menu, explorer, race, lab, dashboard; `test_every_screen_opens_and_escape_returns` |
| 2.2 Championship flow (select circuit, inspect, race, points, leaderboard, champion) | MET | MET | `ui/screens/championship.py`, `engine/championship.py`, `test_full_three_race_championship` |
| 2.3 Short vs safe route, nitro, shortcut, refuel, closure response | MET | MET | Explorer Compare tab, `engine/opponents.wants_nitro`, `engine/race.py`, `RULES.md` recovery policy |
| 3.1 Adjacency lists, vertex/edge fields, dynamic block/activate, Restricted edges | MET | MET | `core/graph.py`, `tests/test_graph.py`, `test_events.py` |
| 3.2 Racer, RaceResult, ChampionshipEntry, Event records | MET | MET | `core/models.py`, `engine/events.py` |
| 3.3 Normalisation, weights, non-negative, displayed = optimised cost | MET | MET | `core/cost.py`, `route_summary`, report section 4 |
| 3.3 State rationale for normalisation | PARTIAL (docs) | PARTIAL | now `docs/RULES.md` "Cost normalisation rationale"; REPORT text below |
| 3.3 Different presets choose different routes on one circuit | MET | MET | `tests/test_tracks.py::test_presets_choose_different_routes` (Grand Ring 3+ routes) |
| 4.1 Cycle, dead end, several difficulties, services, obstacles, closures | MET | MET | `tracks/validator.py`, `test_circuit_race_data` |
| 4.2 rules 1-5, 7 (start, laps, order, shortcut, edges, ties by id) | MET | MET | `engine/race.py`; `test_skipping_a_checkpoint_does_not_complete_the_lap`, `test_complete_two_lap_race_on_every_circuit` |
| 4.2 rule 6 fuel stop, DNF | MET | MET | `RULES.md` recovery rule 3-4; `test_running_out_of_fuel_is_dnf_and_ranked_by_progress` |
| 4.2 rule 8 time limit ranking, "state whether unfinished racers get points" | MET | MET | SPEC 4.6 / `RULES.md`: no points; `test_unfinished_racers_score_nothing`, `test_time_limit_ends_the_race_for_everyone` |
| 4.3 Fuel/nitro table values, same rules for all | MET | MET | `config.py`, `test_nitro_speed_fuel_and_limits` |
| 4.3 DP scaling unit and effect on state space | MET | MET | SPEC 4.2 `FUEL_SCALE = 10`; `RULES.md` additions; `refuel.py` docstring (F = C*scale+1 states) |
| 4.4 Opponent 1 fixed route + documented detour | MET | MET | `RULES.md` Opponents; `test_road_closure_mid_race_reroutes_without_restart` (detour taken) |
| 4.4 Opponent 2 shortcut, fallback to main route when it closes | MET | MET | `test_opponent_2_takes_open_shortcuts_and_falls_back_when_closed` |
| 4.4 Opponent 3 min-distance, recompute | MET | MET | `test_opponent_3_drives_the_minimum_distance_route` |
| 4.4 Refuel rule (below 25%) | MET | MET | `config.LOW_FUEL_FRACTION`; documented extension (+ margin) in `RULES.md`; `test_opponents_refuel_at_an_eligible_station_and_use_nitro` |
| 4.4 Determinism, one recovery policy for all | MET | MET | `RULES.md` recovery policy; `test_identical_inputs_give_identical_results` |
| 4.5 Heap key (time, priority, sequence) | MET | MET | `engine/events.py`, `test_pop_order_is_time_then_priority_then_insertion` |
| 4.5 Simultaneous events applied in heap order, one replan after | PARTIAL | PARTIAL | `pop_due`, `RULES.md` Batching; new `test_simultaneous_events_apply_in_heap_order_then_one_replan_per_racer` |
| 4.5 Validate target exists and valid in current state | MET | MET | `EventQueue._apply`; `test_missing_target_or_invalid_state_is_rejected_with_a_reason`, `test_double_block_and_double_spawn_are_rejected` |
| 4.5 Overlap handling, independent effects, restore | MET | MET | `test_overlapping_effects_compose_and_expire_independently`, `RULES.md` Events |
| 4.5 Deterministic expiry events | MET | MET | `test_temporary_effect_schedules_its_own_expiry`, `test_expiry_falling_due_in_the_same_call_is_processed` |
| 4.5 Lazy deletion + trade-off explained | MET | MET | `test_cancelled_events_are_skipped_lazily`; report section 5; `RULES.md` additions |
| 4.6 Points table, bonus, comparator with 4 tie-breaks, single comparator | MET | MET | `championship_less`, `test_comparator_follows_every_tie_break_level`, `test_ten_racer_championship_uses_the_whole_points_table` |
| 5.1 Adjacency lists, any start/destination, reachable checkpoints, unreachable reported | MET | MET | `ui/screens/explorer.py`, `test_bfs_unreachable_and_disconnected` |
| 5.1 Dead end and alternative route definitions, path limit | MET | MET | `dfs.dead_ends`, `enumerate_paths` (`ALT_ROUTE_LIMIT`, `ALT_PATH_MAX_EDGES`), `RULES.md` |
| 5.1 Tests: connected, disconnected, cyclic, branching, single vertex; BFS min edges; DFS cycle and dead end | MET | MET | `tests/test_bfs_dfs.py` (S-T example, cycle, dead end tests) |
| 5.1 BFS/DFS actual gameplay use | PARTIAL | PARTIAL | validator, generator, Explorer, Lab, and now the championship briefing (`scouting`); `test_briefing_scouting_uses_gameplay_bfs_and_dfs`. Not in the per-tick race loop, stated in `RULES.md` map |
| 5.2 Checkpoint-ordered legs, recompute from current state | MET | MET | `engine/routing.py`, `test_route_visits_every_checkpoint_in_order`, `test_plan_from_checkpoint_progress` |
| 5.2 Heuristic admissible; consistency stated; reopening case | MET | MET | `astar.py` docstring (consistent, no reopen; ratio 0 gives Dijkstra); report section 5 |
| 5.2 Tests: source=target, unreachable, blocked, equal cost, zero weight, long routes, immediate recalc | MET | MET | `tests/test_shortest_path.py` (grid test, 40+10 random-graph cross-checks, `test_zero_weight_edges`, `test_equal_cost_paths_are_deterministic`, `test_blocked_edge_and_immediate_recalculation`) |
| 5.2 Counters: expanded, relaxed, heap ops, cost, time | MET | MET | `PathResult`, `test_counters_and_observer`, Exp 2 |
| 5.3 Knapsack DP: state, recurrence, base, reconstruction, complexity documented | PARTIAL | PARTIAL | `knapsack_dp` docstring and `RULES.md` (met in code docs); report only one line: REPORT text below |
| 5.3 Refuel DP documented (state, transitions, unreachable states, unit) | PARTIAL | PARTIAL | `plan_refuel` docstring, `RULES.md`; report only one line: REPORT text below |
| 5.3 Zero-cost items and ties in greedy defined and tested | MET | MET | `knapsack_greedy` docstring, `RULES.md`, `test_zero_cost_pickups`, `test_greedy_order_and_tie_break` |
| 5.3 DP equals exhaustive search | MET | MET | `test_dp_equals_exhaustive_on_random_instances` (200), Exp 3 sweep (500) |
| 5.3 At least two team-created greedy-suboptimal cases | PARTIAL | PARTIAL | tests held only the brief's variant and the textbook 10/20/30 case; added the two original Exp 3 team cases to `TEAM_CASES` |
| 5.3 Recommendations feasible in gameplay | PARTIAL | PARTIAL | `test_pickup_plan_never_recommends_what_fuel_cannot_cover`; new `test_recommended_pickup_and_refuel_plan_is_feasible_in_the_engine` (both solvers, all circuits) |
| 5.3 Greedy has a functional role in gameplay | PARTIAL | PARTIAL | Quick Race "Pickup planner" setting (dp, greedy, none) -> `Autopilot`; Racing Screen shows DP vs greedy benefit; `test_pickup_planner_setting_reaches_the_race_and_hud`, `test_autopilot_honours_the_pickup_solver_and_keeps_both_results` |
| 5.3 Fuel, nitro, time not silently merged | MET | MET | `RULES.md` Resource planner (time-only budget, nitro cap, fuel check) |
| 5.4 MST connected check, undirected, extra edges after | MET | MET | `generator.py`, `mst.py`, `tests/test_mst.py`, `test_generator.py` |
| 5.4 Validator confirms ordered reachability, return, 2 routes, fuel plan; invalid rejected | MET | MET | `validator.py`, `tests/test_tracks.py` rejection tests |
| 5.4 Pruning rules documented with why safe | MET | MET | `RULES.md` Generator (8 rules); report has one line: REPORT text below |
| 5.4 Worst-case backtracking explained | PARTIAL | PARTIAL | now `RULES.md` "Backtracking: worst case and pruning"; REPORT text below |
| 5.4 Closure triggers recalculation without restart | MET | MET | `test_road_closure_mid_race_reroutes_without_restart` |
| 5.4 Never freeze silently | PARTIAL | PARTIAL | recovery policy existed; `RULES.md` now states it explicitly; `test_closure_of_every_route_makes_racers_wait_then_dnf` |
| 5.5 Sorting shapes, three agree, same comparator | MET | MET | `tests/test_sorting_topk.py::datasets`, `test_three_sorts_agree` |
| 5.5 Case needing final racer-id tie-break | MET | MET | `id_tie_break` dataset, `test_final_racer_id_tie_break` |
| 5.5 Top-k equals first k; compare with full sort | MET | MET | `test_top_k_equals_prefix_of_full_sort`, Exp 5 |
| 6 Twelve algorithms, Prim or Kruskal, DS vs algorithms | MET | MET | `smart_racing/algorithms/`, report section 5-6 |
| 7 Five experiments: objective, environment, input generation, sizes, procedure, metrics, results, interpretation, limitations, conclusion | MET | MET | `experiments/results/SUMMARY.md` (all headings present for each) |
| 7 5+ runs after warm-up, mean/median/std, init stated, rendering excluded | MET | MET | SUMMARY lines 13-17 and each Procedure |
| 7 Raw measurements published; correctness separate from timed runs | MET | MET | `exp*_raw.csv`, `environment.json`; untimed verification passes in SUMMARY |
| 7 Theory separated from measured runtime | MET | MET | SUMMARY interpretation and conclusion paragraphs; report section 8 (Exp 1 says measurements do not confirm linearity) |
| 8 Three challenges | MET | MET | Generator screen, Explorer Compare tab, Dashboard live top-k |
| 9.1 Test coverage list | MET | MET | report section 7 table; files above |
| 9.2 Report structure, sections 1-10 | MET | MET | `report/report_main.md` |
| 9.2 Pseudocode (numbered steps), data structures, correctness, complexity per algorithm | PARTIAL (REPORT) | PARTIAL | report has one-line "core idea" per algorithm: REPORT text below |
| 9.2 DP and pruning documentation in report, normalisation rationale | PARTIAL (REPORT) | PARTIAL | REPORT text below |
| 9.2 Integration section accurate | PARTIAL (REPORT) | PARTIAL | Greedy and BFS/DFS rows outdated: corrections below |
| 9.3 Deliverables: executable, README, PDF, visualisation, results, ZIP | MET | MET | `README.md`, `report/report.pdf`, `scripts/package.py`; ZIP filename uses placeholders (human task) |
| Demo and viva | NOT VERIFIABLE | - | human |

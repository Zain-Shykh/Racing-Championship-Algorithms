"""Phase 6 UI: Algorithm Lab, championship flow, dashboard, track generator, multi-objective view."""
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402
import pytest  # noqa: E402

from smart_racing import config  # noqa: E402
from smart_racing.algorithms import astar, backtracking, bfs, dfs, dijkstra, heap, knapsack, mst, sorting  # noqa: E402
from smart_racing.engine import events  # noqa: E402
from smart_racing.tracks.loader import load_builtin, load_circuit  # noqa: E402
from smart_racing.ui import lab_registry as L  # noqa: E402
from smart_racing.ui.app import App  # noqa: E402
from smart_racing.ui.screens import generator as generator_screen  # noqa: E402
from smart_racing.ui.screenshots import click_tab, click_vertex, play_championship_race, run_until, shoot_phase6  # noqa: E402

EXPECTED = {"BFS": bfs.bfs, "DFS": dfs.dfs, "Dijkstra": dijkstra.dijkstra, "A*": astar.astar,
            "Knapsack DP": knapsack.knapsack_dp, "Greedy": knapsack.knapsack_greedy, "Backtracking": backtracking.solve,
            "Kruskal": mst.kruskal, "Event heap": events.EventQueue, "Merge sort": sorting.merge_sort,
            "Quick sort": sorting.quick_sort, "Heap sort": sorting.heap_sort}


@pytest.fixture(scope="module")
def app():
    a = App()
    yield a
    pygame.quit()


@pytest.fixture(autouse=True)
def home(app):
    app.error = None
    app.flow = None
    app.goto("menu")
    app.pump(frames=2)
    yield
    assert app.error is None, app.error


def lab_data(name: str, circuit: str = "harbor_eight") -> dict:
    """Fresh data for a direct call (the event heap mutates its graph, so never share it)."""
    c = load_builtin(circuit)
    g, fam = c.graph, L.ALGOS[name].family
    return {"graph": dict(graph=g, src=g.start.id, dst=g.checkpoints()[5].id, preset="Balanced"),
            "knapsack": dict(items=L.items_from(L.KNAPSACK_PRESETS["Brief A/B/C (B=10)"][0]), budget=10),
            "backtrack": dict(circuit=c, k=5, gap=4), "kruskal": dict(graph=g), "heap": dict(circuit=c),
            "sort": dict(entries=L.sample_entries(12))}[fam]


# --- registry: no second implementation ---------------------------------------------------------------
def test_registry_is_the_gameplay_functions():
    assert set(L.REGISTRY) == set(EXPECTED) and len(L.REGISTRY) == 12
    for name, fn in EXPECTED.items():
        assert L.REGISTRY[name] is fn and L.ALGOS[name].fn is fn
    assert heap.MinHeap is events.MinHeap                        # the event queue's heap is the one hand-written heap


@pytest.mark.parametrize("name", list(EXPECTED))
def test_lab_counters_equal_direct_call(name):
    rec = L.record(name, lab_data(name))
    _, direct = L.run(name, lab_data(name))                      # observer=None, same function
    assert rec.counters == direct and rec.steps
    live = L.live_counters(name, rec.steps, len(rec.steps))
    assert all(rec.counters[k] == v for k, v in live.items())    # replayed counters agree with the result's own
    assert L.live_counters(name, rec.steps, 0).keys() <= rec.counters.keys()


def test_recorded_run_matches_unobserved_result():
    data = lab_data("Dijkstra")
    rec = L.record("Dijkstra", data)
    plain = dijkstra.dijkstra(data["graph"], data["src"], data["dst"], L.make_cost_fn("Balanced"))
    assert rec.result.edge_path == plain.edge_path and rec.result.cost == plain.cost
    assert L.graph_state("Dijkstra", rec.steps, len(rec.steps))["path"] == plain.edge_path


def test_knapsack_brief_example_dp_beats_greedy():
    items = L.items_from(L.KNAPSACK_PRESETS["Brief A/B/C (B=10)"][0])
    dp, greedy = L.record("Knapsack DP", dict(items=items, budget=10)), L.record("Greedy", dict(items=items, budget=10))
    assert (dp.result.total_benefit, greedy.result.total_benefit) == (48, 30)


# --- Lab screen ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(EXPECTED))
def test_lab_steps_to_end_and_back(app, name):
    app.goto("lab", algo=name)
    lab = app.screen
    total = lab.total
    assert total > 0 and lab.pos == 0
    app.click_label("Step >")
    app.click_label("Step >")
    assert lab.pos == min(2, total)
    app.click_label("Play")
    assert lab.playing
    lab.speed.index = len(lab.speed.options) - 1                  # 400 steps/s
    app.pump(seconds=60, dt=0.5)
    assert lab.pos == total and not lab.playing
    app.pump(frames=2)
    shown = lab.rec.counters
    _, direct = L.run(name, lab_data(name))
    assert shown == direct
    for _ in range(min(total, 5)):
        app.click_label("< Step")
    assert lab.pos == total - min(total, 5)
    app.click_label("Restart")
    assert lab.pos == 0 and not lab.playing
    app.press(pygame.K_RIGHT)
    assert lab.pos == 1
    app.press(pygame.K_SPACE)
    assert lab.playing
    app.press(pygame.K_SPACE)
    assert not lab.playing


def test_lab_switch_algorithm_circuit_and_options(app):
    app.goto("lab")
    lab = app.screen
    for circuit in config.BUILTIN_CIRCUITS:
        lab.circ_cycle.set_value(circuit)
        lab.set_circuit(circuit)
        for name in EXPECTED:
            lab.algo_cycle.set_value(name)
            lab.pick(name)
            lab.pos = lab.total // 2
            app.pump(frames=1)
    lab.pick("A*")
    app.click(lab.view.pt(5))                                     # click a vertex: new destination
    assert lab.dst == 5
    lab.preset_cycle.step(1)
    assert lab.rec.data["preset"] == "Speed"
    # knapsack editing re-records
    lab.pick("Knapsack DP")
    before = lab.rec.result.total_benefit
    app.click_label("B +")
    app.click_label("Add item")
    assert len(lab.items) == 4 and lab.rec.data["budget"] == lab.budget
    app.click_label("val+")
    app.click_label("Remove item")
    app.click_label("B -")
    assert len(lab.items) == 3 and lab.rec.result.total_benefit == before
    lab.kn_cycle.set_value("Track pickups (route, B=60)")
    lab.set("kn_preset", "Track pickups (route, B=60)")
    assert lab.budget == 60 and lab.items
    # sorts: three columns, standings data
    lab.pick("Quick sort")
    assert [r.name for r in lab.recs] == list(L.SORTS)
    lab.data_cycle.step(1)
    assert len(lab.recs[0].data["entries"]) == 24
    lab.data_cycle.step(1)                                        # no championship: falls back to the sample
    assert len(lab.recs[0].data["entries"]) == 12


# --- championship flow -----------------------------------------------------------------------------------------
def test_full_championship_from_menu_to_champion(app):
    app.settings.laps = 1
    app.click_label("Championship")
    assert app.screen_name == "championship" and app.screen.phase == "briefing"
    app.pump(frames=2)
    flow = app.flow
    names = []
    for i in range(3):
        assert app.screen.phase == "briefing" and app.screen.champ.race_number == i + 1
        names.append(app.screen.circuit.name)
        play_championship_race(app)
        assert app.screen_name == "championship" and app.screen.phase == "results"
        assert len(flow.champ.results) == i + 1
        app.pump(frames=2)
        if i == 0:                                                # Esc asks before leaving a championship in progress
            app.press(pygame.K_ESCAPE)
            assert app.screen.confirm
            app.press(pygame.K_ESCAPE)
            assert app.screen.confirm is None and app.screen_name == "championship"
            app.press(pygame.K_ESCAPE)
            app.click_label("Leave")
            assert app.screen_name == "menu"
            app.click_label("Championship")                       # resumes where it was
            assert app.screen.phase == "results" and app.flow is flow
        app.click_label("Champion!" if i == 2 else "Next race")
    assert names == ["Harbor Eight", "Grand Ring", "Serpent Pass"]
    assert app.screen.phase == "champion" and flow.champ.finished
    app.pump(frames=2)
    champion = flow.champ.champion
    assert champion is flow.champ.standings().items[0]
    app.click_label("Dashboard")
    assert app.screen_name == "dashboard" and app.screen.mode.value == "Current championship"
    app.click_label("Back")
    app.click_label("Championship")                               # a finished championship starts a new one
    assert app.screen.phase == "briefing" and app.flow is not flow
    app.settings.laps = config.LAPS_PER_RACE


def test_championship_restart_keeps_the_flow_and_menu_back_is_safe(app):
    app.settings.laps = 1
    app.goto("championship", new=True)
    app.click_label("Back")                                       # nothing recorded yet: no confirmation
    assert app.screen_name == "menu"
    app.goto("championship")
    app.click_label("Start race")
    rs = app.screen
    app.press(pygame.K_ESCAPE)                                    # pause, then restart: still a championship race
    app.click_label("Restart race")
    assert app.screen is not rs and app.screen.on_finish == app.flow.finish
    app.settings.laps = config.LAPS_PER_RACE


# --- dashboard -----------------------------------------------------------------------------------------------------
def test_dashboard_standalone_and_sorts_agree(app):
    app.goto("dashboard")
    d = app.screen
    assert d.mode.value.startswith("Sample") and d.champ is not None and d.champ.finished
    app.pump(frames=2)
    ids = {m: [e.racer_id for e in r.items] for m, r in d.ranks.items()}
    assert ids["merge"] == ids["quick"] == ids["heap"] and d.same
    for m in ("merge", "quick", "heap"):                          # counts equal a direct call of the gameplay sort
        direct = {"merge": sorting.merge_sort, "quick": sorting.quick_sort, "heap": sorting.heap_sort}[m](d.entries)
        assert d.ranks[m].comparisons == direct.comparisons
    for _ in range(3):
        d.sort.step(1)
        app.pump(frames=1)
    assert d.ranking is d.ranks[d.sort.value].items
    d.race_cycle.step(1)
    app.pump(frames=1)
    d.mode.step(1)                                                # large sample field: top-k beats a full sort
    assert d.champ is None and len(d.entries) == 200
    d.kcycle.set_value(3)
    d.kcycle.step(0)
    d.refresh()
    assert d.top.comparisons < d.ranks["merge"].comparisons / 4 and d.same
    ids = [e.racer_id for e in d.top.items]
    assert ids == [e.racer_id for e in d.ranks["merge"].items[:3]]
    for _ in range(len(d.kcycle.options)):
        d.kcycle.step(1)
        assert [e.racer_id for e in d.top.items] == [e.racer_id for e in d.ranks["merge"].items[:d.kcycle.value]]
        app.pump(frames=1)


# --- generator -----------------------------------------------------------------------------------------------------
def test_generator_demo_seed_shows_rejection_and_actions(app, tmp_path, monkeypatch):
    monkeypatch.setattr(generator_screen, "SAVE_DIR", tmp_path / "saved")
    app.goto("generator")
    g = app.screen
    assert g.seed == 29 and g.report.success and [r.attempt for r in g.report.rejected] == [1]
    assert any("fuel" in s for s, _ in g.text.rows) and g.verdict.ok
    names = [s.name for s in g.report.stages]
    for i, name in enumerate(names):                              # every pipeline stage opens
        g.tabs.index = i
        g.show(i)
        app.pump(frames=1)
        assert g.report.stages[g.stage].name == name
    app.press(pygame.K_LEFT)
    app.click_label("+1")
    app.click_label("Generate")
    assert g.seed == 30
    for ch in "29":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=ord(ch), mod=0, unicode=ch, scancode=0))
    app.step(0.0)
    assert g.typed == "29"
    app.press(pygame.K_RETURN)
    assert g.seed == 29 and g.circuit is not None
    app.click_label("Save circuit")
    saved = tmp_path / "saved" / "generated_seed29.json"
    assert saved.exists() and load_circuit(saved).graph.num_edges == g.circuit.graph.num_edges
    app.click_label("Open in Explorer")
    ex = app.screen
    assert app.screen_name == "explorer" and ex.name == "Generated #29" and ex.circuit_cycle.value == "Generated #29"
    click_tab(app, "Compare")
    ex.mode.step(1)
    app.click_label("Start race")
    assert app.screen_name == "race" and app.screen.engine.circuit.name == "Generated #29"
    rs = app.screen
    rs.set_speed(4)
    assert run_until(app, lambda: rs.results is not None, 0.25)
    app.click_label("Race again")                                 # restarts the same generated track, untouched
    assert app.screen is not rs and app.screen.engine.clock < 1
    app.goto("generator")
    app.screen.bump(1, True)                                      # a failure-free seed with no rejection
    app.pump(frames=2)


# --- multi-objective -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", [1, 2])
def test_explorer_multi_objective_view(app, mode):
    app.goto("explorer", circuit="harbor_eight")
    ex = app.screen
    click_vertex(app, 0)
    click_vertex(app, 12)
    click_tab(app, "Compare")
    ex.mode.step(mode)
    r = ex.res["Compare"]
    assert [row[0] for row in r.table[1]] == list(config.COST_PRESETS)
    assert r.table2 is not None and [row[0] for row in r.table2[1]] == list(config.COST_PRESETS)
    assert r.table2[1][1][1:] == ["0.5", "3", "0.25", "0.5", "0.5"]       # the Speed row of the weights table
    assert len(r.overlays) == 4
    assert any("Pareto" in s for s, _ in ex.text.rows) and any("Weights are arbitrary" in s for s, _ in ex.text.rows)
    app.pump(frames=2)


# --- screenshots ----------------------------------------------------------------------------------------------------------
def test_phase6_screenshots(app, tmp_path):
    saved = shoot_phase6(tmp_path, app)
    assert len(saved) >= 11 and all(p.stat().st_size > 5000 for p in saved)

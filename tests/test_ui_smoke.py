"""Headless smoke tests of the pygame UI (dummy video and audio drivers)."""
import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402
import pytest  # noqa: E402

from smart_racing import config  # noqa: E402
from smart_racing.ui.app import App  # noqa: E402
from smart_racing.ui.screens import SCREENS  # noqa: E402
from smart_racing.ui.screenshots import click_edge, click_tab, click_vertex, run_until, shoot_all  # noqa: E402
from smart_racing.ui.widgets import ScrollText  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = App()
    yield a
    pygame.quit()


@pytest.fixture(autouse=True)
def home(app):
    app.error = None
    app.goto("menu")
    app.pump(frames=2)
    yield
    assert app.error is None, app.error


def test_every_screen_opens_and_escape_returns(app):
    for name in SCREENS:
        app.goto(name)
        app.pump(frames=3)
        assert app.screen_name == name
        app.press(pygame.K_ESCAPE)
        app.pump(frames=1)
        assert app.screen_name in ("menu", "race")      # a race pauses on Escape instead of leaving
        app.goto("menu")


def test_menu_buttons_reach_screens(app):
    for label, name in [("Quick Race", "quick"), ("Track Explorer", "explorer"), ("Instructions", "instructions"),
                        ("Settings", "settings"), ("Championship", "championship"), ("Algorithm Lab", "lab"),
                        ("Dashboard", "dashboard")]:
        app.click_label(label)
        assert app.screen_name == name
        app.pump(frames=2)
        app.click_label("Back" if name in ("quick", "explorer", "instructions", "settings") else "Back to menu")
        assert app.screen_name == "menu"


def test_settings_cycles_change_shared_settings(app):
    app.goto("settings")
    cycles = [w for w in app.screen.widgets if hasattr(w, "options")]
    before = (app.settings.laps, app.settings.speed, app.settings.show_ids)
    for c in cycles:
        app.click((c.box.right - 10, c.box.centery))
    assert (app.settings.laps, app.settings.speed, app.settings.show_ids) != before
    for c in cycles:                                         # restore
        app.click((c.box.x + 10, c.box.centery))
    assert (app.settings.laps, app.settings.speed, app.settings.show_ids) == before


@pytest.mark.parametrize("circuit", config.BUILTIN_CIRCUITS)
def test_explorer_every_tab_and_click_path(app, circuit):
    app.goto("explorer", circuit=circuit)
    ex = app.screen
    g = ex.g
    cps = g.checkpoints()
    click_vertex(app, g.start.id)
    click_vertex(app, cps[4].id)
    assert (ex.src, ex.dst) == (g.start.id, cps[4].id)
    app.click_label("Run BFS")
    assert any("Reachable checkpoints: 10 of 10" in s for s, _ in ex.text.rows)
    app.click_label("Run DFS")
    assert any("Cycle: found" in s for s, _ in ex.text.rows)
    app.click_label("Next alternative route")
    for tab in ("Routes", "Compare", "Resources", "Reach"):
        click_tab(app, tab)
        app.pump(frames=2)
    click_tab(app, "Routes")
    app.click_label("Run both")
    ex.scope.step(1)                                         # full lap
    assert ex.res["Routes"].table is not None
    click_tab(app, "Compare")
    ex.mode.step(1)
    assert len(ex.res["Compare"].table[1]) == 4              # four presets
    ex.mode.step(1)
    assert len(ex.res["Compare"].table[1]) >= 3              # candidate routes
    ex.preset_cycle.step(1)
    app.pump(frames=2)


def test_explorer_block_unblock_and_unreachable(app):
    app.goto("explorer", circuit="harbor_eight")
    ex = app.screen
    click_tab(app, "Routes")
    before = list(ex.res["Routes"].overlays[0].edges)
    victim = before[4]
    click_edge(app, victim)                                  # block a road on the route by clicking it
    assert ex.g.edge(victim).blocked
    assert victim not in list(ex.res["Routes"].overlays[0].edges)    # recalculated
    click_edge(app, victim)
    assert not ex.g.edge(victim).blocked
    for e, _ in ex.g.incident(ex.dst):                       # cut the destination off completely
        ex.g.block_edge(e.id)
    ex.invalidate()
    assert any("UNREACHABLE" in s for s, _ in ex.text.rows)
    click_tab(app, "Reach")
    app.click_label("Run BFS")
    assert any("UNREACHABLE" in s for s, _ in ex.text.rows)
    app.click_label("Reset roads")
    assert not any(e.blocked for e in ex.g.edges())


def test_scroll_text_wheel(app):
    st = ScrollText((0, 0, 300, 100), [f"line {i}" for i in range(50)])
    st.hover = True
    st.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-2, x=0))
    assert st.offset > 0


def test_error_banner_instead_of_crash(app):
    app.goto("settings")
    boom = lambda surf: 1 / 0  # noqa: E731
    app.screen.draw = boom
    app.pump(frames=2)
    assert app.error and "ZeroDivisionError" in app.error[0]
    app.error = None
    app.goto("menu")                                         # the window is still alive and navigable
    assert app.screen_name == "menu"
    app.goto("race", circuit="no_such_circuit")              # a failing constructor stays on the current screen
    assert app.screen_name == "menu" and app.error
    app.error = None


@pytest.mark.parametrize("circuit", config.BUILTIN_CIRCUITS)
def test_race_autopilot_to_results(app, circuit):
    app.goto("race", circuit=circuit, laps=2, autopilot=True)
    rs = app.screen
    rs.set_speed(4)
    assert run_until(app, lambda: rs.results is not None, 0.25)
    app.pump(frames=2)
    assert rs.engine.finished and len(rs.results) == 4
    assert [b.label for b in rs.modal] == ["Race again", "Main menu"]
    app.click_label("Race again")
    app.pump(frames=2)
    assert app.screen is not rs and app.screen.engine.clock < 1
    app.screen.set_speed(1)


@pytest.mark.parametrize("circuit", config.BUILTIN_CIRCUITS)
def test_race_manual_scripted_inputs(app, circuit):
    app.goto("race", circuit=circuit, laps=1, autopilot=False)
    rs = app.screen
    rs.set_speed(4)
    e, me = rs.engine, rs.me
    run_until(app, lambda: rs.countdown <= 0, 0.5)
    frames = 0
    while rs.results is None and frames < 8000:
        frames += 1
        if len(e.legal_choices(me.id)) > 1:
            app.press(pygame.K_1 + frames % 3)               # varied choices, some out of range
        if e.station_offer(me.id):
            app.press(pygame.K_r if frames % 2 else pygame.K_f)
        if frames % 40 == 0:
            app.press(pygame.K_SPACE)
        if frames == 100:
            app.press(pygame.K_TAB)
        if frames == 200:                                    # autopilot toggled both ways mid-race
            app.press(pygame.K_a)
        if frames == 300:
            app.press(pygame.K_a)
        app.step(0.25)
    assert rs.results is not None
    assert len(rs.results) == 4
    assert rs.engine.finished


def test_race_pause_hooks_and_road_closure(app):
    seen = []
    app.goto("race", circuit="harbor_eight", laps=1, autopilot=True, on_finish=seen.append,
             on_continue=lambda: seen.append("next"), continue_label="Next race")
    rs = app.screen
    e = rs.engine
    app.press(pygame.K_ESCAPE)                               # pause
    assert rs.paused
    clock = e.clock
    app.pump(frames=20, dt=0.1)
    assert e.clock == clock
    app.click_label("Resume")
    assert not rs.paused
    rs.set_speed(4)
    assert run_until(app, lambda: e.clock > 36.0, 0.1)       # the scripted closure of road 6 at 35 s
    assert e.graph.edge(6).blocked
    assert any("Road blocked" in s for _, s, _ in rs.msgs)
    assert 6 not in rs.me.route
    assert run_until(app, lambda: rs.results is not None, 0.25)
    assert seen == [e]
    assert rs.modal[0].label == "Next race"
    app.click_label("Next race")
    assert seen[-1] == "next"
    app.press(pygame.K_ESCAPE)
    assert app.screen_name == "menu"


def test_junction_click_chooses_road(app):
    app.goto("race", circuit="harbor_eight", laps=1, autopilot=False)
    rs = app.screen
    e = rs.engine
    run_until(app, lambda: rs.countdown <= 0, 0.5)
    assert run_until(app, lambda: len(e.legal_choices(0)) > 1, 0.05)
    choice = e.legal_choices(0)[-1]
    click_edge_pos = rs.view.edge_mid(e.graph.edge(choice.edge_id), 0.7)
    app.click(click_edge_pos)
    assert rs.me.chosen_edge == choice.edge_id


def test_screenshot_helper_writes_images(app, tmp_path):
    saved = shoot_all(tmp_path, app)
    assert len(saved) >= 7 and all(p.stat().st_size > 5000 for p in saved)

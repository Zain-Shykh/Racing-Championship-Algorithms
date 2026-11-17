"""End-to-end sync tests: what the GUI shows is what the backend computes, and the controls do what the screen says.

The real App is driven through synthetic pygame events at real screen coordinates (App.click/press/step). Everything
the screens draw is captured by spying the text helper, GraphView.draw and GraphView.draw_car, then compared with a
ground truth computed straight from the engine/algorithms or with a small independent reference written here.
"""
import math
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402
import pytest  # noqa: E402

from smart_racing import config  # noqa: E402
from smart_racing.engine.championship import Championship, score_race  # noqa: E402
from smart_racing.engine.race import FINISHED, REFUELLING, create_race  # noqa: E402
from smart_racing.tracks.loader import load_builtin  # noqa: E402
from smart_racing.ui import render, widgets  # noqa: E402
from smart_racing.ui.app import App  # noqa: E402
from smart_racing.ui.screens import race as race_screen  # noqa: E402
from smart_racing.ui.screens.race import clock_text  # noqa: E402
from smart_racing.ui.screenshots import click_tab, click_vertex, run_until  # noqa: E402
from smart_racing.ui.widgets import ROUTE_COLORS, wrap  # noqa: E402

ROAD_CIRCUITS = ("harbor_eight", "grand_ring")


# --- harness ---------------------------------------------------------------------------------------------------
class Spy:
    """Records every string drawn, every GraphView.draw call and every car drawn in the last frame."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.rects: list[tuple] = []
        self.views: list[dict] = []
        self.cars: list[tuple] = []

    def clear(self) -> None:
        self.texts, self.views, self.cars, self.rects = [], [], [], []


@pytest.fixture(scope="module")
def spy():
    s = Spy()
    orig_text, orig_draw, orig_car = widgets.text, render.GraphView.draw, render.GraphView.draw_car

    def text(surf, st, *a, **k):
        s.texts.append(str(st))
        rect = orig_text(surf, st, *a, **k)
        s.rects.append((str(st), rect))
        return rect

    def draw(self, surf, show_ids=False, overlays=(), rings=None, flash=None, tags=None):
        overlays = list(overlays)
        s.views.append(dict(view=self, overlays=[(list(o.edges), o.color) for o in overlays], rings=dict(rings or {}),
                            tags=dict(tags or {})))
        return orig_draw(self, surf, show_ids, overlays, rings, flash, tags)

    def car(self, surf, pos, heading, color, label="", player=False, boost=False, faded=False):
        s.cars.append((pos, color, player, boost, faded))
        return orig_car(self, surf, pos, heading, color, label, player, boost, faded)

    saved = {}
    for name, mod in list(sys.modules.items()):
        if name.startswith("smart_racing.ui") and getattr(mod, "text", None) is orig_text:
            saved[name] = mod
            mod.text = text
    render.GraphView.draw, render.GraphView.draw_car = draw, car
    yield s
    for mod in saved.values():
        mod.text = orig_text
    render.GraphView.draw, render.GraphView.draw_car = orig_draw, orig_car


@pytest.fixture(scope="module")
def app():
    a = App()
    yield a
    pygame.quit()


@pytest.fixture(autouse=True)
def home(app):
    app.error = None
    app.flow = None
    app.settings.laps, app.settings.speed = config.LAPS_PER_RACE, 1
    app.settings.autopilot, app.settings.pickup_solver, app.settings.preset = True, "dp", "Balanced"
    app.settings.opponents, app.settings.circuit, app.settings.show_ids = config.NUM_OPPONENTS, config.BUILTIN_CIRCUITS[0], True
    app.goto("menu")
    app.pump(frames=2)
    yield
    assert app.error is None, app.error


def frame(app, spy) -> list[str]:
    """Redraw the current screen (no update, no time passes) and return every string it drew."""
    spy.clear()
    app.draw()
    return list(spy.texts)


def after(texts: list[str], header: str, stop: str) -> list[str]:
    """The strings drawn between two panel titles."""
    i = texts.index(header)
    return texts[i + 1:texts.index(stop, i)]


def start_race(app, circuit, laps=1, autopilot=False, speed=1, **kw):
    app.goto("race", circuit=circuit, laps=laps, autopilot=autopilot, **kw)
    rs = app.screen
    rs.set_speed(speed)
    return rs


def skip_countdown(app, rs):
    assert run_until(app, lambda: rs.countdown <= 0, 0.5)


# --- ground truth helpers ---------------------------------------------------------------------------------------
def independent_legal(g, vertex: int, fuel: float) -> set[int]:
    """Roads the player may enter at `vertex`: open, driven in the allowed direction, affordable. Written from the rules,
    scanning every edge, not by calling graph.neighbors."""
    out = set()
    for e in g.edges():
        if e.blocked or e.effective_fuel > fuel + 1e-9:
            continue
        if e.src == vertex or (not e.directed and e.dst == vertex):
            out.add(e.id)
    return out


def decision_vertex(me):
    return me.current_vertex if me.edge_id is None else me.to_vertex


def decision_fuel(me):
    return me.fuel if me.edge_id is None else me.fuel - me.edge_fuel * (1 - me.progress)


def choice_lines(choices):
    return [f"{i + 1}: to v{c.to_vertex}  {c.time:.1f}s  {c.fuel:.1f}f" + ("  *" if c.recommended else "")
            for i, c in enumerate(choices)]


def diamonds_lit(app, rs) -> int:
    """Lit nitro diamonds read back from the pixels of the HUD."""
    x, y = race_screen.YOU.x + 12, race_screen.YOU.y + 32
    got = 0
    for i in range(config.NITRO_MAX_CHARGES):
        px = app.surface.get_at((x + 62 + i * 30, y + 88))[:3]
        got += px == (50, 140, 255)
    return got


def check_results_panel(app, spy, rs):
    """The results modal equals the engine's classification and an independent score of the race."""
    e = rs.engine
    texts = frame(app, spy)
    order = sorted(e.racers, key=lambda r: (r.status != FINISHED, r.finish_time if r.finish_time is not None else 0, r.id))
    fin = [r for r in e.racers if r.status == FINISHED]
    assert [r.id for r in e.classification()][:len(fin)] == [r.id for r in sorted(fin, key=lambda r: (r.finish_time, r.id))]
    best = min(fin, key=lambda r: (r.fastest_lap, r.id)) if fin else None
    assert len(rs.results) == len(e.racers)
    for res in rs.results:
        r = e.racer(res.racer_id)
        pos = res.finish_position
        assert e.classification()[pos - 1].id == r.id
        exp_pts = config.POINTS_TABLE[pos - 1] if r.status == FINISHED and pos <= 10 else 0
        assert res.points_awarded == exp_pts and res.bonus_points == (config.FASTEST_LAP_BONUS if r is best else 0)
        when = f"{r.finish_time:.2f} s" if r.finish_time is not None else ("DNF" if r.status == "dnf" else "time limit")
        lap = f"{min(r.lap_times):.2f} s" if r.lap_times and r.status == FINISHED else "-"
        pts = f"{exp_pts}" + (f" +{res.bonus_points}" if res.bonus_points else "")
        i = texts.index(f"{pos}  {r.name}")
        assert texts[i + 1:i + 5] == [when, lap, str(r.fuel_stops), pts], (texts[i:i + 5], when, lap, pts)
    assert f"{e.classification()[0].name} wins" in texts
    del order


# --- scenario 1: manual driving --------------------------------------------------------------------------------------
def check_prompt(app, spy, rs, choices):
    e, me, g = rs.engine, rs.me, rs.engine.graph
    texts = frame(app, spy)
    here = decision_vertex(me)
    assert {c.edge_id for c in choices} == independent_legal(g, here, decision_fuel(me)), choices
    i = texts.index("Controls")
    for line in choice_lines(choices)[:3]:
        assert line in texts[i:], (line, texts[i:])
    for c in choices:                                           # badge numbers: time and fuel equal the road's own values
        edge = g.edge(c.edge_id)
        assert (c.time, c.fuel, c.distance, c.to_vertex) == (edge.effective_time, edge.effective_fuel, edge.distance,
                                                             edge.other(here))
    if not e.station_offer(me.id):                              # at a station the buy block takes the heading's place
        assert f"Choose the road from v{here}" in "".join(texts[i:])
    ids = [c.edge_id for c in choices]
    assert [c.edge_id for c in choices if c.recommended] == ([me.route[0]] if me.route and me.route[0] in ids else [])


def pick_road(app, spy, rs, choices, idx, by_key, stats=None):
    """Choose option `idx` by key or by clicking the road, after probing the two rejection paths."""
    e, me, g = rs.engine, rs.me, rs.engine.graph
    check_prompt(app, spy, rs, choices)
    pre = me.chosen_edge
    app.press(pygame.K_9)                                       # no such option: refused and the screen says so
    assert me.chosen_edge == pre and "No option 9 here." in frame(app, spy)
    here, legal = decision_vertex(me), {c.edge_id for c in choices}
    bad = [x for x in g.edges() if x.id not in legal and (x.src == here or x.dst == here)]
    if bad:                                                     # clicking a road that is not highlighted does nothing
        app.click(rs.view.edge_mid(bad[0], 0.5))
        assert me.chosen_edge == pre
    app.click((rs.view.rect.x + 4, rs.view.rect.bottom - 4))   # nor does empty space
    assert me.chosen_edge == pre
    want = choices[idx].edge_id
    if by_key:
        app.press(pygame.K_1 + idx)
    else:
        app.click(rs.view.edge_mid(g.edge(want), 0.5))
    assert me.chosen_edge == want
    before, said = len(me.driven), False
    for _ in range(400):
        if len(me.driven) > before:
            break
        app.step(0.25)
        said = said or bool(rs.hint and "no longer available" in rs.hint[0] and rs.hint[0] in frame(app, spy))
    assert len(me.driven) == before + 1 and me.edge_id == me.driven[-1]
    if me.driven[-1] != want:                                   # a track event closed the road first: the screen says so
        assert g.edge(want).blocked and said
        if stats is not None:
            stats["dropped"] += 1
    return want


def buy_at_station(app, spy, rs, mode):
    """Buy fuel at the station the player stands on, with R, F, arrows+Enter or the buttons; check every number."""
    e, me, g = rs.engine, rs.me, rs.engine.graph
    offer = e.station_offer(me.id)
    texts = frame(app, spy)
    assert offer[0] == max(0, min(40, math.floor(100 - me.fuel)))
    assert g.vertex(me.current_vertex).type == "FuelStation" and g.vertex(me.current_vertex).active
    assert f"Station: max {offer[0]}, recommended {offer[1]}" in texts and f"{rs.buy_amount} units" in texts
    assert all(b.visible for b in rs.buy_buttons)
    label = next(r for t, r in spy.rects if t == f"{rs.buy_amount} units")
    assert not any(label.colliderect(b.rect) for b in rs.buy_buttons), (label, [b.rect for b in rs.buy_buttons])
    fuel0, stops0, t0 = me.fuel, me.fuel_stops, e.clock
    if offer[0] < 1:                                            # a full tank: nothing to buy, and the screen says so
        app.press(pygame.K_r)
        assert "Cannot buy fuel here." in frame(app, spy) and me.fuel == fuel0 and me.fuel_stops == stops0
        return 0
    if mode == "R":
        app.press(pygame.K_r)
        if offer[1] < 1:                                        # "recommended 0" means no purchase: R must not buy
            assert "Nothing recommended here" in frame(app, spy)[-60:] or any("Nothing recommended" in t for t in frame(app, spy))
            assert me.fuel == fuel0 and me.fuel_stops == stops0 and me.status != REFUELLING
            return 0
        want = offer[1]
    elif mode == "F":
        want = offer[0]; app.press(pygame.K_f)
    elif mode == "keys":
        start = rs.buy_amount
        for k in (pygame.K_UP, pygame.K_UP, pygame.K_DOWN, pygame.K_MINUS):
            app.press(k)
        want = start
        for d in (5, 5, -5, -5):
            want = max(1, min(offer[0], want + d))
        assert rs.buy_amount == want and f"{want} units" in frame(app, spy)
        app.press(pygame.K_RETURN)
    else:
        for label in ("+5", "-5", "+5"):
            app.click_label(label)
        want = rs.buy_amount
        assert f"{want} units" in frame(app, spy)
        app.click_label("Buy")
    assert me.fuel == min(100.0, fuel0 + want) and me.fuel_stops == stops0 + 1
    assert me.status == REFUELLING and me.stop_left == config.REFUEL_STOP_TIME
    texts = frame(app, spy)
    assert f"Refuelling ({config.REFUEL_STOP_TIME:.1f} s)" in texts and f"Fuel {me.fuel:.0f} / 100" in texts
    assert not any(b.visible for b in rs.buy_buttons) and e.station_offer(me.id) is None
    for _ in range(100):
        if me.status != REFUELLING:
            break
        app.step(config.SIM_DT)
    assert abs((e.clock - t0) - config.REFUEL_STOP_TIME) <= 0.06
    assert any(x.kind == "refuel" and f"bought {min(want, 100 - fuel0):g} " in x.text for x in e.log)
    return want


def fire_nitro(app, spy, rs):
    """Space on a road: one charge less, boost indicator, speed 1.5x and fuel use 2x exactly as the engine rules say."""
    e, me, g = rs.engine, rs.me, rs.engine.graph
    c0, used0, fuel0, prog0, ticks0, edge = me.nitro_charges, me.nitro_used, me.fuel, me.progress, e.ticks, g.edge(me.edge_id)
    assert diamonds_lit(app, rs) == c0
    app.press(pygame.K_SPACE)
    assert (me.nitro_charges, me.nitro_used, me.nitro_active) == (c0 - 1, used0 + 1, True)
    texts = frame(app, spy)
    assert any(t.startswith("BOOST ") for t in texts) and diamonds_lit(app, rs) == c0 - 1
    assert [c[3] for c in spy.cars if c[2]] == [True]           # the player's car is drawn with the boost flame
    app.press(pygame.K_SPACE)                                   # a second Space while boosting is refused
    assert me.nitro_charges == c0 - 1 and "No nitro charge, or a boost is already running." in frame(app, spy)
    app.step(config.SIM_DT)
    n = e.ticks - ticks0
    if me.edge_id == edge.id and n:
        assert me.progress - prog0 == pytest.approx(n * config.SIM_DT * config.NITRO_SPEED_MULT / edge.effective_time)
        assert fuel0 - me.fuel == pytest.approx(me.edge_fuel * (me.progress - prog0) * config.NITRO_FUEL_MULT)
    t0 = e.clock
    while me.nitro_active:
        app.step(config.SIM_DT)
    if not any(x.kind == "nitro" and "cut out" in x.text for x in e.log[-3:]):
        assert e.clock - (t0 - n * config.SIM_DT) == pytest.approx(config.NITRO_DURATION, abs=0.1)
    assert not any(t.startswith("BOOST ") for t in frame(app, spy))


@pytest.mark.parametrize("circuit", ROAD_CIRCUITS)
def test_manual_race_end_to_end(app, spy, circuit):
    rs = start_race(app, circuit, laps=1, autopilot=False)
    e, me = rs.engine, rs.me
    for k in (pygame.K_1, pygame.K_r, pygame.K_UP, pygame.K_RETURN, pygame.K_9):     # countdown: keys are harmless
        app.press(k)
    assert e.clock == 0 and rs.countdown > 0 and not me.driven
    skip_countdown(app, rs)
    stats = dict(key=0, click=0, nitro=0, buys=0, dropped=0)
    n, last_nitro, seen = 0, -99.0, set()
    for _ in range(9000):
        if rs.results is not None:
            break
        choices = e.legal_choices(me.id)
        if e.station_offer(me.id) and me.status != REFUELLING and (me.current_vertex, me.fuel_stops) not in seen:
            seen.add((me.current_vertex, me.fuel_stops))
            stats["buys"] += bool(buy_at_station(app, spy, rs, ("R", "F", "keys", "buttons")[stats["buys"] % 4]))
        elif len(choices) > 1 and me.chosen_edge is None:
            pick_road(app, spy, rs, choices, n % len(choices), n % 2 == 0, stats)
            stats["key" if n % 2 == 0 else "click"] += 1
            n += 1
        elif me.edge_id is not None and me.nitro_charges and not me.nitro_active and e.clock - last_nitro > 25 and me.progress < 0.3:
            fire_nitro(app, spy, rs)
            stats["nitro"] += 1
            last_nitro = e.clock
        else:
            app.step(0.25)
    assert rs.results is not None and stats["key"] and stats["click"] and stats["nitro"], stats
    check_results_panel(app, spy, rs)


def drive_to(app, spy, rs, vertex):
    """Drive the player to `vertex` with the keyboard, following an independently planned route."""
    from smart_racing.engine.routing import plan_through
    e, me, g = rs.engine, rs.me, rs.engine.graph
    for _ in range(600):
        if me.edge_id is None and me.current_vertex == vertex:
            return
        choices = e.legal_choices(me.id)
        if len(choices) > 1 and me.chosen_edge is None and decision_vertex(me) != vertex:
            plan = plan_through(g, decision_vertex(me), [vertex], "Balanced", "dijkstra")
            pick_road(app, spy, rs, choices, [c.edge_id for c in choices].index(plan.edges[0]), True)
        else:
            app.step(0.25)
    raise AssertionError("never reached the vertex")


@pytest.mark.parametrize("circuit", ROAD_CIRCUITS)
def test_manual_station_purchase_all_controls(app, spy, circuit):
    from smart_racing.engine.routing import plan_through
    rs = start_race(app, circuit, laps=1, autopilot=False)
    e, me, g = rs.engine, rs.me, rs.engine.graph
    skip_countdown(app, rs)
    station = g.vertices_of_type("FuelStation")[0].id
    drive_to(app, spy, rs, station)
    assert me.current_vertex == station and me.edge_id is None
    for mode in ("R", "F", "keys", "buttons"):
        me.fuel = 8.0 if mode == "R" else 30.0                  # set-up: a low tank so every purchase is meaningful
        if me.status != REFUELLING:
            me.station_done = False
        assert e.station_offer(me.id) is not None
        buy_at_station(app, spy, rs, mode)
    me.fuel = 95.5                                              # "recommended 0": R buys nothing, "max 4": F still can
    me.station_done = False
    offer = e.station_offer(me.id)
    assert offer and offer[0] == 4 and offer[1] == 0
    app.press(pygame.K_r)
    assert me.fuel == 95.5 and me.status != REFUELLING and "Nothing recommended here" in " ".join(frame(app, spy))
    me.fuel = 99.5                                              # under one unit of room: "max 0", every buy is refused
    app.press(pygame.K_f)
    assert me.fuel == 99.5 and me.status != REFUELLING and "Cannot buy fuel here." in frame(app, spy)
    me.fuel = 100.0                                             # a full tank: the buy is refused, the screen says so
    app.press(pygame.K_f)
    assert "Cannot buy fuel here." in frame(app, spy) and me.fuel == 100.0


def test_pause_speed_and_nitro_refusals(app, spy):
    rs = start_race(app, "harbor_eight", laps=1, autopilot=False)
    e, me = rs.engine, rs.me
    skip_countdown(app, rs)
    for _ in range(40):                                         # get onto a road
        if me.edge_id is not None:
            break
        app.step(0.25)
    assert me.edge_id is not None and rs.speed == 1
    app.press(pygame.K_TAB)                                     # Tab: 1x -> 2x, the engine runs twice as fast
    assert rs.speed == 2 and app.settings.speed == 2
    t0 = e.ticks
    app.step(0.2)
    assert e.ticks - t0 == 8
    app.click_label("4x")
    t0 = e.ticks
    app.step(0.1)
    assert rs.speed == 4 and e.ticks - t0 == 8
    app.click_label("1x")
    t0 = e.ticks
    app.step(0.2)
    assert rs.speed == 1 and e.ticks - t0 == 4
    app.press(pygame.K_p)                                       # pause freezes the engine clock completely
    assert rs.paused and "Resume" in frame(app, spy)
    clock, charges = e.clock, me.nitro_charges
    app.press(pygame.K_SPACE)                                   # nothing fires while paused
    app.press(pygame.K_1)
    app.pump(frames=30, dt=0.5)
    assert e.clock == clock and me.nitro_charges == charges and not me.nitro_active
    app.click_label("Resume")
    assert not rs.paused
    app.step(0.2)
    assert e.clock > clock
    while me.nitro_charges:                                     # spend every charge; then Space is refused with a message
        app.press(pygame.K_SPACE)
        while me.nitro_active:
            app.step(0.25)
    app.press(pygame.K_SPACE)
    assert me.nitro_charges == 0 and "No nitro charge, or a boost is already running." in frame(app, spy)
    assert diamonds_lit(app, rs) == 0


def test_illegal_roads_are_not_offered(app, spy):
    """One-way against its direction, a blocked road and an unaffordable road never appear as options."""
    rs = start_race(app, "harbor_eight", laps=1, autopilot=False)
    e, me, g = rs.engine, rs.me, rs.engine.graph
    skip_countdown(app, rs)
    assert run_until(app, lambda: len(e.legal_choices(me.id)) > 1, 0.05)
    here = decision_vertex(me)
    legal = e.legal_choices(me.id)
    g.block_edge(legal[0].edge_id, "test-closure")              # a road closes while the player is deciding
    me.fuel = decision_fuel(me) if me.edge_id is None else me.fuel
    now = e.legal_choices(me.id)
    assert legal[0].edge_id not in [c.edge_id for c in now]
    check_prompt(app, spy, rs, now)
    assert choice_lines(legal)[0] not in frame(app, spy)
    app.press(pygame.K_1 + len(now))                            # the option that vanished is refused
    assert f"No option {len(now) + 1} here." in frame(app, spy) and me.chosen_edge is None
    cheapest = min(c.fuel for c in now)                         # fuel just short of every road but the cheapest
    me.fuel = cheapest + 0.01 if me.edge_id is None else me.fuel
    if me.edge_id is None:
        left = e.legal_choices(me.id)
        assert {c.edge_id for c in left} == independent_legal(g, here, me.fuel)
        assert all(c.fuel <= me.fuel for c in left)
    wrong_way = [x for x in g.edges() if x.directed and x.dst == here]
    for x in wrong_way:
        assert x.id not in [c.edge_id for c in e.legal_choices(me.id)]
    # one-way roads from the real circuits: never offered backwards at their head vertex
    for name in config.BUILTIN_CIRCUITS:
        eng = create_race(name, 1)
        for x in eng.graph.edges():
            if x.directed:
                assert x.id not in independent_legal(eng.graph, x.dst, 100.0)
                assert x.id in independent_legal(eng.graph, x.src, 100.0)


# --- scenario 2: rendered state vs engine state -------------------------------------------------------------------------
def mandatory_sequence(g, next_checkpoint: int, laps_left: int) -> list[int]:
    cps = [v.id for v in sorted(g.checkpoints(), key=lambda v: v.checkpoint_order)]
    seq = cps[next_checkpoint - 1:] + [g.finish.id]
    return seq + (cps + [g.finish.id]) * (laps_left - 1)


def walk_vertices(g, start: int, edges) -> list[int]:
    out = [start]
    for eid in edges:
        out.append(g.edge(eid).other(out[-1]))
    return out


def is_subsequence(needle, hay) -> bool:
    it = iter(hay)
    return all(any(x == y for y in it) for x in needle)


def expected_effects(circuit_events, t: float) -> dict[str, set[int]]:
    """Which roads are blocked / oiled / speed-limited at time t, computed from the circuit's event script alone."""
    out = {"block": set(), "oil": set(), "speed": set()}
    for ev in circuit_events:
        if ev["time"] > t + 1e-9:
            continue
        kind, target = ev["type"], ev["target"]
        if kind in ("road_block", "shortcut_close"):
            out["block"].add(target)
        elif kind in ("road_clear", "shortcut_open"):
            out["block"].discard(target)
        elif kind == "oil_spill" and t < ev["time"] + config.EVENT_DURATION[kind]:
            out["oil"].add(target)
        elif kind == "speed_restriction" and t < ev["time"] + config.EVENT_DURATION[kind]:
            out["speed"].add(target)
    return out


def check_race_frame(app, spy, rs):
    e, me, g, view = rs.engine, rs.me, rs.engine.graph, rs.view
    texts = frame(app, spy)
    n = len(e.racers)
    order = e.running_order()
    # HUD numbers
    assert clock_text(e.clock) in texts and f"Lap {min(me.lap + 1, e.laps)}/{e.laps}" in texts
    assert f"Fuel {me.fuel:.0f} / 100" in texts
    assert f"P{[r.id for r in order].index(me.id) + 1}/{n}" in texts
    cps = [v for v in sorted(g.checkpoints(), key=lambda v: v.checkpoint_order)]
    target = cps[me.next_checkpoint - 1].id if me.next_checkpoint <= len(cps) else g.finish.id
    nxt = f"Next: checkpoint {me.next_checkpoint}" if me.next_checkpoint <= len(cps) else "Next: Finish"
    if me.active:
        assert f"{nxt} (v{target})" in texts
    live = rs.results is None                                  # the results modal dims the pixels behind it
    assert not live or diamonds_lit(app, rs) == me.nitro_charges
    assert any(t.startswith("BOOST ") for t in texts) == me.nitro_active
    # running order panel = engine.running_order() (the panel draws the heap top-k, the engine's merge-sorted order)
    rows = after(texts, "Running order", "Controls")
    assert rows[1::3] == [r.name for r in order] and rows[0::3] == [str(i + 1) for i in range(n)]
    for r, info in zip(order, rows[2::3]):
        want = (f"FIN {r.finish_time:.1f}s" if r.status == FINISHED else "DNF" if r.status == "dnf"
                else f"L{min(r.lap + 1, e.laps)} CP{r.next_checkpoint - 1}")
        assert info == want, (r.name, info, want)
    # cars are drawn where the engine says they are, mapped through the same GraphView
    drawn = spy.cars
    assert len(drawn) == n
    for (pos, color, player, boost, faded), r in zip(drawn, reversed(e.racers)):
        x, y = view.to_screen(*e.xy(r.id))
        if r.edge_id is None:
            x, y = x + (r.id % 3 - 1) * 6, y + (r.id // 3 - 1) * 6
        gone = r.status in (FINISHED, "dnf")
        assert pos == pytest.approx((x, y)) and faded == gone and player == (r.is_human and not gone) and boost == r.nitro_active
    # the highlighted player route is racer.edge_id + racer.route; the ringed vertex is the next mandatory vertex
    first = spy.views[0]
    if me.active:
        assert first["overlays"][0] == (([me.edge_id] if me.edge_id is not None else []) + list(me.route), ROUTE_COLORS[0])
        assert target in first["rings"]
        start = me.to_vertex if me.edge_id is not None else me.current_vertex
        walk = walk_vertices(g, start, me.route)
        assert all(not g.edge(x).blocked for x in me.route), "route uses a blocked road"
        # mandatory vertices still ahead (the one being driven to counts) appear in order
        ahead = mandatory_sequence(g, me.next_checkpoint, e.laps - me.lap)
        if me.edge_id is not None and walk[0] == ahead[0]:
            ahead = ahead[1:]
        elif me.edge_id is not None:
            pass
        assert is_subsequence(ahead[:len(ahead)], ([start] if start == target else []) + walk) or not me.route
    # event feed lines are the engine's applied events with their times
    shown = [(t, s) for t, s, _ in rs.msgs]
    for entry in e.feed:
        assert (entry.time, entry.text) in shown
    if rs.msgs:
        t, s, _ = rs.msgs[-1]
        assert wrap(f"{t:5.1f}s {s}", 20, race_screen.COL_W - 24)[0] in texts
    # roads: blocked / oil / speed limit drawn exactly where the graph (and the event script) say
    want = expected_effects(rs.engine.circuit.events, e.clock)
    flashing = set(rs.flash)
    for edge in g.edges():
        kinds = set(edge.effects.values())
        assert (edge.id in want["block"]) == edge.blocked, (edge.id, e.clock)
        assert (edge.id in want["oil"]) == ("oil" in kinds) and (edge.id in want["speed"]) == ("speed" in kinds)
        mid = view.edge_mid(edge)
        if not live or any(math.dist(mid, c[0]) < 16 for c in drawn):
            continue
        px = tuple(app.surface.get_at((int(mid[0]), int(mid[1])))[:3])
        if edge.blocked:
            assert px == widgets.BAD, (edge.id, px)
        elif "oil" in kinds or "speed" in kinds:
            a, b = view.pt(edge.src), view.pt(edge.dst)
            L = math.dist(a, b)
            off = render.road_width(edge) / 2 + 2.5
            m3 = view.edge_mid(edge, 0.3)                       # off the "!" disc at the middle of the road
            p = (m3[0] - (b[1] - a[1]) / L * off, m3[1] + (b[0] - a[0]) / L * off)
            halo = render.HALO["oil" if "oil" in kinds else "speed"]
            q = [tuple(app.surface.get_at((int(p[0] + dx), int(p[1] + dy)))[:3]) for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1))]
            assert halo in q or edge.id in flashing, (edge.id, q, halo)
        else:
            assert px != widgets.BAD


@pytest.mark.parametrize("circuit", ROAD_CIRCUITS + ("serpent_pass",))
def test_race_frames_match_engine_and_events(app, spy, circuit):
    rs = start_race(app, circuit, laps=2, autopilot=True, speed=4)
    e, me, g = rs.engine, rs.me, rs.engine.graph
    skip_countdown(app, rs)
    script = e.circuit.events
    sampled, closures, nfeed = 0, 0, 0
    while rs.results is None:
        before = (list(me.route), me.edge_id)
        near = any(0 <= ev["time"] - e.clock < 1.5 for ev in script)
        if near:
            rs.set_speed(1)
            app.step(config.SIM_DT)
        else:
            rs.set_speed(4)
            app.step(0.25)
        if len(e.feed) > nfeed:
            new = e.feed[nfeed:]
            nfeed = len(e.feed)
            check_race_frame(app, spy, rs)
            sampled += 1
            if any(x.text.startswith(("Road blocked", "Shortcut closed")) for x in new):
                closed = [x for x in g.edges() if x.blocked]
                if any(x.id in before[0] for x in closed):    # the closure cut the player's route
                    assert me.route != before[0] and all(not x.blocked for x in map(g.edge, me.route))
                    assert rs.banner and "recalculated" in rs.banner[0] and rs.banner[0] in frame(app, spy)
                    closures += 1
        elif int(e.clock) % 20 == 0 and not near and e.ticks % 20 == 0:
            check_race_frame(app, spy, rs)
            sampled += 1
    check_race_frame(app, spy, rs)
    assert sampled >= 10 and (closures or circuit != "harbor_eight")
    assert any("blocked" in x.text or "closed" in x.text for x in e.feed)


# --- independent references (small, brute force, written from the definitions) --------------------------------------------------
def moves(g, v):
    """(edge, other vertex) pairs a car may drive from v: open roads, one-way roads only forwards."""
    for e in g.edges():
        if e.blocked:
            continue
        if e.src == v:
            yield e, e.dst
        elif e.dst == v and not e.directed:
            yield e, e.src


def ref_bfs(g, src):
    dist, queue = {src: 0}, [src]
    for v in queue:
        for _, w in moves(g, v):
            if w not in dist:
                dist[w] = dist[v] + 1
                queue.append(w)
    return dist


def ref_edge_cost(e, weights):
    span = config.MAX_DIFFICULTY - config.MIN_DIFFICULTY
    parts = (e.distance / config.DIST_REF, e.effective_time / config.TIME_REF, e.effective_fuel / config.FUEL_REF,
             (e.effective_difficulty - config.MIN_DIFFICULTY) / span, e.obstacle_penalty)
    return sum(w * c for w, c in zip(weights, parts))


def ref_dijkstra(g, src, dst, cost):
    """O(V^2) Dijkstra with a plain list scan. Returns the optimal cost or None."""
    best, done = {src: 0.0}, set()
    while True:
        cand = [(d, v) for v, d in best.items() if v not in done]
        if not cand:
            return best.get(dst)
        d, v = min(cand)
        if v == dst:
            return d
        done.add(v)
        for e, w in moves(g, v):
            nd = d + cost(e)
            if nd < best.get(w, math.inf) - 1e-12:
                best[w] = nd


def path_cost(g, edges, cost):
    return sum(cost(g.edge(x)) for x in edges)


def assert_valid_walk(g, start, edges):
    """edges form a drivable walk from start (open roads, forward on one-way roads); returns the vertex list."""
    v, out = start, [start]
    for x in edges:
        e = g.edge(x)
        assert not e.blocked and (e.src == v or (e.dst == v and not e.directed)), (x, v)
        v = e.other(v)
        out.append(v)
    return out


def ref_components(g):
    parent = {v: v for v in g.vertex_ids()}

    def find(a):
        while parent[a] != a:
            a = parent[a]
        return a
    for e in g.edges():
        if not e.blocked:
            parent[find(e.src)] = find(e.dst)
    sizes = {}
    for v in parent:
        sizes[find(v)] = sizes.get(find(v), 0) + 1
    return sorted(sizes.values())


def ref_has_cycle(g):
    """A closed trail (no road used twice) driven in the allowed directions exists. Brute-force trail search."""
    def trail(start, v, used):
        for e, w in moves(g, v):
            if e.id in used:
                continue
            if w == start or trail(start, w, used | {e.id}):
                return True
        return False
    return any(trail(v, v, frozenset()) for v in g.vertex_ids())


def ref_dead_ends(g):
    """Non-mandatory vertices reachable (without reversing) from which the finish cannot be reached without reversing."""
    start, finish = g.start.id, g.finish.id
    states, stack = {(None, start)}, [(None, start)]
    while stack:
        last, v = stack.pop()
        for e, w in moves(g, v):
            if e.id != last and (e.id, w) not in states:
                states.add((e.id, w))
                stack.append((e.id, w))
    good = {s for s in states if s[1] == finish}
    changed = True
    while changed:
        changed = False
        for last, v in states - good:
            if any(e.id != last and (e.id, w) in good for e, w in moves(g, v)):
                good.add((last, v))
                changed = True
    mandatory = {x.id for x in g.vertices() if x.type in ("Start", "Finish", "Checkpoint")}
    return sorted(v for v in {s[1] for s in states} - mandatory if not any(s[1] == v and s in good for s in states))


def ref_paths(g, src, dst, exclude, limit=config.ALT_ROUTE_LIMIT, max_len=config.ALT_PATH_MAX_EDGES):
    """Simple paths in ascending edge-id order, skipping the main route, at most `limit` of them."""
    out = []

    def go(v, seen, edges):
        if len(out) >= limit:
            return
        if v == dst:
            if edges != exclude:
                out.append(list(edges))
            return
        if len(edges) >= max_len:
            return
        for e, w in sorted(moves(g, v), key=lambda p: p[0].id):
            if w not in seen:
                go(w, seen | {w}, edges + [e.id])
    go(src, {src}, [])
    return out


def sums(g, edges):
    es = [g.edge(x) for x in edges]
    return sum(e.distance for e in es), sum(e.effective_time for e in es), sum(e.effective_fuel for e in es)


def plain(lines):
    return [s if isinstance(s, str) else s[0] for s in lines]


def explorer(app, circuit):
    app.goto("explorer", circuit=circuit)
    return app.screen


def pick(app, ex, a, b):
    click_vertex(app, a)
    click_vertex(app, b)
    assert (ex.src, ex.dst) == (a, b)


def shown_rows_drawn(app, spy, ex):
    """Everything the explorer's right-hand text box and table(s) display is really drawn."""
    texts = frame(app, spy)
    r = ex.res[ex.tab]
    for tbl in (r.table, r.table2):
        if tbl:
            header, rows, widths, _ = tbl
            for line in [header] + rows:
                for cell, w in zip(line, widths):
                    assert widgets.fit(cell, 20, w - 10 - (24 if cell is line[0] else 0)) in texts or cell in texts, cell
    vis = ex.text.rows[ex.text.offset:ex.text.offset + ex.text.visible_rows]
    assert all(s in texts for s, _ in vis)
    return texts


EXPLORER_PAIRS = {"harbor_eight": [(0, 12), (7, 22), (3, 3), (20, 5)], "grand_ring": [(0, 9), (11, 19)],
                  "serpent_pass": [(0, 14)]}


# --- scenario 3: Track Explorer -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("circuit", EXPLORER_PAIRS)
def test_explorer_reach_tab_matches_independent_bfs_dfs(app, spy, circuit):
    ex = explorer(app, circuit)
    g = ex.g
    for a, b in EXPLORER_PAIRS[circuit]:
        pick(app, ex, a, b)
        app.click_label("Run BFS")
        lines = plain(ex.res["Reach"].lines)
        shown_rows_drawn(app, spy, ex)
        dist = ref_bfs(g, a)
        cps = g.checkpoints()
        hit = sorted(c.checkpoint_order for c in cps if c.id in dist)
        assert lines[1].startswith(f"Reachable vertices: {len(dist)} of {g.num_vertices} ")
        assert lines[2] == f"Reachable checkpoints: {len(hit)} of {len(cps)}" + (f"  {hit}" if hit else "")
        assert {v for v in ex.res["Reach"].rings} == set(g.vertex_ids()) - set(dist)       # red rings = unreachable
        if b in dist:
            roads = next(s for s in lines if s.startswith("Minimum-edge path"))
            assert roads.endswith(f": {dist[b]} roads")                                        # fewest roads, vs independent BFS
            verts = [int(x) for x in next(s for s in lines if s.startswith("  vertices:")).split(":")[1].split()]
            edges = list(ex.res["Reach"].overlays[0].edges)
            assert assert_valid_walk(g, a, edges) == verts and len(edges) == dist[b] and verts[-1] == b
            d, t, f = sums(g, edges)
            assert f"  distance {d:.0f}, time {t:.1f} s, fuel {f:.1f}" in lines
        else:
            assert any(s.startswith("UNREACHABLE") for s in lines) and not ex.res["Reach"].overlays
        # DFS from the start: traversal covers exactly the reachable set; cycle, components, dead ends
        app.click_label("Run DFS")
        lines = plain(ex.res["Reach"].lines)
        shown_rows_drawn(app, spy, ex)
        order = [int(x) for x in lines[2].split()]
        assert order[0] == a and sorted(order) == sorted(dist) and f"({len(dist)} vertices," in lines[1]
        cyc = next(s for s in lines if s.startswith("Cycle:"))
        assert cyc.startswith("Cycle: found") == ref_has_cycle(g)
        comps = next(s for s in lines if s.startswith("Connected components:"))
        sizes = ref_components(g)
        assert comps.startswith(f"Connected components: {len(sizes)} ") and sorted(eval(comps.split("sizes ")[1][:-1])) == sizes
        de = next(s for s in lines if s.startswith("Dead ends:"))
        assert de == (f"Dead ends: {ref_dead_ends(g)}" if ref_dead_ends(g) else "Dead ends: none")
        if b in dist:                                      # main route = the optimum under the preset, alternatives = independent DFS
            weights = config.COST_PRESETS[ex.preset]
            cost = lambda e: ref_edge_cost(e, weights)  # noqa: E731
            best = ref_dijkstra(g, a, b, cost)
            main_edges = list(ex.res["Reach"].overlays[0].edges)
            assert path_cost(g, main_edges, cost) == pytest.approx(best)
            assert any(f"cost {best:.3f}" in s and s.startswith("Main route") for s in lines)
            alts = ref_paths(g, a, b, main_edges)
            assert f"Found {len(alts)};" in next(s for s in lines if s.startswith("Limits:"))
            rows = [s for s in lines if s[:1] in ">" or s[:3].strip().startswith("#")]
            rows = [s for s in lines if s.lstrip("> ").startswith("#")]
            assert len(rows) == len(alts)
            for i, (row, path) in enumerate(zip(rows, alts)):
                d, t, _ = sums(g, path)
                assert row.lstrip("> ") == (f"#{i + 1}: {len(path)} roads, distance {d:.0f}, time {t:.1f} s, "
                                            f"cost {path_cost(g, path, cost):.3f}")


def test_explorer_dfs_cycle_follows_blocked_roads(app, spy):
    """Block roads one by one by clicking them: the DFS panel's cycle/component/dead-end lines track an independent
    computation until the graph has no cycle left."""
    from smart_racing.ui.screenshots import click_edge
    ex = explorer(app, "harbor_eight")
    g = ex.g
    app.click_label("Run DFS")
    order = [e.id for e in g.edges()]
    flips = 0
    for eid in order:
        if g.edge(eid).blocked:
            continue
        had = ref_has_cycle(g)
        click_edge(app, eid)
        if not g.edge(eid).blocked:                      # the click landed on a vertex or a neighbouring road: skip it
            continue
        lines = plain(ex.res["Reach"].lines)
        assert next(s for s in lines if s.startswith("Cycle:")).startswith("Cycle: found") == ref_has_cycle(g)
        flips += had and not ref_has_cycle(g)
        assert next(s for s in lines if s.startswith("Connected components:")).startswith(
            f"Connected components: {len(ref_components(g))} ")
        de = next(s for s in lines if s.startswith("Dead ends:"))
        assert de == (f"Dead ends: {ref_dead_ends(g)}" if ref_dead_ends(g) else "Dead ends: none")
        if flips:
            break
    assert flips == 1
    app.click_label("Run BFS")
    dist = ref_bfs(g, ex.src)
    assert any(s.startswith(f"Reachable vertices: {len(dist)} of") for s in plain(ex.res["Reach"].lines))


def route_row(table, label):
    return next(r for r in table[1] if r[0] == label)


def lap_targets(g):
    return [v.id for v in sorted(g.checkpoints(), key=lambda v: v.checkpoint_order)] + [g.finish.id]


def check_route_overlay(g, source, edges, targets):
    """The drawn edges form one drivable walk from source that visits every target in order."""
    verts = assert_valid_walk(g, source, edges)
    assert is_subsequence(targets, verts[1:]), (targets, verts)
    return verts


@pytest.mark.parametrize("circuit", EXPLORER_PAIRS)
def test_explorer_routes_and_compare_tabs_match_references(app, spy, circuit):
    from smart_racing.engine.routing import compare_presets, plan_route
    ex = explorer(app, circuit)
    g = ex.g
    a, b = EXPLORER_PAIRS[circuit][0]
    pick(app, ex, a, b)
    for preset in config.COST_PRESETS:
        ex.preset_cycle.set_value(preset)
        ex.preset_cycle.step(0)
        ex._preset(preset)
        weights = config.COST_PRESETS[preset]
        cost = lambda e: ref_edge_cost(e, weights)  # noqa: E731
        click_tab(app, "Routes")
        for scope in ("Selected vertices", "Full lap"):
            ex.scope.set_value(scope)
            ex.scope.step(0)
            ex.rerun()
            r = ex.res["Routes"]
            texts = shown_rows_drawn(app, spy, ex)
            dj_edges, ast_edges = (list(o.edges) for o in r.overlays)
            src, targets = (a, [b]) if scope == "Selected vertices" else (g.start.id, lap_targets(g))
            for edges in (dj_edges, ast_edges):
                check_route_overlay(g, src, edges, targets)
            opt, legs_from = 0.0, src
            for t in targets:                                 # independent optimum: sum of per-leg optima
                opt += ref_dijkstra(g, legs_from, t, cost)
                legs_from = t
            hdr, rows = r.table[0], r.table[1]
            assert hdr == ["", "Dijkstra", "A*"]
            for col, edges in ((1, dj_edges), (2, ast_edges)):
                d, t, f = sums(g, edges)
                assert route_row(r.table, "Roads")[col] == str(len(edges))
                assert route_row(r.table, "Distance")[col] == f"{d:.1f}"
                assert route_row(r.table, "Est. time (s)")[col] == f"{t:.2f}"
                assert route_row(r.table, "Fuel")[col] == f"{f:.2f}"
                shown = float(route_row(r.table, "Scalar cost")[col])
                assert shown == pytest.approx(path_cost(g, edges, cost), abs=6e-5) == pytest.approx(opt, abs=6e-5)
            assert any("same optimal cost" in s for s in plain(r.lines))
        # compare tab: presets table vs direct plan_route per preset, overlays equal those paths
        click_tab(app, "Compare")
        ex.mode.set_value("Cost presets (full lap)")
        ex.mode.step(0)
        ex.rerun()
        r = ex.res["Compare"]
        shown_rows_drawn(app, spy, ex)
        direct = compare_presets(g, g.start.id)
        assert [row[0] for row in r.table[1]] == list(config.COST_PRESETS)
        for row, (name, plan), ov in zip(r.table[1], direct.items(), r.overlays):
            assert list(ov.edges) == plan.edges
            d, t, f = sums(g, plan.edges)
            w = config.COST_PRESETS[name]
            assert row[1:6] == [str(len(plan.edges)), f"{d:.0f}", f"{t:.1f}", f"{f:.1f}",
                                f"{path_cost(g, plan.edges, lambda e, w=w: ref_edge_cost(e, w)):.3f}"]
            check_route_overlay(g, g.start.id, plan.edges, lap_targets(g))
        # the same presets between the two picked vertices equal the independent optimum under each preset
        ex.mode.set_value("Cost presets (selected vertices)")
        ex.mode.step(0)
        ex.rerun()
        r = ex.res["Compare"]
        for row, ov, (name, w) in zip(r.table[1], r.overlays, config.COST_PRESETS.items()):
            c = lambda e, w=w: ref_edge_cost(e, w)  # noqa: E731
            assert float(row[5]) == pytest.approx(ref_dijkstra(g, a, b, c), abs=6e-4)
            assert float(row[5]) == pytest.approx(path_cost(g, list(ov.edges), c), abs=6e-4)
        break                                                  # one preset per circuit is enough for the heavy checks
    # candidate routes: min distance, min time and min roads are optimal by independent references
    ex.mode.set_value("Candidate routes (selected vertices)")
    ex.mode.step(0)
    ex.rerun()
    r = ex.res["Compare"]
    shown_rows_drawn(app, spy, ex)
    rows = {row[0]: row for row in r.table[1]}
    assert rows["Min distance"][2] == f"{ref_dijkstra(g, a, b, lambda e: e.distance):.0f}"
    assert rows["Min time"][3] == f"{ref_dijkstra(g, a, b, lambda e: e.effective_time):.1f}"
    assert rows["Min roads (BFS)"][1] == str(ref_bfs(g, a)[b])
    assert float(rows[f"Min cost ({ex.preset})"][5]) == pytest.approx(
        ref_dijkstra(g, a, b, lambda e: ref_edge_cost(e, config.COST_PRESETS[ex.preset])), abs=6e-4)
    del plan_route


def test_explorer_blocking_unreachable_and_reset(app, spy):
    from smart_racing.ui.screenshots import click_edge
    ex = explorer(app, "harbor_eight")
    g = ex.g
    pick(app, ex, 0, 12)
    click_tab(app, "Routes")
    weights = config.COST_PRESETS[ex.preset]
    cost = lambda e: ref_edge_cost(e, weights)  # noqa: E731
    for _ in range(3):                                         # block a road on the drawn route, three times in a row
        before = list(ex.res["Routes"].overlays[1].edges)
        for victim in before[len(before) // 2:] + before:      # a road whose closure keeps 12 reachable
            g.block_edge(victim, "probe")
            ok = 12 in ref_bfs(g, 0)
            g.unblock_edge(victim, "probe")
            if ok:
                break
        click_edge(app, victim)
        assert g.edge(victim).blocked
        for overlay in ex.res["Routes"].overlays:              # both recomputed routes avoid it
            assert victim not in overlay.edges and all(not g.edge(x).blocked for x in overlay.edges)
        assert float(route_row(ex.res["Routes"].table, "Scalar cost")[2]) == pytest.approx(ref_dijkstra(g, 0, 12, cost), abs=6e-5)
        texts = frame(app, spy)
        assert any(t.startswith("Blocked: [") for t in texts)
    click_tab(app, "Reach")
    app.click_label("Run BFS")
    assert any(s.startswith(f"Reachable vertices: {len(ref_bfs(g, 0))} of") for s in plain(ex.res["Reach"].lines))
    # cut the destination off: every tab says UNREACHABLE, none draws a route to it
    for e, _ in list(g.incident(12)):
        g.block_edge(e.id)
    ex.invalidate()
    assert 12 not in ref_bfs(g, 0)
    assert any("UNREACHABLE" in s for s in plain(ex.res["Reach"].lines))
    for tab in ("Routes", "Compare"):
        click_tab(app, tab)
        assert any("UNREACHABLE" in s for s in plain(ex.res[tab].lines)), tab
        assert "UNREACHABLE" in " ".join(t for t in frame(app, spy)) or any("UNREACHABLE" in s for s, _ in ex.text.rows)
    ex.mode.set_value("Cost presets (selected vertices)")
    ex.mode.step(0)
    ex.rerun()
    assert any("UNREACHABLE" in s for s in plain(ex.res["Compare"].lines))
    app.click_label("Reset roads")
    assert not any(e.blocked for e in ex.g.edges())
    assert (ex.src, ex.dst) == (ex.g.start.id, ex.g.finish.id)
    click_tab(app, "Routes")
    assert not any("UNREACHABLE" in s for s in plain(ex.res["Routes"].lines))


def test_explorer_resources_tab_matches_direct_calls_and_replays(app, spy):
    from smart_racing.engine.resources import pickup_plan
    from smart_racing.engine.routing import plan_route
    for circuit in ROAD_CIRCUITS:
        ex = explorer(app, circuit)
        g = ex.g
        click_tab(app, "Resources")
        for fuel in (100, 50, 25):
            ex.fuel.set_value(fuel)
            ex.fuel.step(0)
            ex.rerun()
            shown_rows_drawn(app, spy, ex)
            lines = plain(ex.res["Resources"].lines)
            plan = plan_route(g, g.start.id, 1, 1, ex.preset, "astar")
            pk = pickup_plan(g, g.start.id, plan.edges, float(fuel), config.NITRO_START_CHARGES, ex.budget.value, "dp")
            d, t, f = sums(g, plan.edges)
            assert f"Route: {len(plan.edges)} roads, distance {d:.0f}, time {t:.1f} s, fuel needed {f:.1f} " \
                   f"(start with {fuel:g}, 1 nitro charge)." in lines
            # DP benefit equals an exhaustive search over every subset of the offered pickups; greedy equals a rewritten greedy
            items = [o.item for o in pk.options]
            best = max((sum(x.benefit for x in sub) for k in range(1 << len(items))
                        for sub in [[items[i] for i in range(len(items)) if k >> i & 1]]
                        if sum(x.cost for x in sub) <= pk.budget), default=0)
            zero = [x for x in items if x.cost == 0 and x.benefit > 0]
            rest = sorted((x for x in items if x.cost and x.benefit > 0), key=lambda x: (-x.benefit / x.cost, x.id))
            left, got = pk.budget, sum(x.benefit for x in zero)
            for x in rest:
                if x.cost <= left:
                    left -= x.cost
                    got += x.benefit
            dp_line = next(s for s in lines if s.startswith("DP: pick"))
            gr_line = next(s for s in lines if s.startswith("Greedy: pick"))
            assert f"benefit {best:g}, cost {pk.dp.total_cost}/{pk.budget}" in dp_line and pk.dp.total_benefit == best
            assert f"benefit {got:g}, cost {pk.greedy.total_cost}/{pk.budget}" in gr_line and pk.greedy.total_benefit == got
            assert got <= best
            # refuel plan: replay the plan over the drawn route with a plain simulation
            adv, route = pk.refuel, list(ex.res["Resources"].overlays[0].edges)
            assert route == pk.edges
            tank, v, stop = float(fuel), g.start.id, 0
            buys = adv.result.purchases
            # independent feasibility: buying the most at every station is never worse, so simulate that
            top, v2, ok, first = float(fuel), g.start.id, True, True
            for x in route:
                e = g.edge(x)
                if top + 1e-9 < e.effective_fuel:
                    ok = False
                    break
                top -= e.effective_fuel
                v2 = e.other(v2)
                if g.vertex(v2).type == "FuelStation" and g.vertex(v2).active:
                    top = min(100.0, top + config.STATION_MAX_PURCHASE)
            assert adv.result.feasible == ok
            assert any(s.startswith("INFEASIBLE") for s in lines) == (not ok)
            if not ok:
                continue
            assert any(s.startswith("Feasible. Buy:") for s in lines)
            made = 0
            if buys[0]:
                tank, made = min(100.0, tank + buys[0]), made + 1
            for x in route:
                e = g.edge(x)
                assert tank + 1e-9 >= e.effective_fuel, "the displayed plan runs dry"
                tank -= e.effective_fuel
                v = e.other(v)
                if g.vertex(v).type == "FuelStation" and g.vertex(v).active:
                    stop += 1
                    if buys[stop]:
                        tank, made = min(100.0, tank + buys[stop]), made + 1
            assert stop == len(buys) - 1 and made == adv.result.stops_made
            line = next(s for s in lines if s.startswith("Feasible."))
            assert f"stop time {made * config.REFUEL_STOP_TIME:.1f} s; purchased {sum(buys)}; DP states {adv.result.states}." in line
            assert [v for v, _ in adv.purchases] == [s for s, a in zip(adv.stops, buys) if a]


# --- scenario 4: Algorithm Lab ----------------------------------------------------------------------------------------------------
from smart_racing.algorithms import astar, backtracking, bfs as bfs_mod, dfs as dfs_mod, dijkstra, heap as heap_mod  # noqa: E402
from smart_racing.algorithms import knapsack, mst, sorting  # noqa: E402
from smart_racing.core.cost import make_cost_fn  # noqa: E402
from smart_racing.engine.events import EventQueue  # noqa: E402
from smart_racing.ui import lab_registry as L  # noqa: E402
from smart_racing.ui.screens.lab import BLUE  # noqa: E402

LAB_ALGOS = list(L.ALGOS)


def champ_oracle(entries):
    """Python's sorted() as the oracle, under the championship order (points, wins, position sum, best lap, id)."""
    return sorted(entries, key=lambda e: (-e.total_points, -e.wins, e.sum_of_finish_positions, e.best_fastest_lap, e.racer_id))


def ref_knapsack_table(items, budget):
    table = [[0] * (budget + 1)]
    for it in items:
        prev = table[-1]
        table.append([max(prev[b], prev[b - it.cost] + it.benefit) if b >= it.cost else prev[b] for b in range(budget + 1)])
    return table


def direct_call(lab):
    """The gameplay function called straight, no observer, on the data the Lab was given. -> (result, counters)."""
    name, g = lab.name, load_builtin(lab.circuit_name).graph
    cost = make_cost_fn(lab.preset)
    if name == "BFS":
        r = bfs_mod.bfs(g, lab.src, lab.dst)
        return r, {"visited": r.visited, "edges_examined": r.edges_examined}
    if name == "DFS":
        r = dfs_mod.dfs(g, lab.src)
        return r, {"visited": r.visited, "edges_examined": r.edges_examined}
    if name in ("Dijkstra", "A*"):
        r = (dijkstra.dijkstra if name == "Dijkstra" else astar.astar)(g, lab.src, lab.dst, cost)
        return r, {"expanded": r.expanded, "relaxed": r.relaxed, "edges_examined": r.edges_examined,
                   "heap_ops": r.heap_ops, "heap_comparisons": r.heap_comparisons}
    if name in ("Knapsack DP", "Greedy"):
        r = (knapsack.knapsack_dp if name == "Knapsack DP" else knapsack.knapsack_greedy)(list(lab.items), lab.budget)
        return r, {"states": r.states, "total_cost": r.total_cost, "total_benefit": r.total_benefit}
    if name == "Backtracking":
        p = L.station_problem(load_builtin(lab.circuit_name), lab.k, lab.gap)
        r = backtracking.solve(p["variables"], p["domains"], p["consistent"], p["prune"])
        return r, {"nodes": r.nodes, "prunes": r.prunes, "backtracks": r.backtracks}
    if name == "Kruskal":
        r = mst.kruskal(g.vertex_ids(), [(e.id, e.src, e.dst, e.distance) for e in g.edges()])
        return r, {"edges_examined": r.edges_examined, "comparisons": r.comparisons, "finds": r.finds, "unions": r.unions}
    if name == "Event heap":
        r, c = L._run_event_heap(EventQueue, load_builtin(lab.circuit_name), None)
        return r, c
    fn = {"Merge sort": sorting.merge_sort, "Quick sort": sorting.quick_sort, "Heap sort": sorting.heap_sort}[name]
    r = fn(lab.recs[0].data["entries"])
    return r, {"comparisons": r.comparisons}


def lab_state(app, spy):
    """Everything visible on the Lab screen: the strings and what the map view drew."""
    texts = frame(app, spy)
    return texts, [(v["overlays"], v["rings"], v["tags"]) for v in spy.views]


def play_to_end(app, lab):
    lab.speed.index = len(lab.speed.options) - 1
    app.click_label("Play")
    assert lab.playing
    app.pump(seconds=60, dt=0.5)
    assert lab.pos == lab.total and not lab.playing


LAB_CASES = [(n, c) for n in LAB_ALGOS for c in ROAD_CIRCUITS
             if c == "harbor_eight" or L.ALGOS[n].family not in ("knapsack", "sort")]   # knapsack and sorts ignore the circuit


@pytest.mark.parametrize("name,circuit", LAB_CASES)
def test_lab_final_state_equals_direct_call_and_step_back_is_exact(app, spy, name, circuit):
    app.goto("lab", algo=name, circuit=circuit)
    lab = app.screen
    assert lab.name == name and lab.circuit_name == circuit
    # step forward k, back k, forward k: the display returns to exactly the same state
    for _ in range(min(7, lab.total)):
        app.click_label("Step >")
    mid_pos, mid = lab.pos, lab_state(app, spy)
    for _ in range(mid_pos):
        app.click_label("< Step")
    assert lab.pos == 0 and lab_state(app, spy)[0].count("Press Play or Step to run the algorithm on this data.") == 1
    for _ in range(mid_pos):
        app.click_label("Step >")
    assert lab.pos == mid_pos and lab_state(app, spy) == mid
    play_to_end(app, lab)
    end = lab_state(app, spy)
    for _ in range(3):
        app.click_label("< Step")
    for _ in range(3):
        app.click_label("Step >")
    assert lab_state(app, spy) == end
    texts, views = end
    result, counters = direct_call(lab)
    # final counters on screen = direct call
    if lab.family == "sort":
        for rec, fn in zip(lab.recs, (sorting.merge_sort, sorting.quick_sort, sorting.heap_sort)):
            i = texts.index(rec.name + " comparisons")
            assert texts[i + 1] == str(fn(lab.recs[0].data["entries"]).comparisons)
    else:
        for key, val in counters.items():
            i = texts.index(key.replace("_", " "))
            assert texts[i + 1] == (f"{val:g}" if isinstance(val, float) else str(val)), (key, texts[i:i + 2], val)
    ov, rings, tags = views[0] if views else ([], {}, {})
    g = load_builtin(circuit).graph
    if name in ("BFS", "Dijkstra", "A*"):
        path = next(edges for edges, color in ov if color == widgets.GOOD)
        assert path == result.edge_path and result.found
        assert_valid_walk(g, lab.src, path)
        cost = make_cost_fn(lab.preset)
        if name == "BFS":
            assert len(path) == ref_bfs(g, lab.src)[lab.dst]                        # fewest roads
        else:
            assert path_cost(g, path, cost) == pytest.approx(ref_dijkstra(g, lab.src, lab.dst, cost))
            assert result.cost == pytest.approx(path_cost(g, path, cost))
    if name == "DFS":
        assert {v for v, c in rings.items() if c in (BLUE, widgets.WARN, (255, 255, 255), widgets.GOOD)} >= set(result.order)
        assert len(next(edges for edges, color in ov if color == (0, 225, 255))) == len(result.order) - 1   # DFS tree
    if name in ("Knapsack DP", "Greedy"):
        taken = {r[0] for r in [[it.name] for it in lab.items] if False}
        ids = set(result.selected)
        for it in lab.items:
            row = texts.index(it.name)
            assert texts[row + 1:row + 4] == [str(it.cost), f"{it.benefit:g}", f"{it.benefit / it.cost:.2f}" if it.cost else "free"]
            assert texts[row + 4] == ("taken" if it.id in ids else "-") or name == "Greedy"
        oracle_best = max(sum(it.benefit for k, it in enumerate(lab.items) if m >> k & 1)
                          for m in range(1 << len(lab.items))
                          if sum(it.cost for k, it in enumerate(lab.items) if m >> k & 1) <= lab.budget)
        if name == "Knapsack DP":
            assert result.total_benefit == oracle_best
            table = ref_knapsack_table(lab.items, lab.budget)
            assert result.table == table and table[-1][-1] == oracle_best
            i = texts.index("dp[i][b]: best benefit, first i items, budget b") + 1 + lab.budget + 1
            for row in range(len(lab.items) + 1):
                assert texts[i] == ("0" if row == 0 else lab.items[row - 1].name)
                assert [float(x) for x in texts[i + 1:i + 2 + lab.budget]] == [float(x) for x in table[row]], row
                i += 2 + lab.budget
        else:
            assert result.total_benefit <= oracle_best
        del taken
    if name == "Backtracking":
        route = L.station_problem(load_builtin(circuit), lab.k, lab.gap)["route"]
        assert ("SOLVED: stations placed" if result.solved else "NO SOLUTION: every combination was tried and rejected") in \
            "".join(t for t in texts) or any(t.startswith("SOLVED") or t.startswith("NO SOLUTION") for t in texts)
        if result.solved:
            assert {route[p]: f"S{var}" for var, p in result.assignment.items()} == \
                {v: t for v, t in tags.items() if t.startswith("S") and t != "S"}
            pos = sorted(result.assignment.values())                                     # the displayed placement obeys the rule
            n = len(route)
            assert all(min(abs(a - b), n - abs(a - b)) >= lab.gap for a, b in zip(pos, pos[1:]))
    if name == "Kruskal":
        accepted = next(edges for edges, color in ov if color == widgets.GOOD)
        assert accepted == [x[0] for x in result.edges]
        assert len(accepted) == g.num_vertices - result.components
        # independent check: the tree is a minimum one (weight equals Prim's on a plain scan)
        in_tree, best = {0}, 0.0
        while len(in_tree) < g.num_vertices:
            w, nxt = min((e.distance, e.dst if e.src in in_tree else e.src) for e in g.edges()
                         if (e.src in in_tree) != (e.dst in in_tree))
            in_tree.add(nxt)
            best += w
        assert result.total_weight == pytest.approx(best)
    if name == "Event heap":
        q = result
        assert counters["applied"] == len(q.applied) and counters["rejected"] == len(q.rejected)
        final = L.restore_snapshot  # noqa: F841
        eng_graph = q.graph
        shown = {e.id: dict(e.effects) for e in lab.circuit.graph.edges()}
        assert shown == {e.id: dict(e.effects) for e in eng_graph.edges()}
        assert "(empty)" in texts
    if lab.family == "sort":
        entries = lab.recs[0].data["entries"]
        want = " ".join(str(e.racer_id) for e in champ_oracle(entries)[:9]) + (" .." if len(entries) > 9 else "")
        assert texts.count("ranking: " + want) == 3, want
        for rec in lab.recs:
            assert [e.racer_id for e in rec.result.items] == [e.racer_id for e in champ_oracle(entries)]


def ref_greedy(items, budget):
    zero = [x for x in items if x.cost == 0 and x.benefit > 0]
    rest = sorted((x for x in items if x.cost and x.benefit > 0), key=lambda x: (-x.benefit / x.cost, x.id))
    left, got = budget, sum(x.benefit for x in zero)
    for x in rest:
        if x.cost <= left:
            left -= x.cost
            got += x.benefit
    return got


def ref_best(items, budget):
    return max(sum(it.benefit for k, it in enumerate(items) if m >> k & 1) for m in range(1 << len(items))
               if sum(it.cost for k, it in enumerate(items) if m >> k & 1) <= budget)


def test_lab_knapsack_presets_and_edits_show_the_optimum_and_the_greedy_gap(app, spy):
    app.goto("lab", algo="Knapsack DP")
    lab = app.screen
    seen = set()
    for _ in range(len(lab.kn_cycle.options)):
        app.click((lab.kn_cycle.box.right - 10, lab.kn_cycle.box.centery))             # next item set, by the real widget
        seen.add(lab.kn_preset)
        for algo in ("Knapsack DP", "Greedy"):
            lab.algo_cycle.set_value(algo)
            lab.pick(algo)
            play_to_end(app, lab)
            texts = frame(app, spy)
            best, greedy = ref_best(lab.items, lab.budget), ref_greedy(lab.items, lab.budget)
            mine, other = (best, greedy) if algo == "Knapsack DP" else (greedy, best)
            other_name = "Greedy" if algo == "Knapsack DP" else "Knapsack DP"
            assert f"{algo}: benefit {mine:g}   {other_name} (same data): benefit {other:g}" in texts, (algo, texts[-12:])
            if algo == "Greedy":                                         # per-item verdicts replay the ratio order
                order = sorted((x for x in lab.items if x.benefit > 0 and x.cost), key=lambda x: (-x.benefit / x.cost, x.id))
                left, verdict = lab.budget, {}
                for x in order:
                    verdict[x.id] = x.cost <= left
                    left -= x.cost if verdict[x.id] else 0
                for x in lab.items:
                    if x.id in verdict:
                        assert texts[texts.index(x.name) + 4] == ("picked" if verdict[x.id] else "rejected")
    assert len(seen) == len(lab.kn_cycle.options)
    lab.pick("Knapsack DP")                                                      # edit buttons re-record on the new data
    lab.kn_cycle.set_value(L.KNAPSACK_PRESETS and list(L.KNAPSACK_PRESETS)[0])
    lab.set("kn_preset", list(L.KNAPSACK_PRESETS)[0])
    for label in ("cost+", "val+", "Add item", "B +", "val+", "cost-", "B -", "Remove item"):
        app.click_label(label)
        assert lab.rec.data["items"] == lab.items and lab.rec.data["budget"] == lab.budget
        assert lab.rec.result.total_benefit == ref_best(lab.items, lab.budget)


# --- scenario 5: championship and dashboard --------------------------------------------------------------------------------------
def recompute_standings(engines):
    """Points, wins, position sums and best laps from the finished race engines alone, then ranked with sorted()."""
    from smart_racing.core.models import ChampionshipEntry
    entries = {r.id: ChampionshipEntry(r.id) for r in engines[0].racers}
    per_race = []
    for eng in engines:
        order = eng.classification()
        fin = sorted((r for r in eng.racers if r.status == FINISHED), key=lambda r: (r.finish_time, r.id))
        assert [r.id for r in order[:len(fin)]] == [r.id for r in fin]
        best = min(fin, key=lambda r: (min(r.lap_times), r.id)) if fin else None
        got = {}
        for pos, r in enumerate(order, start=1):
            pts = (config.POINTS_TABLE[pos - 1] if r.status == FINISHED and pos <= len(config.POINTS_TABLE) else 0)
            pts += config.FASTEST_LAP_BONUS if r is best else 0
            en = entries[r.id]
            en.total_points += pts
            en.wins += pos == 1 and r.status == FINISHED
            en.sum_of_finish_positions += pos
            if r.lap_times:
                en.best_fastest_lap = min(en.best_fastest_lap, min(r.lap_times))
            got[r.id] = pts
        per_race.append(got)
    return champ_oracle(entries.values()), per_race


def standings_cells(texts, ranked, names, before=None):
    """The rows the standings table drew, in order: ['1  Name', pts, gain-or-wins, possum, lap]."""
    rows = []
    for place, e in enumerate(ranked, start=1):
        i = texts.index(f"{place}  {names[e.racer_id]}")
        rows.append(texts[i:i + 5])
    return rows


def lap_str(en):
    return f"{en.best_fastest_lap:.2f}" if en.best_fastest_lap != math.inf else "-"


def drive_race_as_player(app, spy, rs):
    """Manual race: take the recommended road at every junction, buy the recommended fuel, fire nitro now and then."""
    e, me = rs.engine, rs.me
    last = -99.0
    for _ in range(12000):
        if rs.results is not None:
            return
        ch = e.legal_choices(me.id)
        if e.station_offer(me.id) and me.status != REFUELLING and e.station_offer(me.id)[0] >= 1 and me.fuel < 60:
            app.press(pygame.K_r)
        elif len(ch) > 1 and me.chosen_edge is None:
            rec = [i for i, c in enumerate(ch) if c.recommended]
            app.press(pygame.K_1 + (rec[0] if rec else 0))
        elif me.edge_id is not None and me.nitro_charges and not me.nitro_active and e.clock - last > 30:
            app.press(pygame.K_SPACE)
            last = e.clock
        app.step(0.25)
    raise AssertionError("race did not finish")


def test_full_championship_standings_and_dashboard_match_recomputation(app, spy):
    app.settings.laps = 1
    app.click_label("Championship")
    flow = app.flow
    assert app.screen.phase == "briefing"
    done = []
    for k in range(3):
        assert app.screen.phase == "briefing" and app.screen.champ.race_number == k + 1
        texts = frame(app, spy)
        assert f"Championship - race {k + 1} of 3" in texts
        if k == 0:                                      # race 1 is driven by hand (the Your car selector), races 2 and 3 by autopilot
            app.click((app.screen.auto.box.right - 10, app.screen.auto.box.centery))
            assert "You drive" in frame(app, spy) and flow.champ.race_options["autopilot"] is False
        else:
            app.screen.auto.set_value(True) if not flow.champ.race_options["autopilot"] else None
            app.screen.set_auto(True)
        app.click_label("Start race")
        rs = app.screen
        assert rs.me.autopilot == (k != 0)
        rs.set_speed(4)
        if k == 0:
            skip_countdown(app, rs)
            drive_race_as_player(app, spy, rs)
            assert rs.me.driven, "the manual player never moved"
        else:
            assert run_until(app, lambda: rs.results is not None, 0.25)
        app.pump(frames=2)
        check_results_panel(app, spy, rs)
        app.click_label("Results and standings")
        assert app.screen_name == "championship" and app.screen.phase == "results"
        done.append(flow.champ.races[-1])
        assert flow.champ.races[-1] is rs.engine
        ranked, per_race = recompute_standings(done)
        texts = frame(app, spy)
        champ = flow.champ
        # the finish-order table of this race
        res = champ.results[-1]
        for r in res:
            rs_ = rs.engine.racer(r.racer_id)
            i = texts.index(f"{r.finish_position}  {champ.names[r.racer_id]}")
            when = f"{r.finish_time:.2f} s" if r.finish_time is not None else ("DNF" if rs_.status == "dnf" else "time limit")
            assert texts[i + 1] == when
            assert texts[i + 5] == f"{per_race[-1][r.racer_id] - r.bonus_points}" + (f" +{r.bonus_points}" if r.bonus_points else "")
        # standings after the race = independent recomputation (points, tie-breaks, order), gains = this race's points
        assert [e.racer_id for e in champ.standings().items] == [e.racer_id for e in ranked]
        before = {e.racer_id: sum(p[e.racer_id] for p in per_race[:-1]) for e in ranked}
        i = texts.index(f"Standings after race {k + 1}")
        cells = standings_cells(texts[i:], ranked, champ.names)
        for row, e in zip(cells, ranked):
            assert row[1:] == [str(e.total_points), f"+{e.total_points - before[e.racer_id]}",
                               str(e.sum_of_finish_positions), lap_str(e)], (row, e)
        app.click_label("Champion!" if k == 2 else "Next race")
    assert app.screen.phase == "champion" and flow.champ.finished
    ranked, per_race = recompute_standings(done)
    texts = frame(app, spy)
    assert texts[texts.index("CHAMPIONSHIP COMPLETE") + 1] == flow.champ.names[ranked[0].racer_id]
    assert f"{ranked[0].total_points} points, {ranked[0].wins} wins" in texts
    assert flow.champ.champion.racer_id == ranked[0].racer_id
    # dashboard on the live championship: the three sorts, comparison counts, top-k
    app.click_label("Dashboard")
    d = app.screen
    assert app.screen_name == "dashboard" and d.mode.value == "Current championship"
    entries = list(flow.champ.entries.values())
    for algo, fn in (("merge", sorting.merge_sort), ("quick", sorting.quick_sort), ("heap", sorting.heap_sort)):
        d.sort.set_value(algo)
        d.sort.step(0)
        d.refresh()
        texts = frame(app, spy)
        direct = fn(entries)
        assert [e.racer_id for e in direct.items] == [e.racer_id for e in ranked]
        names = flow.champ.names
        assert f"Standings ({algo} sort, n = {len(entries)})" in texts
        rows = standings_cells(texts, ranked, names)
        assert [r[0].split("  ", 1)[1] for r in rows] == [names[e.racer_id] for e in ranked]
        assert [r[1] for r in rows] == [str(e.total_points) for e in ranked]
        i = texts.index(f"{algo.capitalize()} sort")
        assert texts[i + 1] == str(direct.comparisons)                       # comparison count = direct call
    assert "Identical ranking: YES" in texts
    for k in (1, 2, 3, len(entries)):
        d.kcycle.options = d.kcycle.options if k in d.kcycle.options else sorted(d.kcycle.options + [k])
        d.kcycle.set_value(k)
        d.kcycle.step(0)
        d.refresh()
        texts = frame(app, spy)
        assert [e.racer_id for e in d.top.items] == [e.racer_id for e in ranked[:k]]
        assert f"Heap top-k: {d.top.comparisons} comparisons, {d.top.heap_ops} heap ops" in texts
        assert f"Full merge sort: {sorting.merge_sort(entries).comparisons} comparisons" in texts
        assert "Same leaders as the full sort: yes" in texts
        i = texts.index("Live top-k (heap)") + 1
        shown = texts[i + 2:i + 2 + 2 * min(k, 8)]                        # (rank + name, points) pairs
        assert shown[0::2] == [f"{p}  {flow.champ.names[e.racer_id]}" for p, e in enumerate(ranked[:min(k, 8)], 1)]
    # the per-race results table on the dashboard = the engine's results
    for i in range(3):
        d.race_cycle.set_value(i)
        d.race_cycle.step(0)
        texts = frame(app, spy)
        for r in flow.champ.results[i]:
            j = texts.index(f"{r.finish_position}  {flow.champ.names[r.racer_id]}", texts.index("Race results"))
            assert texts[j + 1] == (f"{r.finish_time:.1f}" if r.finish_time is not None else "DNF")
            assert texts[j + 3] == f"{r.points_awarded}" + (f"+{r.bonus_points}" if r.bonus_points else "")
    app.settings.laps = config.LAPS_PER_RACE


def test_dashboard_sample_field_matches_oracle_and_topk_is_cheaper(app, spy):
    app.goto("dashboard")
    d = app.screen
    sample = d.entries
    oracle = champ_oracle(sample)
    for algo in ("merge", "quick", "heap"):
        d.sort.set_value(algo)
        d.sort.step(0)
        d.refresh()
        assert [e.racer_id for e in d.ranking] == [e.racer_id for e in oracle]
    d.mode.step(1)                                        # the large sample field
    big = champ_oracle(d.entries)
    assert len(big) == 200
    d.kcycle.set_value(3)
    d.kcycle.step(0)
    d.refresh()
    texts = frame(app, spy)
    assert [e.racer_id for e in d.top.items] == [e.racer_id for e in big[:3]]
    assert d.top.comparisons < sorting.merge_sort(d.entries).comparisons
    assert "Same leaders as the full sort: yes" in texts and "Identical ranking: YES" in texts
    assert f"Standings ({d.sort.value} sort, n = 200)" in texts and "... top 8 of 200 shown" in texts


# --- scenario 6: generator ----------------------------------------------------------------------------------------------------------
def graph_signature(g):
    return ([(v.id, v.type, round(v.x, 6), round(v.y, 6), v.checkpoint_order) for v in g.vertices()],
            [(e.id, e.src, e.dst, e.distance, e.base_time, e.fuel_cost, e.difficulty, e.is_shortcut, e.directed) for e in g.edges()])


def test_generator_seed_29_report_stages_save_and_race(app, spy, tmp_path, monkeypatch):
    from smart_racing.tracks.generator import generate
    from smart_racing.tracks.loader import circuit_to_dict, load_circuit
    from smart_racing.tracks.validator import validate_circuit
    from smart_racing.ui.screens import generator as gen
    monkeypatch.setattr(gen, "SAVE_DIR", tmp_path / "saved")
    app.click_label("Track Generator")
    g = app.screen
    circuit, report = generate(29)                          # the independent run of the same seeded pipeline
    assert g.seed == 29 and report.success and [r.attempt for r in report.rejected] == [1]
    texts = frame(app, spy)
    rows = [s for s, _ in g.text.rows]
    assert "Seed 29: accepted on attempt 2 of " + str(config.GEN_MAX_ATTEMPTS) == rows[0] == f"Seed 29: accepted on attempt {report.attempts} of {config.GEN_MAX_ATTEMPTS}"
    rej = report.rejected[0]
    assert f"Attempt 1 rejected at {rej.stage}:" in rows and rej.reasons
    for why in rej.reasons:                                 # the validator's own wording, word for word
        assert why in " ".join(r.strip() for r in rows)         # (long reasons are word-wrapped over several rows)
    assert any("fuel" in why for why in rej.reasons)
    # the validator really does refuse that candidate for that reason: replay its verdict on the final circuit
    verdict = validate_circuit(circuit)
    assert verdict.ok and "PASS: every playability rule holds" in rows
    # every stage tab shows the report's stage graph
    for i, st in enumerate(report.stages):
        tab = g.tabs
        w = tab.rect.w / len(tab.names)
        app.click((tab.rect.x + i * w + w / 2, tab.rect.centery))
        assert g.stage == i and tab.index == i
        spy.clear()
        app.draw()
        shown = spy.views[0]["view"].graph
        assert graph_signature(shown) == graph_signature(st.graph), st.name
        assert st.description in spy.texts and f"Stage {i + 1}: {st.name}" in [s for s, _ in g.text.rows]
        overlay = spy.views[0]["overlays"]
        if st.name == "extras":
            assert overlay == [(list(st.info["extras"]), widgets.WARN)]
        elif st.name == "one_way":
            assert overlay == [(list(st.info["one_way"]), widgets.WARN)]
        else:
            assert overlay == [] or st.name == "loop"
    # a typed seed, Enter, arrows
    for ch in "5":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=ord(ch), mod=0, unicode=ch, scancode=0))
    app.step(0.0)
    assert "Seed 5_" in frame(app, spy)
    app.press(pygame.K_RETURN)
    c5, r5 = generate(5)
    assert g.seed == 5 and [s for s, _ in g.text.rows][0].startswith(f"Seed 5: " + ("accepted" if r5.success else "FAILED"))
    assert len([s for s, _ in g.text.rows if s.startswith("Attempt ")]) == len(r5.rejected)
    app.click_label("Demo: seed 29")
    assert g.seed == 29
    # save: the JSON reloads to an equal circuit
    app.click_label("Save circuit")
    path = tmp_path / "saved" / "generated_seed29.json"
    assert path.exists() and g.message == f"Saved to {path}" and widgets.fit(g.message, 19, 760) in frame(app, spy)
    again = load_circuit(path)
    assert circuit_to_dict(again) == circuit_to_dict(g.circuit) == circuit_to_dict(circuit)
    assert graph_signature(again.graph) == graph_signature(circuit.graph) and again.events == circuit.events
    # race on this track: a full race to completion on exactly this circuit
    app.click_label("Race on it")
    rs = app.screen
    assert app.screen_name == "race" and rs.engine.circuit.name == "Generated #29"
    assert graph_signature(rs.engine.graph) == graph_signature(circuit.graph)
    rs.set_speed(4)
    assert run_until(app, lambda: rs.results is not None, 0.25)
    app.pump(frames=2)
    assert rs.engine.finished and len(rs.results) == 4 and any(r.status == FINISHED for r in rs.engine.racers)
    check_results_panel(app, spy, rs)


# --- scenario 7: menu, settings, error paths --------------------------------------------------------------------------------------------
def click_cycle(app, cycle, steps=1):
    for _ in range(steps):
        app.click((cycle.box.right - 10, cycle.box.centery))


def test_every_menu_entry_opens_and_returns(app, spy):
    entries = [("Championship", "championship"), ("Quick Race", "quick"), ("Track Explorer", "explorer"),
               ("Algorithm Lab", "lab"), ("Championship Dashboard", "dashboard"), ("Track Generator", "generator"),
               ("Instructions", "instructions"), ("Settings", "settings")]
    for label, name in entries:
        for leave in ("Back", "Esc"):
            app.click_label(label)
            assert app.screen_name == name
            app.pump(frames=2)
            if leave == "Back":
                app.click_label("Back")
            else:
                app.press(pygame.K_ESCAPE)
            assert app.screen_name == "menu", (label, leave)


def test_settings_reach_the_race_that_starts(app, spy):
    app.click_label("Settings")
    st = app.screen
    cyc = {c.caption: c for c in st.widgets if hasattr(c, "options")}
    click_cycle(app, cyc["Laps per race"], 2)                  # 1 -> 3 laps... the shipped default is read first
    laps = app.settings.laps
    assert laps == cyc["Laps per race"].value
    click_cycle(app, cyc["Default cost preset"], 1)
    preset = app.settings.preset
    click_cycle(app, cyc["Simulation speed"], 1)
    speed = app.settings.speed
    assert preset == cyc["Default cost preset"].value and speed == cyc["Simulation speed"].value
    app.click_label("Back")
    app.click_label("Quick Race")
    q = app.screen
    assert (q.laps.value, q.preset.value) == (laps, preset)     # Quick Race shows what Settings chose
    click_cycle(app, q.planner, 1)                              # dp -> greedy
    click_cycle(app, q.opp, 1)
    click_cycle(app, q.auto, 1)                                 # autopilot off
    chosen = (app.settings.pickup_solver, app.settings.opponents, app.settings.autopilot, app.settings.circuit)
    assert chosen[0] == "greedy" and chosen[2] is False
    app.click_label("Start Race")
    rs = app.screen
    e = rs.engine
    assert app.screen_name == "race" and e.laps == laps and rs.speed == speed
    assert rs.me.strategy.preset == preset and rs.me.strategy.pickup_solver == "greedy"
    assert len(e.racers) == 1 + chosen[1] and rs.me.autopilot is False and e.circuit.name.lower().replace(" ", "_") == chosen[3]
    assert f"Lap 1/{laps}" in frame(app, spy)
    app.press(pygame.K_TAB)                                     # Tab cycles from the setting's speed and writes it back
    assert rs.speed != speed and app.settings.speed == rs.speed
    # the settings screen then shows the speed that Tab chose
    app.press(pygame.K_ESCAPE)
    app.click_label("Quit to menu")
    app.click_label("Settings")
    cyc = {c.caption: c for c in app.screen.widgets if hasattr(c, "options")}
    assert cyc["Simulation speed"].value == app.settings.speed


def test_championship_uses_the_settings_laps_and_autopilot(app, spy):
    app.settings.laps = 2
    app.click_label("Championship")
    assert app.flow.champ.laps == 2 and "2 laps, cost preset Balanced" in frame(app, spy)
    app.click_label("Start race")
    assert app.screen.engine.laps == 2 and f"Lap 1/2" in frame(app, spy)


def test_rapid_clicks_escape_and_stray_keys_never_corrupt_state(app, spy):
    import random
    rng = random.Random(3)
    keys = [pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN, pygame.K_TAB, pygame.K_a, pygame.K_p, pygame.K_r, pygame.K_f,
            pygame.K_1, pygame.K_2, pygame.K_9, pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_BACKSPACE,
            pygame.K_PAGEDOWN, pygame.K_HOME]

    def hammer(n):
        for _ in range(n):
            r = rng.random()
            if r < 0.5:
                app.click((rng.randrange(0, 1280), rng.randrange(0, 720)), button=rng.choice((1, 1, 3)))
            elif r < 0.9:
                app.press(rng.choice(keys))
            else:
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=rng.choice((-3, 3)), flipped=False))
                app.step(0.05)
            assert app.error is None, app.error
            if app.screen_name == "menu" and rng.random() < 0.5:      # keep wandering through the screens
                app.goto(rng.choice(["quick", "explorer", "lab", "dashboard", "generator", "settings", "instructions",
                                     "championship", "race"]))
    hammer(700)
    # a race hammered during the countdown, mid-race, paused and in the results modal stays consistent
    rs = start_race(app, "harbor_eight", laps=1, autopilot=False, speed=4)
    e, me = rs.engine, rs.me
    for _ in range(60):                                         # countdown: clock must not move
        app.press(rng.choice(keys[1:]))
        app.click((rng.randrange(0, 960), rng.randrange(60, 626)))
        if app.screen is not rs:
            break
    assert app.screen is not rs or e.clock == 0
    app.goto("race", circuit="harbor_eight", laps=1, autopilot=True)
    rs = app.screen
    rs.set_speed(4)
    e, me = rs.engine, rs.me
    last = 0.0
    for _ in range(3000):
        if rs.results is not None or app.screen is not rs:
            break
        r = rng.random()
        if r < 0.3:
            app.press(rng.choice([k for k in keys if k != pygame.K_ESCAPE or rng.random() < 0.3]))
        elif r < 0.5:
            app.click((rng.randrange(0, 1280), rng.randrange(0, 720)))
        app.step(0.25)
        assert app.error is None and e.clock >= last and all(0 <= x.fuel <= 100 for x in e.racers)
        last = e.clock
    if app.screen is rs and rs.results is not None:
        snap = (e.clock, me.fuel, me.nitro_charges, rs.speed, len(rs.results), [r.finish_position for r in rs.results])
        for _ in range(80):                                     # results modal: stray keys and clicks change nothing
            app.press(rng.choice([k for k in keys if k != pygame.K_ESCAPE]))
            app.click((rng.randrange(0, 1280), rng.randrange(0, 720)))
            if app.screen is not rs:
                break
        if app.screen is rs:
            assert snap[:3] == (e.clock, me.fuel, me.nitro_charges) and snap[4:] == (len(rs.results), [r.finish_position for r in rs.results])
            app.press(pygame.K_ESCAPE)
            assert app.screen_name == "menu"


# --- text must stay inside its column and the window ----------------------------------------------------------------------------------------
def overflow(spy, x0=0, x1=1280, y1=720):
    """Strings drawn from x >= x0 that stick out past x1 on the right or past y1 at the bottom."""
    return [(s, tuple(r)) for s, r in spy.rects if r.x >= x0 and (r.right > x1 or r.bottom > y1)]


def test_race_text_stays_inside_the_right_column_in_every_state(app, spy):
    rs = start_race(app, "harbor_eight", laps=1, autopilot=False)
    e, me, g = rs.engine, rs.me, rs.engine.graph
    skip_countdown(app, rs)
    seen = set()

    def look():
        ch = e.legal_choices(me.id)
        state = ("offer" if e.station_offer(me.id) else "") + ("choices" if len(ch) > 1 else "") + ("boost" if me.nitro_active else "")
        frame(app, spy)
        assert not overflow(spy, race_screen.COL_X, race_screen.COL_X + race_screen.COL_W), (state, overflow(spy, 972, 1268))
        assert not overflow(spy), state
        assert rs._events_rect().bottom <= 720 and rs._prompt_rect().bottom <= rs._events_rect().y
        seen.add(state)

    drive_to(app, spy, rs, g.vertices_of_type("FuelStation")[0].id)
    me.fuel = 20.0
    look()                                                      # at a station: buy block plus the road options
    app.press(pygame.K_f)
    for _ in range(80):
        app.step(0.05)
    look()
    for _ in range(600):
        if me.edge_id is not None and not me.nitro_active:
            app.press(pygame.K_SPACE)
            look()
            break
        if len(e.legal_choices(me.id)) > 1 and me.chosen_edge is None:
            look()
            app.press(pygame.K_1)
        app.step(0.25)
    assert "offerchoices" in seen and any("boost" in x for x in seen), seen
    frame(app, spy)
    assert not overflow(spy)                                    # results modal
    # ten racers: every panel is still inside the window
    app.goto("race", circuit="grand_ring", laps=1, autopilot=False, opponents=9)
    rs = app.screen
    frame(app, spy)
    assert len(rs.engine.racers) == 10 and not overflow(spy) and rs._events_rect().bottom <= 720


@pytest.mark.parametrize("screen,kw", [("quick", {}), ("settings", {}), ("instructions", {}), ("dashboard", {}),
                                      ("generator", {}), ("championship", {"new": True}), ("lab", {"algo": "Event heap"}),
                                      ("lab", {"algo": "Knapsack DP"}), ("lab", {"algo": "Quick sort"}), ("lab", {"algo": "Backtracking"}),
                                      ("explorer", {"circuit": "serpent_pass"})])
def test_screen_text_is_inside_the_window(app, spy, screen, kw):
    app.goto(screen, **kw)
    app.pump(frames=2)
    frame(app, spy)
    assert not overflow(spy), overflow(spy)
    if screen == "explorer":
        for tab in ("Routes", "Compare", "Resources", "Reach"):
            click_tab(app, tab)
            app.click_label("Run DFS") if tab == "Reach" else None
            frame(app, spy)
            assert not overflow(spy, 782, 1268, 712), (tab, overflow(spy, 782, 1268, 712))
    if screen == "lab":
        play_to_end(app, app.screen)
        frame(app, spy)
        assert not overflow(spy, 782, 1268, 712), overflow(spy, 782, 1268, 712)


def test_explorer_hover_text_describes_the_road_under_the_mouse(app, spy):
    ex = explorer(app, "harbor_eight")
    g = ex.g
    for edge in g.edges()[:12]:
        mid = ex.view.edge_mid(edge)
        if ex.view.vertex_at(mid) is not None:
            continue
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(int(mid[0]), int(mid[1])), rel=(0, 0), buttons=(0, 0, 0)))
        app.step(0.0)
        picked = ex.view.edge_at((int(mid[0]), int(mid[1])))
        e = g.edge(picked)
        way = f"one-way {e.src} to {e.dst}" if e.directed else f"{e.src} - {e.dst}"
        assert ex.hover_text == (f"Road {e.id}: {way}{', shortcut' if e.is_shortcut else ''}, dist {e.distance:g}, "
                                 f"time {e.effective_time:g}s, fuel {e.effective_fuel:.1f}, difficulty {e.effective_difficulty}, {e.status}")
        assert ex.hover_text in frame(app, spy) or widgets.fit(ex.hover_text, 21, 744) in frame(app, spy)
    v = g.checkpoints()[2]
    p = ex.view.pt(v.id)
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(int(p[0]), int(p[1])), rel=(0, 0), buttons=(0, 0, 0)))
    app.step(0.0)
    assert ex.hover_text == f"Vertex {v.id}: {v.type}, checkpoint {v.checkpoint_order}"


def test_choice_closed_before_the_car_leaves_is_dropped_with_a_message(app, spy):
    """Regression: a chosen road that closes before the car leaves used to be replaced silently."""
    rs = start_race(app, "harbor_eight", laps=1, autopilot=False)
    e, me, g = rs.engine, rs.me, rs.engine.graph
    skip_countdown(app, rs)
    assert run_until(app, lambda: len(e.legal_choices(me.id)) > 1 and me.edge_id is not None, 0.05)
    choices = e.legal_choices(me.id)
    want = choices[-1].edge_id
    app.press(pygame.K_1 + len(choices) - 1)
    assert me.chosen_edge == want
    g.block_edge(want, "closure")                               # the track event arrives before the car does
    before = len(me.driven)
    said = []
    assert run_until(app, lambda: said.append(bool(rs.hint and "no longer available" in rs.hint[0]
                                                   and rs.hint[0] in frame(app, spy))) or len(me.driven) > before, 0.05)
    assert me.driven[-1] != want and me.chosen_edge is None and any(said)

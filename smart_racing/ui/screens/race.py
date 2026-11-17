"""Racing Screen: the engine runs on its fixed tick, this file draws it and forwards the player's input.

`circuit` is a built-in name or a Circuit (copied, so Restart always starts from the untouched track).
Hook for the championship flow: `RaceScreen(app, engine=..., on_finish=fn, on_continue=fn, on_restart=fn)`.
`on_finish(engine)` is called once when the race ends (record the result there); when `on_continue` is
given the results panel shows a "Next race" button (label via `continue_label`) that calls it.
"""
from __future__ import annotations

import math

import pygame

from smart_racing import config
from smart_racing.engine.championship import score_race
from smart_racing.engine.race import DNF, FINISHED, REFUELLING, WAITING, RaceEngine, create_race, default_racers
from smart_racing.tracks.loader import Circuit, circuit_from_dict, circuit_to_dict
from smart_racing.ui.app import H, W, Screen
from smart_racing.ui.render import CAR_COLORS, GraphView, Overlay, draw_legend
from smart_racing.ui.widgets import (ACCENT, BAD, BORDER, DIM, GOOD, PANEL, ROUTE_COLORS, TEXT, WARN, Button, Panel,
                                     blend, draw_bar, draw_table, fit, text, wrap)

VIEW = pygame.Rect(12, 60, 948, 566)
LEGEND = pygame.Rect(12, 634, 948, 78)
COL_X, COL_W = 972, 296
YOU = pygame.Rect(COL_X, 60, COL_W, 170)
PROMPT_H = 178
SPEEDS = (1, 2, 4)
SKIP_LOG = {"checkpoint", "nitro", "refuel", "pickup", "reroute"}      # shown for the player only


def clock_text(t: float) -> str:
    return f"{int(t) // 60:02d}:{t % 60:04.1f}"


class RaceScreen(Screen):
    def __init__(self, app, circuit: str | None = None, laps: int | None = None, preset: str | None = None,
                 opponents: int | None = None, autopilot: bool | None = None, pickup_solver: str | None = None, engine: RaceEngine | None = None,
                 on_finish=None, on_continue=None, continue_label: str = "Next race", on_restart=None,
                 **kw) -> None:
        super().__init__(app)
        s = app.settings
        self.config = dict(circuit=circuit or s.circuit, laps=laps or s.laps, preset=preset or s.preset,
                           opponents=s.opponents if opponents is None else opponents,
                           autopilot=s.autopilot if autopilot is None else autopilot,
                           pickup_solver=pickup_solver or s.pickup_solver)
        track = self.config["circuit"]
        if isinstance(track, Circuit):
            track = circuit_from_dict(circuit_to_dict(track))
        self.engine = engine or create_race(track, self.config["laps"], self.config["preset"],
                                            default_racers(self.config["opponents"]),
                                            autopilot=self.config["autopilot"],
                                            pickup_solver=None if self.config["pickup_solver"] == "none"
                                            else self.config["pickup_solver"])
        e = self.engine
        self.on_finish, self.on_continue, self.continue_label = on_finish, on_continue, continue_label
        self.on_restart = on_restart
        self.me = e.human
        self.view = GraphView(e.graph, VIEW, 48)
        self.speed = s.speed
        self.paused, self.countdown, self.t = False, 3.0, 0.0
        self.msgs: list[tuple[float, str, tuple]] = []
        self.banner: tuple[str, float] | None = None
        self.hint: tuple[str, float] | None = None
        self.flash: dict[int, float] = {}
        self._sig = self._signature()
        self._nfeed = self._nlog = 0
        self.heading = {r.id: 0.0 for r in e.racers}
        self.results = None
        self.buy_amount, self._offer_at = 0, None
        self.title = e.circuit.name
        self.speed_buttons = [Button((640 + i * 56, 10, 50, 36), f"{v}x", lambda v=v: self.set_speed(v))
                              for i, v in enumerate(SPEEDS)]
        self.bar = self.speed_buttons + [Button((812, 10, 100, 36), "Pause", self.toggle_pause),
                                         Button((920, 10, 100, 36), "Menu", lambda: app.goto("menu"))]
        self.auto_button = Button((1028, 10, 240, 36), "", self.toggle_auto)
        self.bar.append(self.auto_button)
        self.buy_buttons = []
        py = self._prompt_rect().y
        self.minus = Button((COL_X + 12, py + 74, 44, 30), "-5", lambda: self.adjust(-5))
        self.plus = Button((COL_X + 126, py + 74, 44, 30), "+5", lambda: self.adjust(5))
        self.buy = Button((COL_X + 178, py + 74, 106, 30), "Buy", self.buy_custom, color=(40, 120, 70))
        self.buy_rec = Button((COL_X + 12, py + 108, 134, 30), "Recommended", self.buy_recommended)
        self.buy_max = Button((COL_X + 150, py + 108, 134, 30), "Fill up", self.buy_fill)
        self.buy_buttons = [self.minus, self.plus, self.buy, self.buy_rec, self.buy_max]
        for b in self.buy_buttons:
            b.visible = False
        self.modal: list[Button] = []

    # --- layout ----------------------------------------------------------------------------------
    def _order_rect(self) -> pygame.Rect:
        n = len(self.engine.racers)
        return pygame.Rect(COL_X, YOU.bottom + 8, COL_W, 34 + n * 21)

    def _prompt_rect(self) -> pygame.Rect:
        order = self._order_rect()
        extra = 3 * 21 if any(b.visible for b in self.buy_buttons) else 0     # the buy block needs room below it for the road options
        return pygame.Rect(COL_X, order.bottom + 8, COL_W, min(PROMPT_H + extra, 712 - order.bottom - 8))

    def _events_rect(self) -> pygame.Rect:
        p = self._prompt_rect()
        return pygame.Rect(COL_X, p.bottom + 8, COL_W, max(40, 712 - p.bottom - 8))

    def all_widgets(self) -> list:
        return self.modal if self.modal else self.bar + self.buy_buttons

    # --- engine helpers ----------------------------------------------------------------------------
    def _signature(self) -> dict:
        return {e.id: (e.status, e.effective_difficulty) for e in self.engine.graph.edges()}

    @property
    def manual(self) -> bool:
        return self.me is not None and not self.me.autopilot and self.me.active

    def set_speed(self, v: int) -> None:
        self.speed = v
        self.app.settings.speed = v

    def toggle_pause(self) -> None:
        if not self.engine.finished:
            self.paused = not self.paused
            self._build_modal()

    def toggle_auto(self) -> None:
        if self.me and self.me.active:
            self.engine.set_autopilot(self.me.id, not self.me.autopilot)

    def adjust(self, delta: int) -> None:
        offer = self.engine.station_offer(self.me.id)
        if offer:
            self.buy_amount = max(1, min(offer[0], self.buy_amount + delta))

    def _buy(self, amount: int) -> None:
        offer = self.engine.station_offer(self.me.id)
        if amount < 1 or not offer or offer[0] < 1 or not self.engine.refuel(self.me.id, amount):   # offer[0] < 1: under 1 unit of room
            self.note("Cannot buy fuel here.")

    def buy_custom(self) -> None:
        self._buy(self.buy_amount)

    def buy_recommended(self) -> None:
        offer = self.engine.station_offer(self.me.id)
        if offer and offer[1] < 1:
            self.note("Nothing recommended here: the plan needs no fuel at this station.")
        elif offer:
            self._buy(offer[1])

    def buy_fill(self) -> None:
        offer = self.engine.station_offer(self.me.id)
        if offer:
            self._buy(offer[0])

    def choose(self, index: int) -> None:
        if not self.manual:
            return self.note("Autopilot is on: press A (or the Autopilot button) to pick roads yourself.")
        choices = self.engine.legal_choices(self.me.id)
        if 0 <= index < len(choices):
            self.engine.choose_edge(self.me.id, choices[index].edge_id)
        elif len(choices) > 1:
            self.note(f"No option {index + 1} here.")

    def note(self, s: str) -> None:
        self.hint = (s, 2.5)

    def _build_modal(self) -> None:
        self.modal = []
        mx = W // 2 - 140
        if self.paused:
            self.modal = [Button((mx, 300, 280, 50), "Resume", self.toggle_pause),
                          Button((mx, 360, 280, 50), "Restart race", self.restart),
                          Button((mx, 420, 280, 50), "Quit to menu", lambda: self.app.goto("menu"))]
        elif self.results is not None:
            y = 270 + 28 * len(self.results)
            row = [Button((350, y, 280, 50), "Race again", self.restart),
                   Button((650, y, 280, 50), "Main menu", lambda: self.app.goto("menu"))]
            if self.on_continue:
                row[0] = Button((350, y, 280, 50), self.continue_label, self.on_continue, color=(40, 120, 70))
            self.modal = row

    def restart(self) -> None:
        if self.on_restart:
            self.on_restart()
        else:
            self.app.goto("race", **self.config)

    # --- input -------------------------------------------------------------------------------------------
    def on_escape(self) -> None:
        if self.engine.finished:
            self.app.goto("menu")
        else:
            self.toggle_pause()

    def handle_event(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN and not self.modal and self.me:
            k = ev.key
            if k == pygame.K_p:
                self.toggle_pause()
            elif k == pygame.K_a:
                self.toggle_auto()
            elif k == pygame.K_SPACE and self.me.active and not self.paused:
                if not self.engine.fire_nitro(self.me.id):
                    self.note("No nitro charge, or a boost is already running.")
            elif k == pygame.K_TAB:
                self.set_speed(SPEEDS[(SPEEDS.index(self.speed) + 1) % len(SPEEDS)])
            elif pygame.K_1 <= k <= pygame.K_9:
                self.choose(k - pygame.K_1)
            elif k == pygame.K_r:
                self.buy_recommended()
            elif k == pygame.K_f:
                self.buy_fill()
            elif k in (pygame.K_UP, pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.adjust(5)
            elif k in (pygame.K_DOWN, pygame.K_MINUS, pygame.K_KP_MINUS):
                self.adjust(-5)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.buy_custom()
            return True
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and not self.modal and self.manual
                and VIEW.collidepoint(ev.pos)):
            choices = self.engine.legal_choices(self.me.id)
            if len(choices) > 1:
                edge = self.view.edge_at(ev.pos, 12, [c.edge_id for c in choices])
                if edge is not None:
                    self.choose([c.edge_id for c in choices].index(edge))
                    return True
        return super().handle_event(ev)

    # --- update ---------------------------------------------------------------------------------------------
    def update(self, dt: float) -> None:
        e = self.engine
        self.t += dt
        for key in list(self.flash):
            self.flash[key] -= dt
            if self.flash[key] <= 0:
                del self.flash[key]
        for name in ("banner", "hint"):
            val = getattr(self, name)
            if val:
                setattr(self, name, (val[0], val[1] - dt) if val[1] - dt > 0 else None)
        if self.countdown > 0:
            self.countdown = 0.0 if self.paused else max(0.0, self.countdown - dt)
        elif not self.paused and not e.finished:
            # a manual player standing at a decision is given real time to choose
            slow = self.manual and self.me.edge_id is None and (e.station_offer(self.me.id)
                                                                  or len(e.legal_choices(self.me.id)) > 1)
            me, picked, n0 = self.me, self.me.chosen_edge if self.me else None, len(self.me.driven) if self.me else 0
            e.update(min(dt, 0.25) * (1 if slow else self.speed))
            if picked is not None and me.chosen_edge is None and picked not in me.driven[n0:]:
                self.note("Your chosen road is no longer available: the recommended road was taken.")
        self.sync()
        if e.finished and self.results is None:
            self.results = score_race(1, e)
            self._build_modal()
            if self.on_finish:
                self.on_finish(e)

    def sync(self) -> None:
        e = self.engine
        for entry in e.feed[self._nfeed:]:
            self.msgs.append((entry.time, entry.text, WARN))
        self._nfeed = len(e.feed)
        for entry in e.log[self._nlog:]:
            mine = self.me is not None and entry.racer_id == self.me.id
            if entry.kind == "reroute" and mine:
                self.banner = ("Your route was recalculated", 3.5)
            if mine or entry.kind not in SKIP_LOG:
                self.msgs.append((entry.time, entry.text, ROUTE_COLORS[0] if mine else DIM))
        self._nlog = len(e.log)
        sig = self._signature()
        for edge_id, state in sig.items():
            if state != self._sig.get(edge_id):
                self.flash[edge_id] = 1.6
        self._sig = sig
        for r in e.racers:
            if r.edge_id is not None:
                a, b = self.view.pt(r.from_vertex), self.view.pt(r.to_vertex)
                self.heading[r.id] = math.atan2(b[1] - a[1], b[0] - a[0])
            elif r.route and r.active:
                edge = e.graph.edge(r.route[0])
                a, b = self.view.pt(r.current_vertex), self.view.pt(edge.other(r.current_vertex))
                self.heading[r.id] = math.atan2(b[1] - a[1], b[0] - a[0])
        offer = e.station_offer(self.me.id) if self.me else None
        here = self.me.current_vertex if offer else None
        if here != self._offer_at:
            self._offer_at = here
            self.buy_amount = offer[1] if offer else 0
        show = bool(offer) and self.manual and not self.modal
        for b in self.buy_buttons:
            b.visible = show

    # --- drawing -----------------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        e = self.engine
        surf.fill((14, 18, 26))
        self.draw_bar(surf)
        pygame.draw.rect(surf, (18, 23, 33), VIEW, border_radius=8)
        pygame.draw.rect(surf, BORDER, VIEW, 1, border_radius=8)
        overlays, rings, tags = [], {}, {}
        choices = e.legal_choices(self.me.id) if self.manual else []
        if self.me and self.me.active:
            route = ([self.me.edge_id] if self.me.edge_id is not None else []) + list(self.me.route)
            overlays.append(Overlay(route, ROUTE_COLORS[0], 4))
            target = e.next_target(self.me)
            pulse = 0.5 + 0.5 * math.sin(self.t * 6)
            rings[target] = blend((255, 200, 60), (255, 255, 255), pulse)
        if len(choices) > 1:
            overlays.append(Overlay([c.edge_id for c in choices], WARN, 8))
        self.view.draw(surf, self.app.settings.show_ids, overlays, rings, self.flash, tags)
        for r in reversed(e.racers):
            self.draw_racer(surf, r)
        if len(choices) > 1:
            self.draw_badges(surf, choices)
        self.draw_view_overlays(surf)
        draw_legend(surf, LEGEND)
        self.draw_you(surf)
        self.draw_order(surf)
        self.draw_prompt(surf, choices)
        self.draw_events(surf)
        for w in self.all_widgets():
            if w.visible and w not in self.bar:
                w.draw(surf)
        if self.paused or self.results is not None:
            self.draw_modal(surf)
            for w in self.modal:
                w.draw(surf)

    def draw_bar(self, surf) -> None:
        e = self.engine
        lap = min(self.me.lap + 1, e.laps) if self.me else 1
        text(surf, self.title, (14, 28), 32, TEXT, "midleft", bold=True)
        text(surf, f"Lap {lap}/{e.laps}", (270, 28), 28, ACCENT, "midleft", bold=True)
        text(surf, clock_text(e.clock), (420, 28), 32, TEXT, "midleft", bold=True)
        text(surf, "Speed", (590, 28), 21, DIM, "midleft")
        self.auto_button.label = f"Autopilot: {'ON' if self.me and self.me.autopilot else 'OFF'} (A)"
        self.auto_button.toggled = bool(self.me and self.me.autopilot)
        for b, v in zip(self.speed_buttons, SPEEDS):
            b.toggled = v == self.speed
        self.bar[3].label = "Resume" if self.paused else "Pause"
        for b in self.bar:
            b.draw(surf)

    def draw_badges(self, surf, choices) -> None:
        r = self.me
        here = r.current_vertex if r.edge_id is None else r.to_vertex
        a = self.view.pt(here)
        for i, c in enumerate(choices):
            b = self.view.pt(c.to_vertex)
            p = (a[0] + (b[0] - a[0]) * 0.5, a[1] + (b[1] - a[1]) * 0.5)
            color = GOOD if c.recommended else WARN
            pygame.draw.circle(surf, color, p, 12)
            pygame.draw.circle(surf, (20, 20, 20), p, 12, 2)
            text(surf, str(i + 1), p, 22, (15, 15, 15), "center", bold=True)

    def draw_racer(self, surf, r) -> None:
        e = self.engine
        x, y = self.view.to_screen(*e.xy(r.id))
        if r.edge_id is None:
            x, y = x + (r.id % 3 - 1) * 6, y + (r.id // 3 - 1) * 6
        faded = r.status in (FINISHED, DNF)
        self.view.draw_car(surf, (x, y), self.heading[r.id], CAR_COLORS[r.id % len(CAR_COLORS)],
                           "", r.is_human and not faded, r.nitro_active, faded)

    def draw_view_overlays(self, surf) -> None:
        if self.banner:
            s = self.banner[0]
            w = 40 + len(s) * 9
            box = pygame.Rect(VIEW.centerx - w // 2, VIEW.y + 8, w, 32)
            pygame.draw.rect(surf, (90, 60, 10), box, border_radius=8)
            pygame.draw.rect(surf, WARN, box, 2, border_radius=8)
            text(surf, s, box.center, 25, (255, 235, 180), "center", bold=True)
        if self.hint:
            text(surf, self.hint[0], (VIEW.centerx, VIEW.bottom - 14), 22, TEXT, "midbottom")
        if self.countdown > 0:
            n = math.ceil(self.countdown)
            text(surf, str(n) if n > 0 else "GO", VIEW.center, 150, (255, 255, 255), "center", bold=True)

    def draw_you(self, surf) -> None:
        e, r = self.engine, self.me
        Panel(YOU, "You").draw(surf)
        if r is None:
            return
        x, y = YOU.x + 12, YOU.y + 32
        pos = e.race_position(r.id)
        text(surf, f"P{pos}/{len(e.racers)}", (x, y), 34, GOOD if pos == 1 else TEXT, bold=True)
        lap = min(r.lap + 1, e.laps)
        text(surf, f"Lap {lap}/{e.laps}", (x + 100, y + 2), 28, TEXT, bold=True)
        nxt = (f"Next: checkpoint {r.next_checkpoint}" if r.next_checkpoint <= e.num_checkpoints else "Next: Finish")
        text(surf, f"{nxt} (v{e.next_target(r)})", (x, y + 34), 22, (255, 210, 90))
        frac = r.fuel / config.TANK_CAPACITY
        draw_bar(surf, (x, y + 58, COL_W - 24, 22), frac, BAD if frac < 0.25 else GOOD if frac > 0.5 else WARN,
                 f"Fuel {r.fuel:.0f} / {config.TANK_CAPACITY:.0f}")
        text(surf, "Nitro", (x, y + 88), 21, DIM, "midleft")
        for i in range(config.NITRO_MAX_CHARGES):
            c = (x + 62 + i * 30, y + 88)
            pygame.draw.polygon(surf, (50, 140, 255) if i < r.nitro_charges else (45, 55, 75),
                                [(c[0], c[1] - 11), (c[0] + 11, c[1]), (c[0], c[1] + 11), (c[0] - 11, c[1])])
        if r.nitro_active:
            draw_bar(surf, (x + 160, y + 78, COL_W - 24 - 160, 20), r.nitro_left / config.NITRO_DURATION,
                     (255, 140, 30), f"BOOST {r.nitro_left:.1f}s")
        status = {WAITING: f"Waiting: {r.wait_reason} ({r.wait_time:.0f}/{config.DNF_WAIT_TIME:.0f} s)",
                  REFUELLING: f"Refuelling ({r.stop_left:.1f} s)", FINISHED: "Finished",
                  DNF: "DNF"}.get(r.status, "Driving")
        text(surf, fit(status, 21, COL_W - 24), (x, y + 110), 21, BAD if r.status in (WAITING, DNF) else DIM)

    def draw_order(self, surf) -> None:
        e = self.engine
        rect = self._order_rect()
        Panel(rect, "Running order").draw(surf)
        for i, r in enumerate(e.live_top_k(len(e.racers)).items):
            y = rect.y + 32 + i * 21
            if self.me and r.id == self.me.id:
                pygame.draw.rect(surf, (40, 52, 76), (rect.x + 6, y - 2, rect.w - 12, 21), border_radius=4)
            pygame.draw.rect(surf, CAR_COLORS[r.id % len(CAR_COLORS)], (rect.x + 34, y + 2, 12, 12), border_radius=3)
            text(surf, str(i + 1), (rect.x + 14, y), 21, TEXT, bold=True)
            text(surf, fit(r.name, 21, 112), (rect.x + 54, y), 21, TEXT, bold=r.is_human)
            if r.status == FINISHED:
                info, color = f"FIN {r.finish_time:.1f}s", GOOD
            elif r.status == DNF:
                info, color = "DNF", BAD
            else:
                info, color = f"L{min(r.lap + 1, e.laps)} CP{r.checkpoints_done}", DIM
            text(surf, info, (rect.right - 12, y), 20, color, "topright")

    def draw_prompt(self, surf, choices) -> None:
        e, r = self.engine, self.me
        rect = self._prompt_rect()
        Panel(rect, "Controls").draw(surf)
        x, y = rect.x + 12, rect.y + 32
        if r is None or not r.active:
            return
        offer = e.station_offer(r.id)
        if self.manual and offer:
            grace = max(0.0, config.PLAYER_CHOICE_GRACE - r.idle)
            text(surf, f"Station: max {offer[0]}, recommended {offer[1]}", (x, y), 20, WARN, bold=True)    # 264 px at most: fits the column
            text(surf, f"{r.fuel:.0f}/{config.TANK_CAPACITY:.0f} in tank; auto in {grace:.1f} s", (x, y + 22), 20, DIM)
            text(surf, f"{self.buy_amount} units", (COL_X + 91, y + 57), 22, TEXT, "midtop")    # centred in the gap between -5 and +5
            y += 112
        elif self.manual and len(choices) > 1:
            here = r.current_vertex if r.edge_id is None else r.to_vertex
            grace = max(0.0, config.PLAYER_CHOICE_GRACE - r.idle) if r.edge_id is None else None
            head = f"Choose the road from v{here}" + (f" ({grace:.1f} s)" if grace is not None else "")
            text(surf, head, (x, y), 21, WARN, bold=True)
            y += 24
        elif self.manual:
            text(surf, "Manual: forced road, no choice." if choices else "Manual: no road open yet.", (x, y), 21, DIM)
            y += 24
        else:
            text(surf, "Autopilot drives and refuels.", (x, y), 21, GOOD)
            text(surf, "A: take over  Space: nitro", (x, y + 22), 20, DIM)
            text(surf, "Tab: speed   P/Esc: pause", (x, y + 44), 20, DIM)
            text(surf, fit(self.planner_line(), 20, COL_W - 24), (x, y + 66), 20, ACCENT)
            return
        if len(choices) > 1:
            for i, c in enumerate(choices[:max(1, (rect.bottom - y - 6) // 21)]):
                chosen = r.chosen_edge == c.edge_id
                line = f"{i + 1}: to v{c.to_vertex}  {c.time:.1f}s  {c.fuel:.1f}f" + ("  *" if c.recommended else "")
                text(surf, fit(line, 21, COL_W - 24), (x, y + i * 21), 21,
                     ACCENT if chosen else GOOD if c.recommended else TEXT, bold=chosen)

    def planner_line(self) -> str:
        """Which pickup planner the autopilot uses and what DP and greedy last chose."""
        mode = self.config["pickup_solver"]
        picks = getattr(self.me.strategy, "last_picks", None) if self.me else None
        if mode == "none" or picks is None:
            return f"Pickup planner: {mode.upper()}"
        return (f"Planner {mode.upper()}: DP {picks.dp.total_benefit:g} vs greedy {picks.greedy.total_benefit:g}, "
                f"{len(picks.recommended)} pickup(s)")

    def draw_events(self, surf) -> None:
        rect = self._events_rect()
        Panel(rect, "Event feed").draw(surf)
        y, limit = rect.y + 32, rect.bottom - 8
        for t, s, color in reversed(self.msgs[-40:]):
            for line in wrap(f"{t:5.1f}s {s}", 20, COL_W - 24)[:2]:
                if y + 20 > limit:
                    return
                text(surf, line, (rect.x + 12, y), 20, color)
                y += 20

    def draw_modal(self, surf) -> None:
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((5, 8, 14, 190))
        surf.blit(shade, (0, 0))
        if self.results is None:
            Panel((W // 2 - 190, 220, 380, 270), "Paused").draw(surf)
            return
        e = self.engine
        width = 760
        panel = Panel((W // 2 - width // 2, 120, width, 240 + 28 * len(self.results)), "")
        panel.draw(surf)
        text(surf, f"Race results - {self.title}", (W // 2, 150), 38, TEXT, "center", bold=True)
        win = self.results[0]
        text(surf, f"{e.racer(win.racer_id).name} wins" if win.finish_time is not None else "No finisher",
             (W // 2, 182), 24, GOOD, "center")
        rows, sw = [], []
        for res in self.results:
            r = e.racer(res.racer_id)
            when = f"{res.finish_time:.2f} s" if res.finish_time is not None else ("DNF" if r.status == DNF else "time limit")
            lap = f"{res.fastest_lap:.2f} s" if res.fastest_lap is not None else "-"
            pts = f"{res.points_awarded}" + (f" +{res.bonus_points}" if res.bonus_points else "")
            rows.append([f"{res.finish_position}  {r.name}", when, lap, str(r.fuel_stops), pts])
            sw.append(CAR_COLORS[r.id % len(CAR_COLORS)])
        draw_table(surf, (panel.rect.x + 20, 208, width - 40, 0), ["Pos  Racer", "Time", "Best lap", "Stops", "Points"],
                   rows, [230, 130, 130, 90, 140], sw, 28)

"""Championship flow (Project.md 2.2): briefing -> race -> results and standings -> ... -> champion.

`app.flow` holds a `ChampFlow` (the engine-side `Championship` plus the phase); this screen shows the current
phase, so leaving the screen never loses progress. The race itself is the ordinary RaceScreen with hooks.
"""
from __future__ import annotations

import math

import pygame

from smart_racing import config
from smart_racing.engine.championship import Championship
from smart_racing.engine.race import default_racers
from smart_racing.tracks.loader import load_builtin
from smart_racing.ui.app import H, W, Screen
from smart_racing.ui.render import CAR_COLORS, GraphView
from smart_racing.ui.screens.menu import nice
from smart_racing.ui.widgets import (ACCENT, BORDER, DIM, GOOD, PANEL, TEXT, WARN, Button, Cycle, Panel, draw_table, fit,
                                     text, wrap)


class ChampFlow:
    """The championship in progress and where the player is in it."""

    def __init__(self, settings) -> None:
        self.champ = Championship(laps=settings.laps, preset=settings.preset,
                                  racers=default_racers(settings.opponents), autopilot=settings.autopilot)
        self.phase = "briefing"            # briefing | results | champion
        self.last: list = []               # RaceResult list of the race just run

    @property
    def in_progress(self) -> bool:
        return bool(self.champ.results) and not self.champ.finished

    def finish(self, engine) -> None:
        """RaceScreen `on_finish` hook: record the race and move to the results phase."""
        if not any(engine is done for done in self.champ.races):
            self.last = self.champ.record(engine)
        self.phase = "results"

    def hint(self) -> str:
        table = self.champ.standings().items
        names, me = self.champ.names, next((e for e in table if self.champ.specs[e.racer_id].is_human), None)
        if not self.champ.results:
            return "First race: every racer starts on 0 points. Wins and the fastest lap decide the early order."
        lead = table[0]
        if me is None or me is lead:
            gap = lead.total_points - table[1].total_points if len(table) > 1 else 0
            return f"You lead on {lead.total_points} points, {gap} clear of {names[table[1].racer_id]}." if len(table) > 1 \
                else f"You lead on {lead.total_points} points."
        place = table.index(me) + 1
        return (f"{names[lead.racer_id]} leads on {lead.total_points}. You are P{place} on {me.total_points}, "
                f"{lead.total_points - me.total_points} behind.")


RACE_SHADES = [(70, 160, 255), (250, 190, 70), (90, 205, 125)]


def draw_points_chart(surf, champ, ranked, names, x: int, y: int, bar_w: int, rows: int = 8) -> None:
    """Horizontal bars of total points, split by race when `champ` has results (else one solid bar)."""
    top = max(1, max((e.total_points for e in ranked[:rows]), default=1))
    for i, e in enumerate(ranked[:rows]):
        yy = y + i * 28
        text(surf, fit(names[e.racer_id], 19, 92), (x, yy + 12), 19, TEXT, "midleft")
        bx = x + 100
        if champ is not None and champ.results:
            for k, res in enumerate(champ.results):
                w = int(bar_w * sum(r.points_awarded + r.bonus_points for r in res if r.racer_id == e.racer_id) / top)
                if w > 0:
                    pygame.draw.rect(surf, RACE_SHADES[k % 3], (bx, yy, w, 22))
                    pygame.draw.rect(surf, (14, 18, 26), (bx, yy, w, 22), 1)
                bx += w
        else:
            w = int(bar_w * e.total_points / top)
            pygame.draw.rect(surf, ACCENT, (bx, yy, w, 22))
            bx += w
        text(surf, str(e.total_points), (bx + 6, yy + 11), 20, TEXT, "midleft", bold=True)
    if champ is not None and champ.results:
        ly = y + min(rows, len(ranked)) * 28 + 8
        for k in range(len(champ.results)):
            pygame.draw.rect(surf, RACE_SHADES[k % 3], (x + k * 100, ly, 12, 12))
            text(surf, f"Race {k + 1}", (x + 18 + k * 100, ly + 6), 19, DIM, "midleft")


def standings_rows(champ, ranked, before: dict | None = None):
    rows, sw = [], []
    for place, e in enumerate(ranked, start=1):
        gain = f"+{e.total_points - before[e.racer_id]}" if before is not None else f"{e.wins}"
        lap = f"{e.best_fastest_lap:.2f}" if e.best_fastest_lap != math.inf else "-"
        rows.append([f"{place}  {champ.names[e.racer_id]}", str(e.total_points), gain, str(e.sum_of_finish_positions), lap])
        sw.append(CAR_COLORS[e.racer_id % len(CAR_COLORS)])
    return rows, sw


class ChampionshipScreen(Screen):
    def __init__(self, app, new: bool = False, **kw) -> None:
        super().__init__(app)
        if new or app.flow is None:
            app.flow = ChampFlow(app.settings)
        self.flow = app.flow
        self.champ = self.flow.champ
        self.confirm: tuple[str, object] | None = None
        self.phase = self.flow.phase
        self.view = None
        self.widgets: list = []
        self.modal_buttons: list = []
        n = self.champ.race_number
        if self.phase == "briefing":
            name = self.champ.circuits[n - 1]
            self.circuit = load_builtin(name)
            self.view = GraphView(self.circuit.graph, pygame.Rect(12, 100, 760, 560), 40)
            self.auto = Cycle((792, 600, 476, 40), "Your car", [True, False], 0 if self.champ.race_options["autopilot"] else 1,
                              self.set_auto, lambda v: "Autopilot on" if v else "You drive", 100)
            self.widgets = [self.auto, Button((792, 650, 230, 52), "Start race", self.start_race, color=(40, 120, 70)),
                            Button((1034, 650, 234, 52), "Back", self.leave)]
        elif self.phase == "results":
            last = n - 1 >= len(self.champ.circuits)
            self.widgets = [Button((782, 650, 240, 52), "Champion!" if last else "Next race", self.advance,
                                   color=(40, 120, 70)),
                            Button((1034, 650, 140, 52), "Dashboard", lambda: app.goto("dashboard")),
                            Button((1186, 650, 82, 52), "Menu", self.leave)]
        else:
            self.widgets = [Button((330, 640, 200, 52), "Dashboard", lambda: app.goto("dashboard"), color=(40, 120, 70)),
                            Button((540, 640, 200, 52), "Main menu", lambda: app.goto("menu")),
                            Button((750, 640, 200, 52), "New championship", lambda: app.goto("championship", new=True))]

    # --- actions ---------------------------------------------------------------------------------------
    def set_auto(self, v: bool) -> None:
        self.champ.race_options["autopilot"] = v
        self.app.settings.autopilot = v

    def start_race(self) -> None:
        engine = self.champ.next_race()
        self.app.goto("race", engine=engine, laps=self.champ.laps, on_finish=self.flow.finish,
                      on_continue=lambda: self.app.goto("championship"), continue_label="Results and standings",
                      on_restart=self.start_race)

    def advance(self) -> None:
        self.flow.phase = "champion" if self.champ.finished else "briefing"
        self.app.goto("championship")

    def leave(self) -> None:
        if self.flow.in_progress:
            self.ask("Leave the championship? Your progress is kept: choose Championship in the menu to resume.",
                     lambda: self.app.goto("menu"))
        else:
            self.app.goto("menu")

    def ask(self, message: str, yes) -> None:
        self.confirm = (message, yes)
        self.modal_buttons = [Button((W // 2 - 220, 400, 200, 50), "Leave", yes, color=(110, 40, 48)),
                              Button((W // 2 + 20, 400, 200, 50), "Stay", self.dismiss)]

    def dismiss(self) -> None:
        self.confirm, self.modal_buttons = None, []

    def on_escape(self) -> None:
        if self.confirm:
            self.dismiss()
        elif self.phase == "champion":
            self.app.goto("menu")
        else:
            self.leave()

    def all_widgets(self) -> list:
        return self.modal_buttons or self.widgets

    # --- drawing -------------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        surf.fill((14, 18, 26))
        getattr(self, "draw_" + self.phase)(surf)
        for w in self.widgets if not self.modal_buttons else []:
            w.draw(surf)
        if self.confirm:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((5, 8, 14, 200))
            surf.blit(shade, (0, 0))
            Panel((W // 2 - 280, 270, 560, 210)).draw(surf)
            for i, line in enumerate(wrap(self.confirm[0], 24, 520)):
                text(surf, line, (W // 2 - 260, 296 + i * 28), 24, TEXT)
            for b in self.modal_buttons:
                b.draw(surf)

    def draw_briefing(self, surf) -> None:
        c, n = self.champ, self.champ.race_number
        text(surf, f"Championship - race {n} of {len(c.circuits)}", (14, 24), 40, TEXT, bold=True)
        text(surf, nice(c.circuits[n - 1]), (14, 66), 30, ACCENT, bold=True)
        pygame.draw.rect(surf, (18, 23, 33), (12, 100, 760, 560), border_radius=8)
        pygame.draw.rect(surf, BORDER, (12, 100, 760, 560), 1, border_radius=8)
        self.view.draw(surf, False)
        g = self.circuit.graph
        side = Panel((782, 100, 486, 490), "Circuit briefing")
        side.draw(surf)
        facts = [f"{g.num_vertices} vertices, {g.num_edges} roads",
                 f"{len(g.checkpoints())} checkpoints to pass in order, then Finish",
                 f"{sum(e.is_shortcut for e in g.edges())} shortcuts, {sum(e.directed for e in g.edges())} one-way roads",
                 f"{sum(1 for v in g.vertices() if v.type == 'FuelStation')} fuel stations, "
                 f"{sum(1 for v in g.vertices() if v.type == 'NitroPickup')} nitro pickups",
                 f"{len(self.circuit.events)} scripted events (blockages, oil, speed limits, outages)",
                 f"{c.laps} lap{'s' if c.laps != 1 else ''}, cost preset {c.preset}"]
        y = 140
        for f in facts:
            text(surf, fit(f, 22, 460), (796, y), 22, TEXT)
            y += 28
        text(surf, "Standings", (796, y + 8), 22, ACCENT, bold=True)
        ranked = c.standings().items
        rows, sw = standings_rows(c, ranked)
        draw_table(surf, (796, y + 36, 458, 0), ["Racer", "Pts", "Wins", "PosSum", "Best lap"], rows, [150, 60, 60, 82, 98], sw)
        hy = y + 36 + (len(rows) + 1) * 22 + 20
        for i, line in enumerate(wrap(self.flow.hint(), 22, 460)):
            text(surf, line, (796, hy + i * 24), 22, WARN)

    def draw_results(self, surf) -> None:
        c, f = self.champ, self.flow
        k = len(c.results)
        engine, results = c.races[-1], c.results[-1]
        text(surf, f"Race {k} results - {nice(c.circuits[k - 1])}", (14, 24), 40, TEXT, bold=True)
        win = results[0]
        text(surf, f"{c.names[win.racer_id]} wins" if win.finish_time is not None else "No finisher",
             (14, 68), 28, GOOD)
        best = next((r for r in results if r.bonus_points), None)
        rows, sw = [], []
        for r in results:
            rs = engine.racer(r.racer_id)
            when = f"{r.finish_time:.2f} s" if r.finish_time is not None else ("DNF" if rs.status == "dnf" else "time limit")
            lap = f"{r.fastest_lap:.2f}" if r.fastest_lap is not None else "-"
            pts = f"{r.points_awarded}" + (f" +{r.bonus_points}" if r.bonus_points else "")
            rows.append([f"{r.finish_position}  {c.names[r.racer_id]}", when, lap + (" FL" if r is best else ""),
                         str(rs.fuel_stops), str(rs.reroutes), pts])
            sw.append(CAR_COLORS[r.racer_id % len(CAR_COLORS)])
        Panel((12, 100, 760, 170 + 28 * len(rows)), "Finish order").draw(surf)
        draw_table(surf, (26, 138, 732, 0), ["Pos  Racer", "Time", "Best lap", "Stops", "Reroutes", "Points"], rows,
                   [190, 120, 140, 70, 90, 110], sw, 28)
        text(surf, "FL = fastest lap of the race (+1 point, finishers only). Points 25, 18, 15, 12, 10, ... to finishers.",
             (26, 138 + (len(rows) + 1) * 28 + 16), 20, DIM)
        before = {e: 0 for e in c.entries}
        for res in c.results[:-1]:
            for r in res:
                before[r.racer_id] += r.points_awarded + r.bonus_points
        ranked = c.standings().items
        Panel((782, 100, 486, 170 + 28 * len(rows)), f"Standings after race {k}").draw(surf)
        srows, ssw = standings_rows(c, ranked, before)
        draw_table(surf, (796, 138, 458, 0), ["Racer", "Pts", "Gain", "PosSum", "Best lap"], srows, [150, 60, 66, 82, 92],
                   ssw, 28)
        for i, line in enumerate(wrap(f.hint(), 22, 460)):
            text(surf, line, (796, 138 + (len(srows) + 1) * 28 + 16 + i * 24), 22, WARN)
        py = 100 + 170 + 28 * len(rows) + 14
        Panel((12, py, 1256, 636 - py), "Points by race").draw(surf)
        draw_points_chart(surf, c, ranked, c.names, 30, py + 40, 700)

    def draw_champion(self, surf) -> None:
        c = self.champ
        champ = c.champion
        cx = W // 2
        text(surf, "CHAMPIONSHIP COMPLETE", (cx, 34), 34, ACCENT, "midtop", bold=True)
        # trophy
        pygame.draw.polygon(surf, WARN, [(cx - 44, 138), (cx + 44, 138), (cx + 30, 196), (cx - 30, 196)])
        pygame.draw.rect(surf, WARN, (cx - 8, 190, 16, 28))
        pygame.draw.rect(surf, WARN, (cx - 36, 218, 72, 12), border_radius=3)
        pygame.draw.circle(surf, WARN, (cx - 48, 150), 14, 5)
        pygame.draw.circle(surf, WARN, (cx + 48, 150), 14, 5)
        text(surf, c.names[champ.racer_id], (cx, 72), 56, TEXT, "midtop", bold=True)
        text(surf, f"{champ.total_points} points, {champ.wins} wins", (cx, 240), 28, GOOD, "midtop")
        ranked = c.standings().items
        rows, sw = standings_rows(c, ranked)
        Panel((330, 290, 620, 80 + 28 * len(rows)), "Final standings").draw(surf)
        draw_table(surf, (344, 328, 592, 0), ["Racer", "Pts", "Wins", "PosSum", "Best lap"], rows, [200, 80, 80, 110, 122], sw, 28)

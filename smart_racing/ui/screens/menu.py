"""Main Menu, Quick Race setup, Settings and Instructions."""
from __future__ import annotations

import pygame

from smart_racing import config
from smart_racing.tracks.loader import list_circuits, load_builtin
from smart_racing.ui.app import Screen
from smart_racing.ui.render import GraphView
from smart_racing.ui.widgets import ACCENT, BORDER, DIM, PANEL, TEXT, Button, Cycle, Panel, ScrollText, text, wrap

PRESETS = list(config.COST_PRESETS)


def nice(name: str) -> str:
    return name.replace("_", " ").title()


class Preview:
    """A circuit drawn small inside a rect (menu and setup screens)."""

    def __init__(self, rect) -> None:
        self.rect = pygame.Rect(rect)
        self.name = ""

    def draw(self, surf, name: str) -> None:
        if name != self.name:
            self.name = name
            self.circuit = load_builtin(name)
            self.view = GraphView(self.circuit.graph, self.rect, 40)
        self.view.draw(surf)


class MainMenu(Screen):
    ENTRIES = [("Championship", "championship"), ("Quick Race", "quick"), ("Track Explorer", "explorer"),
               ("Algorithm Lab", "lab"), ("Championship Dashboard", "dashboard"), ("Track Generator", "generator"),
               ("Instructions", "instructions"), ("Settings", "settings")]

    def __init__(self, app, **kw) -> None:
        super().__init__(app)
        for i, (label, target) in enumerate(self.ENTRIES):
            self.widgets.append(Button((80, 180 + i * 54, 380, 46), label, lambda t=target: self.open(t)))
        self.widgets.append(Button((80, 180 + len(self.ENTRIES) * 54, 380, 46), "Quit", app.quit, color=(110, 40, 48)))
        self.panel = Panel((520, 150, 700, 530))
        self.preview = Preview((530, 160, 680, 470))
        self.t = 0.0

    def open(self, target: str) -> None:
        if target == "championship":            # resume a championship in progress, otherwise start a new one
            flow = self.app.flow
            self.app.goto(target, new=flow is None or flow.champ.finished)
        else:
            self.app.goto(target)

    def on_escape(self) -> None:
        pass                                    # never quit by accident; the Quit button does it

    def update(self, dt: float) -> None:
        self.t += dt

    def draw(self, surf) -> None:
        super().draw(surf)
        text(surf, "SMART RACING", (80, 56), 66, TEXT, bold=True)
        text(surf, "CHAMPIONSHIP", (80, 108), 44, ACCENT, bold=True)
        text(surf, "12 hand-written algorithms power the game.",
             (80, 146), 21, DIM)
        names = list_circuits()
        name = names[int(self.t / 4) % len(names)]
        self.panel.draw(surf)
        self.preview.draw(surf, name)
        text(surf, nice(name), (self.panel.rect.centerx, self.panel.rect.bottom - 30), 30, TEXT, "center", bold=True)


class QuickRaceSetup(Screen):
    def __init__(self, app, circuit: str | None = None, **kw) -> None:
        super().__init__(app)
        s = app.settings
        if circuit:
            s.circuit = circuit
        x, w = 60, 520
        self.circuit = Cycle((x, 150, w, 44), "Circuit", list_circuits(), list_circuits().index(s.circuit),
                             self._set("circuit"), nice)
        self.laps = Cycle((x, 210, w, 44), "Laps", [1, 2, 3, 4, 5], s.laps - 1, self._set("laps"))
        self.preset = Cycle((x, 270, w, 44), "Cost preset", PRESETS, PRESETS.index(s.preset), self._set("preset"))
        self.opp = Cycle((x, 330, w, 44), "Opponents", list(range(0, config.MAX_RACERS)), s.opponents,
                         self._set("opponents"))
        self.auto = Cycle((x, 390, w, 44), "Autopilot", [True, False], 0 if s.autopilot else 1,
                          self._set("autopilot"), lambda v: "On (follows the planned route)" if v else "Off (you pick the roads)")
        self.widgets += [self.circuit, self.laps, self.preset, self.opp, self.auto,
                         Button((x, 470, w, 56), "Start Race", self.start, color=(40, 120, 70)),
                         Button((x, 540, 250, 48), "Explore this circuit",
                                lambda: app.goto("explorer", circuit=s.circuit)),
                         Button((x + 270, 540, 250, 48), "Back", lambda: app.goto("menu"))]
        self.panel = Panel((620, 150, 600, 520))
        self.preview = Preview((630, 160, 580, 400))

    def _set(self, field: str):
        return lambda v: setattr(self.app.settings, field, v)

    def start(self) -> None:
        s = self.app.settings
        self.app.goto("race", circuit=s.circuit, laps=s.laps, preset=s.preset, opponents=s.opponents,
                      autopilot=s.autopilot)

    def draw(self, surf) -> None:
        super().draw(surf)
        text(surf, "Quick Race", (60, 60), 48, TEXT, bold=True)
        text(surf, "Pick a circuit and rules, then start. Autopilot plans with A* and the knapsack and refuel DP.",
             (60, 108), 21, DIM)
        self.panel.draw(surf)
        name = self.app.settings.circuit
        self.preview.draw(surf, name)
        g = self.preview.circuit
        info = (f"{g.graph.num_vertices} vertices, {g.graph.num_edges} roads, "
                f"{len(g.graph.checkpoints())} checkpoints, {sum(e.is_shortcut for e in g.graph.edges())} shortcuts, "
                f"{len(g.events)} scripted events")
        text(surf, nice(name), (self.panel.rect.x + 16, self.panel.rect.bottom - 70), 30, TEXT, bold=True)
        text(surf, info, (self.panel.rect.x + 16, self.panel.rect.bottom - 36), 20, DIM)


class SettingsScreen(Screen):
    def __init__(self, app, **kw) -> None:
        super().__init__(app)
        s = app.settings
        x, w = 360, 560
        self.widgets += [
            Cycle((x, 180, w, 48), "Laps per race", [1, 2, 3, 4, 5], s.laps - 1, lambda v: setattr(s, "laps", v)),
            Cycle((x, 250, w, 48), "Default cost preset", PRESETS, PRESETS.index(s.preset),
                  lambda v: setattr(s, "preset", v)),
            Cycle((x, 320, w, 48), "Simulation speed", [1, 2, 4], [1, 2, 4].index(s.speed),
                  lambda v: setattr(s, "speed", v), lambda v: f"{v}x"),
            Cycle((x, 390, w, 48), "Show vertex and road ids", [True, False], 0 if s.show_ids else 1,
                  lambda v: setattr(s, "show_ids", v), lambda v: "Yes" if v else "No"),
            Button((x, 500, w, 52), "Back", lambda: app.goto("menu"))]

    def draw(self, surf) -> None:
        super().draw(surf)
        text(surf, "Settings", (360, 80), 48, TEXT, bold=True)
        text(surf, "Used by Quick Race, the Track Explorer and the Racing Screen.", (360, 132), 21, DIM)


INSTRUCTIONS = [
    ("GOAL", ACCENT),
    "Drive the checkpoints in order (1 to 10), then cross Finish: that is one lap. Finish all laps first. "
    "A checkpoint passed out of order does not count; you must come back to it.",
    "",
    ("RACING CONTROLS", ACCENT),
    "A  toggle autopilot (it follows the A* route and buys fuel with the refuel DP).",
    "1-9  or click a highlighted road: choose the next road at a junction. Each option shows its time and fuel.",
    "Space  fire nitro: 1.5x speed for 4 s, double fuel use. Up to 3 charges; collect more at nitro pickups.",
    "At a fuel station: R buy the recommended amount, F fill (max 40), Up/Down change the amount, Enter buy. "
    "Any purchase costs a 3 s stop.",
    "Tab  cycle speed 1x / 2x / 4x.   P or Esc  pause.   Esc after the race returns to the menu.",
    "A manual player who does nothing at a junction or station waits 3 s, then the recommended move is taken.",
    "",
    ("TRACK EXPLORER", ACCENT),
    "Click a vertex to set the start or destination (use the selector), click a road to block or unblock it. "
    "Tabs: BFS/DFS analysis, Dijkstra vs A*, route comparison (four weight presets side by side), resource plan.",
    "",
    ("ALGORITHM LAB, DASHBOARD, GENERATOR", ACCENT),
    "Algorithm Lab: pick any of the 12 algorithms, press Play or Step, step back, change speed. It replays the steps "
    "of the same functions the game calls. Championship runs three races; the Dashboard ranks the field with merge, "
    "quick and heap sort and shows heap-based top-k. Track Generator builds a circuit from a seed and shows every "
    "stage and every rejected candidate.",
    "",
    ("RULES IN BRIEF", ACCENT),
    "Tank 100 units; a road needs its full fuel to be entered. Stations sell up to 40 units per stop. "
    "Events block roads, spill oil, restrict speed, close stations and spawn nitro. Routes are recalculated at once.",
    "A racer that cannot find a route waits; after 60 s of waiting (or if nothing can change) it is DNF. "
    "Points 25, 18, 15, 12, 10, 8, 6, 4, 2, 1 to finishers, +1 for the fastest lap of a finisher.",
    "Roads: colour and width show difficulty (wide green = easy, thin red = hard). Dashed = shortcut. "
    "Arrow = one-way. Red cross = blocked. Halo = oil spill (purple) or speed limit (amber).",
]


class Instructions(Screen):
    def __init__(self, app, **kw) -> None:
        super().__init__(app)
        self.text = ScrollText((140, 140, 1000, 470), INSTRUCTIONS)
        self.widgets += [self.text, Button((140, 630, 200, 48), "Back", lambda: app.goto("menu"))]

    def draw(self, surf) -> None:
        super().draw(surf)
        text(surf, "Instructions", (140, 60), 48, TEXT, bold=True)
        text(surf, "Scroll with the mouse wheel.", (140, 108), 21, DIM)

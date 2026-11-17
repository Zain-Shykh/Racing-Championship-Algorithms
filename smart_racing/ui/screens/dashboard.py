"""Championship Dashboard (Project.md 2.1 screen 5, Act 5, Challenge 3).

Standings come from the gameplay sorts (`Championship.standings`: merge, quick, heap, one comparator) and the
live top-k from the size-k heap (`Championship.top`). Data: the championship in progress, a sample
championship run headless, or a large sample field of ChampionshipEntry records (so top-k vs n is visible).
"""
from __future__ import annotations

import math

import pygame

from smart_racing.algorithms.topk import top_k
from smart_racing.engine.championship import SORTS, Championship
from smart_racing.ui import lab_registry as L
from smart_racing.ui.app import Screen
from smart_racing.ui.render import CAR_COLORS
from smart_racing.ui.screens.championship import draw_points_chart
from smart_racing.ui.screens.menu import nice
from smart_racing.ui.widgets import (ACCENT, BORDER, DIM, GOOD, TEXT, WARN, Button, Cycle, Panel, draw_table, fit, text,
                                     wrap)

_sample: Championship | None = None


def sample_championship() -> Championship:
    """Three one-lap races run headless; cached because the result is deterministic."""
    global _sample
    if _sample is None:
        _sample = Championship(laps=1).run()
    return _sample


class Dashboard(Screen):
    def __init__(self, app, **kw) -> None:
        super().__init__(app)
        flow = app.flow
        self.modes = (["Current championship"] if flow is not None and flow.champ.results else []) + \
            ["Sample championship (headless)", "Large sample field (200)"]
        self.mode = Cycle((120, 8, 400, 40), "Data", self.modes, 0, lambda v: self.load(), caption_w=50)
        self.sort = Cycle((530, 8, 250, 40), "Sort", list(SORTS), 0, lambda v: self.refresh(), lambda v: f"{v} sort", 50)
        self.kcycle = Cycle((790, 8, 150, 40), "k", [1], 0, lambda v: self.refresh(), caption_w=30)
        self.race_cycle = Cycle((24, 394, 500, 34), "", [0], 0, lambda v: self.refresh(), caption_w=0)
        self.widgets = [Button((12, 8, 96, 40), "Back", lambda: app.goto("menu")), self.mode, self.sort, self.kcycle,
                        self.race_cycle]
        self.load()

    # --- data ----------------------------------------------------------------------------------------
    def load(self) -> None:
        mode = self.mode.value
        self.champ = None
        if mode.startswith("Current"):
            self.champ = self.app.flow.champ
        elif mode.startswith("Sample"):
            self.champ = sample_championship()
        if self.champ is not None:
            self.entries = list(self.champ.entries.values())
            self.names = self.champ.names
            self.race_cycle.options = list(range(len(self.champ.results))) or [0]
            self.race_cycle.index = len(self.race_cycle.options) - 1
            self.race_cycle.fmt = lambda i: (f"Race {i + 1}: {nice(self.champ.races[i].circuit.name)}"
                                            if self.champ.results else "no race yet")
        else:
            self.entries = L.sample_entries(200, 11)
            self.names = {e.racer_id: f"Racer {e.racer_id}" for e in self.entries}
        n = len(self.entries)
        self.kcycle.options = [v for v in (1, 2, 3, 5, 10, 25, 50, 100) if v < n] + [n]
        self.kcycle.index = min(len(self.kcycle.options) - 1, 2)
        self.refresh()

    def refresh(self) -> None:
        """Run the three sorts and the heap top-k on the current data (the counts come from the real calls)."""
        c, k = self.champ, self.kcycle.value
        self.ranks = {m: (c.standings(m) if c else SORTS[m](self.entries)) for m in SORTS}
        self.ranking = self.ranks[self.sort.value].items
        self.same = len({tuple(e.racer_id for e in r.items) for r in self.ranks.values()}) == 1
        self.top = c.top(k) if c else top_k(self.entries, k)

    def all_widgets(self) -> list:
        return self.widgets if self.champ is not None and self.champ.results else self.widgets[:-1]

    # --- drawing -----------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        surf.fill((14, 18, 26))
        text(surf, "Championship Dashboard", (950, 28), 28, TEXT, "midleft", bold=True)
        n = len(self.entries)
        shown = self.ranking[:8]
        Panel((12, 56, 520, 300), f"Standings ({self.sort.value} sort, n = {n})").draw(surf)
        rows, sw = [], []
        for place, e in enumerate(shown, start=1):
            lap = f"{e.best_fastest_lap:.2f}" if e.best_fastest_lap != math.inf else "-"
            rows.append([f"{place}  {self.names[e.racer_id]}", str(e.total_points), str(e.wins),
                         str(e.sum_of_finish_positions), lap])
            sw.append(CAR_COLORS[e.racer_id % len(CAR_COLORS)])
        draw_table(surf, (24, 92, 496, 0), ["Racer", "Points", "Wins", "PosSum", "Best lap"], rows, [170, 80, 70, 84, 92], sw, 24)
        if n > len(shown):
            text(surf, f"... top {len(shown)} of {n} shown", (26, 92 + (len(rows) + 1) * 24 + 8), 19, DIM)
        self.draw_results(surf)
        self.draw_compare(surf)
        self.draw_topk(surf)
        self.draw_chart(surf)
        self.draw_stats(surf)
        for w in self.all_widgets():
            w.draw(surf)

    def draw_results(self, surf) -> None:
        Panel((12, 364, 520, 348), "Race results").draw(surf)
        c = self.champ
        if c is None or not c.results:
            text(surf, "No race data: this is a sample field of records.", (26, 404), 21, DIM)
            return
        i = self.race_cycle.value
        res, eng = c.results[i], c.races[i]
        rows, sw = [], []
        for r in res:
            when = f"{r.finish_time:.1f}" if r.finish_time is not None else "DNF"
            lap = f"{r.fastest_lap:.1f}" if r.fastest_lap is not None else "-"
            rows.append([f"{r.finish_position}  {c.names[r.racer_id]}", when, lap, f"{r.points_awarded}" +
                         (f"+{r.bonus_points}" if r.bonus_points else "")])
            sw.append(CAR_COLORS[r.racer_id % len(CAR_COLORS)])
        draw_table(surf, (24, 436, 496, 0), ["Pos  Racer", "Time s", "Best lap", "Points"], rows, [190, 100, 100, 96], sw, 26)
        text(surf, f"{eng.laps} lap{'s' if eng.laps != 1 else ''}, {len(eng.feed)} track events, clock {eng.clock:.1f} s", (26, 436 + (len(rows) + 1) * 26 + 10),
             20, DIM)

    def draw_compare(self, surf) -> None:
        Panel((542, 56, 360, 300), "Three sorts, one ranking").draw(surf)
        n = len(self.entries)
        y = 92
        for m, r in self.ranks.items():
            on = m == self.sort.value
            text(surf, f"{m.capitalize()} sort", (556, y), 24, ACCENT if on else TEXT, bold=on)
            text(surf, f"{r.comparisons}", (888, y), 26, TEXT, "topright", bold=True)
            text(surf, "comparisons", (888, y + 24), 17, DIM, "topright")
            y += 50
        text(surf, ("Identical ranking: YES" if self.same else "Rankings DIFFER"), (556, y), 24, GOOD if self.same else (240, 90, 90),
             bold=True)
        note = (f"All three use one comparator (points, wins, position sum, best lap, id), so the order is a total "
                f"order and cannot differ. Only the work differs. n = {n}; n log2 n = {n * math.log2(max(n, 2)):.0f}.")
        for i, line in enumerate(wrap(note, 19, 330)):
            text(surf, line, (556, y + 28 + i * 20), 19, DIM)

    def draw_topk(self, surf) -> None:
        Panel((542, 364, 360, 348), "Live top-k (heap)").draw(surf)
        n, k = len(self.entries), self.kcycle.value
        full = self.ranks["merge"]
        t = self.top
        rows = [[f"{i}  {self.names[e.racer_id]}", str(e.total_points)] for i, e in enumerate(t.items[:8], start=1)]
        draw_table(surf, (554, 400, 336, 0), ["Top " + str(min(k, n)), "Points"], rows, [236, 100], None, 22)
        y = 400 + (len(rows) + 1) * 22 + 10
        text(surf, f"Heap top-k: {t.comparisons} comparisons, {t.heap_ops} heap ops", (556, y), 20, GOOD, bold=True)
        text(surf, f"Full merge sort: {full.comparisons} comparisons", (556, y + 24), 20, WARN, bold=True)
        agree = [e.racer_id for e in t.items] == [e.racer_id for e in full.items[:k]]
        text(surf, "Same leaders as the full sort: " + ("yes" if agree else "NO"), (556, y + 48), 20, TEXT)
        note = (f"k = {k}, n = {n}. Top-k costs about n log2 k, a full sort n log2 n. "
                + ("k is a small part of n, so the heap does far less work. " if k * 4 <= n else
                   "k is close to n, so the saving is small and k = n is a full sort. "))
        for i, line in enumerate(wrap(note, 19, 332)):
            text(surf, line, (556, y + 78 + i * 20), 19, DIM)

    def draw_chart(self, surf) -> None:
        Panel((912, 56, 356, 300), "Points by race").draw(surf)
        draw_points_chart(surf, self.champ, self.ranking, self.names, 926, 94, 150)

    def draw_stats(self, surf) -> None:
        Panel((912, 364, 356, 348), "Per-racer statistics").draw(surf)
        c = self.champ
        if c is None or not c.races:
            text(surf, "No race data for a sample field.", (926, 404), 21, DIM)
            return
        rows, sw = [], []
        for e in self.ranking:
            stops = sum(eng.racer(e.racer_id).fuel_stops for eng in c.races)
            rer = sum(eng.racer(e.racer_id).reroutes for eng in c.races)
            lap = f"{e.best_fastest_lap:.1f}" if e.best_fastest_lap != math.inf else "-"
            rows.append([c.names[e.racer_id], str(e.wins), str(e.sum_of_finish_positions), lap, str(stops), str(rer)])
            sw.append(CAR_COLORS[e.racer_id % len(CAR_COLORS)])
        draw_table(surf, (922, 400, 342, 0), ["Racer", "W", "PS", "Best", "Stp", "Rr"], rows,
                   [114, 32, 38, 56, 44, 40], sw, 24)
        text(surf, "W wins, PS position sum, Stp fuel stops, Rr reroutes.", (926, 400 + (len(rows) + 1) * 24 + 10), 17, DIM)

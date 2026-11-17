"""Track Explorer / Route Planner (Project.md 2.1 screen 2, Acts 1 to 3).

Every number shown comes from a call into smart_racing.algorithms or smart_racing.engine; this file only
lays results out. Each tab has a default analysis that runs when the tab opens, and a stored analysis
(the last button pressed) that is re-run whenever the start, destination, preset, circuit or a road changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pygame

from smart_racing import config
from smart_racing.algorithms.bfs import bfs
from smart_racing.algorithms.dfs import connected_components, dead_ends, dfs, enumerate_paths, find_cycle
from smart_racing.core.cost import distance_cost, make_cost_fn, time_cost
from smart_racing.core.graph import CHECKPOINT
from smart_racing.engine.resources import pickup_plan
from smart_racing.engine.routing import compare_presets, make_plan, plan_route, plan_through, race_targets
from smart_racing.tracks.loader import list_circuits, load_builtin
from smart_racing.ui.app import Screen
from smart_racing.ui.render import GraphView, Overlay, draw_legend
from smart_racing.ui.screens.menu import PRESETS, nice
from smart_racing.ui.widgets import (ACCENT, BAD, BORDER, DIM, GOOD, PANEL, ROUTE_COLORS, TEXT, WARN, Button, Cycle,
                                     Panel, ScrollText, Tabs, draw_table, fit, text)

VIEW = pygame.Rect(12, 56, 760, 520)
RIGHT = pygame.Rect(782, 56, 486, 656)
TABS = ["Reach", "Routes", "Compare", "Resources"]
CONTENT_Y = 244                    # first pixel below the tab bar's buttons row
START_COLOR, DEST_COLOR = GOOD, BAD


@dataclass
class Result:
    lines: list = field(default_factory=list)
    overlays: list = field(default_factory=list)
    rings: dict = field(default_factory=dict)
    table: tuple | None = None             # (header, rows, widths, swatches)


def fmt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


class Explorer(Screen):
    def __init__(self, app, circuit: str | None = None, **kw) -> None:
        super().__init__(app)
        self.tab = "Reach"
        self.res: dict[str, Result] = {}
        self.again: dict[str, Callable[[], Result]] = {}
        self.alt_index = 0
        self.hover_text = "Hover a vertex or road for details."
        names = list_circuits()
        self.names = names
        self.back = Button((12, 8, 96, 40), "Back", lambda: app.goto("menu"))
        self.circuit_cycle = Cycle((330, 8, 330, 40), "Circuit", names, names.index(circuit or app.settings.circuit),
                                   lambda v: self.load(v), nice, 70)
        self.preset_cycle = Cycle((680, 8, 330, 40), "Cost preset", PRESETS, PRESETS.index(app.settings.preset),
                                  lambda v: self._preset(v), caption_w=100)
        self.common = [self.back, self.circuit_cycle, self.preset_cycle,
                       Button((1020, 8, 114, 40), "Reset roads", lambda: self.load(self.name)),
                       Button((1142, 8, 126, 40), "Start race", lambda: app.goto("quick", circuit=self.name),
                              color=(40, 120, 70))]
        self.pick = Cycle((RIGHT.x, 62, RIGHT.w, 36), "Click a vertex to set", ["Start", "Destination"], 0,
                          None, caption_w=190)
        self.tabs = Tabs((RIGHT.x, 156, RIGHT.w, 34), TABS, 0, self._tab)
        self.text = ScrollText((RIGHT.x, CONTENT_Y, RIGHT.w, RIGHT.bottom - CONTENT_Y))
        self.scope = Cycle((RIGHT.x, 198, 330, 36), "Scope", ["Selected vertices", "Full lap"], 0,
                           lambda v: self.rerun(), caption_w=60)
        self.mode = Cycle((RIGHT.x, 198, RIGHT.w, 36), "", ["Candidate routes (selected vertices)",
                                                             "Cost presets (full lap)"], 0, lambda v: self.rerun())
        self.fuel = Cycle((RIGHT.x, 198, 186, 36), "Fuel", [100, 75, 50, 35, 25], 2,
                          lambda v: self.rerun(), caption_w=50)
        self.budget = Cycle((RIGHT.x + 192, 198, 180, 36), "Detour", [6.0, 12.0, 20.0], 0,
                            lambda v: self.rerun(), lambda v: f"{v:g} s", 64)
        self.tab_widgets = {
            "Reach": [Button((RIGHT.x, 198, 100, 36), "Run BFS", lambda: self.run("Reach", self.bfs_result)),
                      Button((RIGHT.x + 108, 198, 100, 36), "Run DFS", lambda: self.run("Reach", self.dfs_result)),
                      Button((RIGHT.x + 216, 198, 270, 36), "Next alternative route", self.next_alt)],
            "Routes": [self.scope, Button((RIGHT.x + 340, 198, 146, 36), "Run both",
                                          lambda: self.run("Routes", self.routes_result))],
            "Compare": [self.mode],
            "Resources": [self.fuel, self.budget, Button((RIGHT.x + 378, 198, 108, 36), "Recommend",
                                            lambda: self.run("Resources", self.resources_result))]}
        self.defaults = {"Reach": self.bfs_result, "Routes": self.routes_result,
                         "Compare": self.compare_result, "Resources": self.resources_result}
        self.panel = Panel(RIGHT)
        self.load(circuit or app.settings.circuit)

    # --- state ---------------------------------------------------------------------------
    def load(self, name: str) -> None:
        self.name = name
        self.circuit = load_builtin(name)
        self.g = self.circuit.graph
        self.view = GraphView(self.g, VIEW)
        self.src, self.dst = self.g.start.id, self.g.finish.id
        self.alt_index = 0
        if self.circuit_cycle.value != name:
            self.circuit_cycle.set_value(name)
        self.pick.set_value("Start")
        self.invalidate()

    @property
    def preset(self) -> str:
        return self.preset_cycle.value

    def _preset(self, value: str) -> None:
        self.app.settings.preset = value
        self.invalidate()

    def _tab(self, name: str) -> None:
        self.tab = name
        self.ensure()

    def all_widgets(self) -> list:
        return self.common + [self.pick, self.tabs, self.text] + self.tab_widgets[self.tab]

    def invalidate(self) -> None:
        """The graph or the selection changed: drop every result and recompute the visible tab."""
        self.res.clear()
        self.ensure()

    def rerun(self) -> None:
        self.res.pop(self.tab, None)
        self.ensure()

    def run(self, tab: str, fn: Callable[[], Result]) -> None:
        self.again[tab] = fn
        self.rerun()

    def ensure(self) -> None:
        if self.tab not in self.res:
            self.res[self.tab] = self.again.get(self.tab, self.defaults[self.tab])()
        r = self.res[self.tab]
        top = CONTENT_Y + (draw_table_height(r.table) + 6 if r.table else 0)
        self.text.rect = pygame.Rect(RIGHT.x, top, RIGHT.w, RIGHT.bottom - top)
        self.text.offset = 0
        self.text.set_lines(r.lines)

    def next_alt(self) -> None:
        self.alt_index += 1
        self.run("Reach", self.dfs_result)

    # --- vertex helpers ------------------------------------------------------------------
    def vlabel(self, v: int) -> str:
        vert = self.g.vertex(v)
        extra = f" CP{vert.checkpoint_order}" if vert.type == CHECKPOINT else f" {vert.type}"
        return f"v{v}{extra}"

    def route_text(self, vertices: list[int], limit: int = 40) -> str:
        shown = vertices if len(vertices) <= limit else vertices[:limit] + ["..."]
        return " ".join(str(v) for v in shown)

    def unreachable(self, a: int, b: int) -> str:
        return f"UNREACHABLE: no open route from v{a} to v{b} (blocked roads or one-way roads cut it off)."

    # --- Reach tab: BFS and DFS ---------------------------------------------------------------
    def bfs_result(self) -> Result:
        g, res = self.g, Result()
        full, one = bfs(g, self.src), bfs(g, self.src, self.dst)
        cps = g.checkpoints()
        hit = [c.checkpoint_order for c in cps if c.id in full.dist]
        miss = [c.checkpoint_order for c in cps if c.id not in full.dist]
        res.rings = {v: BAD for v in g.vertex_ids() if v not in full.dist}      # ringed red = not reachable
        res.lines = [
            ("BFS from " + self.vlabel(self.src), ACCENT),
            f"Reachable vertices: {len(full.dist)} of {g.num_vertices}  (visited {full.visited}, "
            f"edges examined {full.edges_examined})",
            (f"Reachable checkpoints: {len(hit)} of {len(cps)}" + (f"  {hit}" if hit else ""), GOOD if not miss else WARN),
            (f"Unreachable checkpoints: {miss}" if miss else "Unreachable checkpoints: none", BAD if miss else DIM),
            ""]
        if one.found:
            edges = one.edge_path
            plan = make_plan(g, one.path, edges, self.preset, "bfs")
            res.overlays = [Overlay(edges, ROUTE_COLORS[0], 6)]
            res.lines += [(f"Minimum-edge path to {self.vlabel(self.dst)}: {len(edges)} roads", ACCENT),
                          "  vertices: " + self.route_text(one.path),
                          f"  distance {fmt(plan.distance, 0)}, time {fmt(plan.time, 1)} s, fuel {fmt(plan.fuel, 1)}",
                          "  BFS minimises the number of roads, not distance, time or cost."]
        else:
            res.lines += [(self.unreachable(self.src, self.dst), BAD)]
        return res

    def dfs_result(self) -> Result:
        g, res = self.g, Result()
        d = dfs(g, self.src)
        cyc, comps, dead = find_cycle(g), connected_components(g), dead_ends(g)
        res.rings = {v: (190, 100, 235) for v in dead.dead_ends}
        res.lines = [
            ("DFS from " + self.vlabel(self.src), ACCENT),
            f"Traversal order ({d.visited} vertices, {d.edges_examined} edges examined):",
            "  " + self.route_text(d.order, 60),
            (f"Cycle: found, {len(cyc.cycle) - 1} roads: " + self.route_text(cyc.cycle, 20) if cyc.has_cycle
             else "Cycle: none", GOOD if cyc.has_cycle else WARN),
            f"Connected components: {len(comps.components)}  (sizes {[len(c) for c in comps.components]})",
            (f"Dead ends: {dead.dead_ends}" if dead.dead_ends else "Dead ends: none", (190, 130, 230)),
            ""]
        main = plan_through(g, self.src, [self.dst], self.preset, "astar")
        if not main.found:
            res.lines += [(self.unreachable(self.src, self.dst), BAD)]
            return res
        alts = enumerate_paths(g, self.src, self.dst, exclude=main.edges)
        res.lines += [
            (f"Alternative routes {self.vlabel(self.src)} to {self.vlabel(self.dst)}", ACCENT),
            f"Limits: at most {config.ALT_ROUTE_LIMIT} routes, {config.ALT_PATH_MAX_EDGES} roads each. "
            f"Found {len(alts.paths)}; route limit hit: {'yes' if alts.route_limit_hit else 'no'}; "
            f"length limit hit: {'yes' if alts.length_limit_hit else 'no'}.",
            f"Main route (A*, {self.preset}, white): {len(main.edges)} roads, cost {fmt(main.cost, 3)}"]
        res.overlays = [Overlay(main.edges, ROUTE_COLORS[2], 6, -3)]
        if alts.paths:
            self.alt_index %= len(alts.paths)
            for i, edges in enumerate(alts.edge_paths):
                plan = make_plan(g, alts.paths[i], edges, self.preset, "dfs")
                mark = ">" if i == self.alt_index else " "
                res.lines.append((f"{mark} #{i + 1}: {len(edges)} roads, distance {fmt(plan.distance, 0)}, "
                                  f"time {fmt(plan.time, 1)} s, cost {fmt(plan.cost, 3)}",
                                  ROUTE_COLORS[0] if i == self.alt_index else TEXT))
            res.overlays.append(Overlay(alts.edge_paths[self.alt_index], ROUTE_COLORS[0], 6, 3))
        else:
            res.lines.append(("No alternative route within the limits.", WARN))
        return res

    # --- Routes tab: Dijkstra vs A* ---------------------------------------------------------
    def plans(self, targets: list[int], source: int) -> dict:
        return {a: plan_through(self.g, source, targets, self.preset, a) for a in ("dijkstra", "astar")}

    def routes_result(self) -> Result:
        g, res = self.g, Result()
        lap = self.scope.value == "Full lap"
        source = g.start.id if lap else self.src
        targets = race_targets(g, 1, 1) if lap else [self.dst]
        plans = self.plans(targets, source)
        dj, ast = plans["dijkstra"], plans["astar"]
        what = "Full lap: Start, checkpoints 1 to 10 in order, Finish" if lap else \
            f"{self.vlabel(source)} to {self.vlabel(self.dst)}"
        res.lines = [(f"{what}  [{self.preset}]", ACCENT)]
        if not dj.found or not ast.found:
            bad = dj if not dj.found else ast
            res.lines += [(f"UNREACHABLE: no route to v{bad.failed_target} (blocked roads or one-way roads).", BAD),
                          f"The part found before it has {len(bad.edges)} roads."]
            return res
        rows = [("Roads", len(dj.edges), len(ast.edges)), ("Distance", fmt(dj.distance, 1), fmt(ast.distance, 1)),
                ("Est. time (s)", fmt(dj.time, 2), fmt(ast.time, 2)), ("Fuel", fmt(dj.fuel, 2), fmt(ast.fuel, 2)),
                ("Scalar cost", fmt(dj.cost, 4), fmt(ast.cost, 4)), ("Expanded", dj.expanded, ast.expanded),
                ("Relaxed", dj.relaxed, ast.relaxed), ("Heap ops", dj.heap_ops, ast.heap_ops),
                ("Edges examined", dj.edges_examined, ast.edges_examined)]
        res.table = (["", "Dijkstra", "A*"], [[a, str(b), str(c)] for a, b, c in rows], [196, 140, 140], None)
        res.overlays = [Overlay(dj.edges, ROUTE_COLORS[0], 5, -3), Overlay(ast.edges, ROUTE_COLORS[1], 5, 3)]
        same = abs(dj.cost - ast.cost) < 1e-9
        verdict = ("same optimal cost" if same else "COSTS DIFFER") + "; A* expanded " + (
            f"{dj.expanded - ast.expanded} fewer" if ast.expanded < dj.expanded else
            "the same number of" if ast.expanded == dj.expanded else f"{ast.expanded - dj.expanded} more") + " vertices"
        res.lines += [("Map: cyan line = Dijkstra, magenta line = A*", ROUTE_COLORS[0]), (verdict, GOOD if same else BAD),
                      "Scalar cost = wD*D/100 + wT*T/10 + wF*F/10 + wR*R + wO*O under the selected preset.",
                      "Dijkstra path: " + self.route_text(dj.vertices, 36),
                      "A* path: " + self.route_text(ast.vertices, 36)]
        if lap:
            res.lines.append(f"Search legs: {len(ast.legs)} (one per mandatory vertex, order preserved).")
        return res

    # --- Compare tab ---------------------------------------------------------------------------
    def compare_result(self) -> Result:
        g, res = self.g, Result()
        if self.mode.index == 0:
            return self.candidates(g, res)
        plans = compare_presets(g, g.start.id)
        names = list(plans)
        if not all(p.found for p in plans.values()):
            res.lines = [(f"UNREACHABLE: the full lap cannot be completed under the current roads "
                          f"(first missing target v{next(p for p in plans.values() if not p.found).failed_target}).", BAD)]
            return res
        base = set(plans["Balanced"].edges)
        rows, sw = [], []
        for i, name in enumerate(names):
            p = plans[name]
            rows.append([name, str(len(p.edges)), fmt(p.distance, 0), fmt(p.time, 1), fmt(p.fuel, 1),
                         fmt(p.cost, 3), str(len(set(p.edges) ^ base))])
            sw.append(ROUTE_COLORS[i])
            res.overlays.append(Overlay(p.edges, ROUTE_COLORS[i], 4, (i - 1.5) * 4))
        res.table = (["Preset", "Roads", "Dist", "Time", "Fuel", "Cost*", "Diff"], rows,
                     [118, 56, 56, 56, 56, 70, 48], sw)
        distinct = len({tuple(p.edges) for p in plans.values()})
        res.lines = [("Full lap, A*, each preset under its own weights", ACCENT),
                     f"{distinct} different routes among the 4 presets.",
                     "*Cost is measured with that preset's own weights, so costs of different rows are not comparable. "
                     "Diff = roads that differ from the Balanced route.",
                     "Speed prefers fast roads, Economy low fuel, Safety low difficulty and obstacles."]
        return res

    def candidates(self, g, res: Result) -> Result:
        cost = make_cost_fn(self.preset)
        picks = [(f"Min cost ({self.preset})", plan_through(g, self.src, [self.dst], self.preset, "astar")),
                 ("Min distance", plan_through(g, self.src, [self.dst], distance_cost, "dijkstra")),
                 ("Min time", plan_through(g, self.src, [self.dst], time_cost, "dijkstra"))]
        one = bfs(g, self.src, self.dst)
        if one.found:
            picks.append(("Min roads (BFS)", make_plan(g, one.path, one.edge_path, self.preset, "bfs")))
        res.lines = [(f"{self.vlabel(self.src)} to {self.vlabel(self.dst)}: candidate routes", ACCENT)]
        if not picks[0][1].found:
            res.lines.append((self.unreachable(self.src, self.dst), BAD))
            return res
        rows, sw, notes = [], [], []
        for i, (label, p) in enumerate(picks):
            p = make_plan(g, p.vertices, p.edges, cost, p.algorithm)       # every row measured with one cost
            same = next((picks[j][0] for j in range(i) if picks[j][1].edges == p.edges), None)
            rows.append([label, str(len(p.edges)), fmt(p.distance, 0), fmt(p.time, 1), fmt(p.fuel, 1), fmt(p.cost, 3)])
            sw.append(ROUTE_COLORS[i])
            if same:
                notes.append(f"{label} uses the same roads as {same}.")
            else:
                res.overlays.append(Overlay(p.edges, ROUTE_COLORS[i], 5, (i - 1.5) * 3.5))
        res.table = (["Route", "Roads", "Dist", "Time", "Fuel", f"Cost"], rows, [170, 56, 60, 60, 60, 70], sw)
        res.lines += [f"Cost column: the {self.preset} scalar cost of every route, so rows compare directly. "
                      "The Min cost row is the optimum (A*)."] + notes
        return res

    # --- Resources tab -------------------------------------------------------------------------------
    def resources_result(self) -> Result:
        g, res = self.g, Result()
        plan = plan_route(g, g.start.id, 1, 1, self.preset, "astar")
        res.lines = [(f"Resource plan for the full lap, A* route under {self.preset}", ACCENT)]
        if not plan.found:
            res.lines.append((f"UNREACHABLE: no lap route (target v{plan.failed_target}).", BAD))
            return res
        fuel = float(self.fuel.value)
        pk = pickup_plan(g, g.start.id, plan.edges, fuel, config.NITRO_START_CHARGES,
                         self.budget.value, "dp")
        res.lines += [f"Route: {len(plan.edges)} roads, distance {fmt(plan.distance, 0)}, time {fmt(plan.time, 1)} s, "
                      f"fuel needed {fmt(plan.fuel, 1)} (start with {fuel:g}, 1 nitro charge).", "",
                      ("Pickups (0/1 knapsack, budget B = " f"{pk.budget} tenths of a second of detour)", ACCENT)]
        for o in pk.options:
            res.lines.append(f"  {o.kind} at v{o.vertex}: cost c = {o.item.cost}, benefit v = {o.item.benefit:g}, "
                             f"detour {fmt(o.extra_time, 1)} s")
        if not pk.options:
            res.lines.append("  no optional pickup is on offer for this route")
        for label, r in (("DP", pk.dp), ("Greedy", pk.greedy)):
            res.lines.append(f"{label}: pick {[f'v{i}' for i in r.selected] or 'nothing'}, benefit {r.total_benefit:g}, "
                             f"cost {r.total_cost}/{pk.budget}, states {r.states}")
        gap = pk.dp.total_benefit - pk.greedy.total_benefit
        res.lines.append((f"DP beats greedy by {gap:g}." if gap > 0 else "Greedy matches the DP here.",
                          WARN if gap > 0 else DIM))
        res.lines.append((f"Recommended after the fuel check: {[f'v{i}' for i in pk.recommended] or 'none'}"
                          + (f" (dropped for fuel: {[f'v{i}' for i in pk.dropped]})" if pk.dropped else ""), GOOD))
        rf = pk.refuel.result
        res.lines += ["", ("Refuel plan (DP over the stations on the route)", ACCENT)]
        if rf.feasible:
            buys = [f"v{v} +{a}" for v, a in pk.refuel.purchases]
            res.lines.append(f"Feasible. Buy: {', '.join(buys) if buys else 'nothing needed'}; "
                             f"stop time {fmt(rf.total_stop_time, 1)} s; purchased {rf.total_purchased}; "
                             f"DP states {rf.states}.")
        else:
            res.lines.append((f"INFEASIBLE: {rf.reason or 'the tank cannot cover a leg'}", BAD))
        res.overlays = [Overlay(pk.edges, ROUTE_COLORS[0], 5)]
        res.rings = {v: WARN for v in pk.recommended}
        return res

    # --- input -------------------------------------------------------------------------------------------
    def handle_event(self, ev) -> bool:
        if ev.type == pygame.MOUSEMOTION and VIEW.collidepoint(ev.pos):
            self.hover_text = self.describe(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3) and VIEW.collidepoint(ev.pos):
            v = self.view.vertex_at(ev.pos)
            if v is not None:
                self.pick_vertex(v, ev.button == 3)
                return True
            e = self.view.edge_at(ev.pos)
            if e is not None and ev.button == 1:
                if not self.g.unblock_edge(e):
                    self.g.block_edge(e)
                self.invalidate()
                return True
        return super().handle_event(ev)

    def pick_vertex(self, v: int, as_destination: bool = False) -> None:
        if as_destination or self.pick.value == "Destination":
            self.dst = v
            self.pick.set_value("Start")
        else:
            self.src = v
            self.pick.set_value("Destination")
        self.alt_index = 0
        self.invalidate()

    def describe(self, pos) -> str:
        v = self.view.vertex_at(pos)
        if v is not None:
            vert = self.g.vertex(v)
            extra = f", checkpoint {vert.checkpoint_order}" if vert.checkpoint_order else ""
            state = "" if vert.active else " (inactive)"
            return f"Vertex {v}: {vert.type}{extra}{state}"
        e = self.view.edge_at(pos)
        if e is None:
            return "Hover a vertex or road for details."
        ed = self.g.edge(e)
        way = f"one-way {ed.src} to {ed.dst}" if ed.directed else f"{ed.src} - {ed.dst}"
        return (f"Road {e}: {way}{', shortcut' if ed.is_shortcut else ''}, dist {ed.distance:g}, "
                f"time {ed.effective_time:g}s, fuel {ed.effective_fuel:.1f}, difficulty {ed.effective_difficulty}, "
                f"{ed.status}")

    # --- drawing ---------------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        surf.fill((14, 18, 26))
        text(surf, "Track Explorer", (120, 28), 30, TEXT, "midleft", bold=True)
        pygame.draw.rect(surf, (18, 23, 33), VIEW, border_radius=8)
        pygame.draw.rect(surf, BORDER, VIEW, 1, border_radius=8)
        r = self.res.get(self.tab, Result())
        rings = dict(r.rings)
        rings[self.src] = START_COLOR
        rings[self.dst] = BAD if self.dst != self.src else START_COLOR
        tags = {self.src: "A"}
        tags[self.dst] = "A=B" if self.dst == self.src else "B"
        self.view.draw(surf, self.app.settings.show_ids, r.overlays, rings, tags=tags)
        pygame.draw.rect(surf, PANEL, (VIEW.x, VIEW.bottom + 4, VIEW.w, 28), border_radius=6)
        text(surf, fit(self.hover_text, 21, VIEW.w - 16), (VIEW.x + 8, VIEW.bottom + 18), 21, DIM, "midleft")
        draw_legend(surf, (VIEW.x, VIEW.bottom + 38, VIEW.w, RIGHT.bottom - VIEW.bottom - 38))
        self.panel.draw(surf)
        blocked = [e.id for e in self.g.edges() if e.blocked]
        text(surf, f"A  {self.vlabel(self.src)}", (RIGHT.x + 4, 106), 22, START_COLOR, bold=True)
        text(surf, f"B  {self.vlabel(self.dst)}", (RIGHT.x + 190, 106), 22, BAD, bold=True)
        text(surf, fit(f"Blocked: {blocked if blocked else 'none'}", 20, 210), (RIGHT.x + 4, 132), 20,
             WARN if blocked else DIM)
        text(surf, "Click road: block. Right-click: set B", (RIGHT.right - 8, 132), 19, DIM, "topright")
        for w in self.all_widgets():
            if w is not self.text:
                w.draw(surf)
        if r.table:
            header, rows, widths, sw = r.table
            draw_table(surf, (RIGHT.x, CONTENT_Y, sum(widths) + 12, 0), header, rows, widths, sw)
        self.text.draw(surf)


def draw_table_height(table) -> int:
    return (len(table[1]) + 1) * 22 + 4

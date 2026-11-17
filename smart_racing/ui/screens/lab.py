"""Algorithm Lab / Visualization (Project.md 2.1 screen 4).

The Lab never re-implements an algorithm: `lab_registry.record` calls the gameplay function with an
`observer`, stores the steps, and this screen replays them (play, pause, step, step back, restart, speed).
Counters are rebuilt from the replayed steps and, at the last step, are the result object's own counters.
"""
from __future__ import annotations

import pygame

from smart_racing.algorithms.knapsack import Item
from smart_racing.tracks.loader import list_circuits, load_builtin
from smart_racing.ui import lab_registry as L
from smart_racing.ui.app import Screen
from smart_racing.ui.render import GraphView, Overlay
from smart_racing.ui.screens.menu import PRESETS, nice
from smart_racing.ui.widgets import (ACCENT, BAD, BORDER, DIM, GOOD, PANEL, PANEL_HI, TEXT, WARN, Button, Cycle,
                                     Panel, ScrollText, blend, draw_bar, draw_table, fit, text)

VIEW = pygame.Rect(12, 56, 760, 440)
SPEEDS = [2, 5, 15, 40, 120, 400]
BLUE, TREE = (80, 130, 220), (0, 225, 255)
KNAPSACK_NAMES = list(L.KNAPSACK_PRESETS) + ["Track pickups (route, B=60)"]


class Lab(Screen):
    def __init__(self, app, algo: str = "BFS", circuit: str | None = None, **kw) -> None:
        super().__init__(app)
        self.name = algo if algo in L.ALGOS else "BFS"
        self.circuit_name = circuit or app.settings.circuit
        self.pos, self.acc, self.playing = 0, 0.0, False
        self.rec: L.Recording | None = None
        self.recs: list[L.Recording] = []
        self.src = self.dst = 0
        self.items: list[Item] = []
        self.budget = 0
        self.sel = 0
        self.k, self.gap = L.STATION_DEFAULTS[self.circuit_name]
        self.preset = app.settings.preset
        self.sort_data = "Sample (12 racers)"
        self.kn_preset = KNAPSACK_NAMES[0]
        self.pickup_note = ""
        mk = lambda *a, **k: Button(*a, **k)  # noqa: E731
        self.algo_cycle = Cycle((120, 8, 330, 40), "", list(L.ALGOS), list(L.ALGOS).index(self.name),
                                lambda v: self.pick(v), caption_w=0)
        self.circ_cycle = Cycle((460, 8, 300, 40), "Circuit", list_circuits(), list_circuits().index(self.circuit_name),
                                lambda v: self.set_circuit(v), nice, 80)
        self.common = [Button((12, 8, 96, 40), "Back", lambda: app.goto("menu")), self.algo_cycle, self.circ_cycle]
        self.play_btn = Button((110, 504, 104, 36), "Play", self.toggle)
        self.speed = Cycle((416, 504, 190, 36), "Speed", SPEEDS, 2, None, lambda v: f"{v}/s", 56)
        self.controls = [Button((12, 504, 90, 36), "Restart", self.restart), self.play_btn,
                         Button((222, 504, 90, 36), "< Step", lambda: self.step(-1)),
                         Button((320, 504, 90, 36), "Step >", lambda: self.step(1)), self.speed]
        # family options
        self.preset_cycle = Cycle((12, 548, 300, 36), "Cost", PRESETS, PRESETS.index(self.preset),
                                  lambda v: self.set("preset", v), caption_w=50)
        self.k_cycle = Cycle((12, 548, 220, 36), "Stations", [2, 3, 4, 5, 6], [2, 3, 4, 5, 6].index(self.k), lambda v: self.set("k", v), caption_w=84)
        self.gap_cycle = Cycle((240, 548, 220, 36), "Min gap", [3, 4, 5, 6, 7, 8], [3, 4, 5, 6, 7, 8].index(self.gap), lambda v: self.set("gap", v), caption_w=84)
        self.data_cycle = Cycle((12, 548, 360, 36), "Data", ["Sample (12 racers)", "Sample (24 racers)", "Championship standings"],
                                0, lambda v: self.set("sort_data", v), caption_w=50)
        self.kn_cycle = Cycle((12, 548, 330, 36), "Items", KNAPSACK_NAMES, 0, lambda v: self.set("kn_preset", v), caption_w=60)
        self.item_cycle = Cycle((350, 548, 170, 36), "Edit", [0], 0, lambda v: self.select(v), lambda i: f"item {chr(65 + i % 26)}", 44)
        self.edit = [mk((528, 548, 56, 36), "cost-", lambda: self.edit_item(-1, 0)), mk((590, 548, 56, 36), "cost+", lambda: self.edit_item(1, 0)),
                     mk((652, 548, 56, 36), "val-", lambda: self.edit_item(0, -1)), mk((714, 548, 56, 36), "val+", lambda: self.edit_item(0, 1)),
                     mk((12, 590, 90, 36), "B -", lambda: self.edit_budget(-1)), mk((110, 590, 90, 36), "B +", lambda: self.edit_budget(1)),
                     mk((208, 590, 120, 36), "Add item", self.add_item), mk((336, 590, 140, 36), "Remove item", self.remove_item)]
        self.about = ScrollText((790, 218, 472, 492))
        self.panel_about = Panel((782, 210, 486, 502), "About this algorithm")
        self.panel_counters = Panel((782, 56, 486, 146), "Live counters")
        self.rebuild()

    # --- widgets ---------------------------------------------------------------------------------
    @property
    def family(self) -> str:
        return L.ALGOS[self.name].family

    def options(self) -> list:
        return {"graph": [self.preset_cycle] if self.name in ("Dijkstra", "A*") else [],
                "knapsack": [self.kn_cycle, self.item_cycle] + self.edit,
                "backtrack": [self.k_cycle, self.gap_cycle], "sort": [self.data_cycle]}.get(self.family, [])

    def all_widgets(self) -> list:
        return self.common + self.controls + self.options() + [self.about]

    # --- state changes -----------------------------------------------------------------------------
    def pick(self, name: str) -> None:
        self.name = name
        self.rebuild()

    def set_circuit(self, name: str) -> None:
        self.circuit_name = name
        self.k, self.gap = L.STATION_DEFAULTS[name]
        self.k_cycle.set_value(self.k)
        self.gap_cycle.set_value(self.gap)
        self.rebuild()

    def set(self, field: str, value) -> None:
        setattr(self, field, value)
        self.rebuild(keep_items=field != "kn_preset")

    def select(self, i: int) -> None:
        self.sel = i

    def edit_item(self, dc: int, dv: int) -> None:
        if self.items:
            it = self.items[self.sel]
            self.items[self.sel] = Item(it.id, max(0, it.cost + dc), max(0, it.benefit + 2 * dv), it.name)
            self.rebuild(keep_items=True)

    def edit_budget(self, d: int) -> None:
        self.budget = max(0, min(80, self.budget + d * (5 if self.budget >= 20 else 1)))
        self.rebuild(keep_items=True)

    def add_item(self) -> None:
        if len(self.items) < 8:
            self.items.append(Item(len(self.items), 3, 10, chr(65 + len(self.items))))
            self.sel = len(self.items) - 1
            self.rebuild(keep_items=True)

    def remove_item(self) -> None:
        if len(self.items) > 1:
            self.items.pop(self.sel)
            self.items = [Item(i, it.cost, it.benefit, chr(65 + i)) for i, it in enumerate(self.items)]
            self.sel = min(self.sel, len(self.items) - 1)
            self.rebuild(keep_items=True)

    def restart(self) -> None:
        self.pos, self.acc, self.playing = 0, 0.0, False

    def toggle(self) -> None:
        if self.pos >= self.total:
            self.pos = 0
        self.playing = not self.playing

    def step(self, d: int) -> None:
        self.playing = False
        self.pos = max(0, min(self.total, self.pos + d))

    # --- recording --------------------------------------------------------------------------------------
    def rebuild(self, keep_items: bool = False) -> None:
        """Load a fresh circuit, build the data for the chosen algorithm and record it."""
        self.circuit = load_builtin(self.circuit_name)
        g = self.circuit.graph
        fam = self.family
        if fam in ("graph", "kruskal", "heap"):
            if not (g.has_vertex(self.src) and g.has_vertex(self.dst)) or self.src == self.dst or not hasattr(self, "_g_name") \
                    or self._g_name != self.circuit_name:
                self.src, self.dst = g.start.id, g.checkpoints()[5].id
            self._g_name = self.circuit_name
        if fam == "knapsack" and not (keep_items and self.items):
            self.load_items()
        self.initial = L._snapshot(g)
        self.recs = []
        if fam == "sort":
            data = {"entries": self.entries()}
            self.recs = [L.record(n, data) for n in L.SORTS]
            self.rec = self.recs[L.SORTS.index(self.name)]
        else:
            self.rec = L.record(self.name, self.data())
        self.pos, self.acc, self.playing = 0, 0.0, False
        self.view = GraphView(g, pygame.Rect(VIEW.x, VIEW.y, 470 if fam == "heap" else VIEW.w, VIEW.h - 26), 44)
        self.item_cycle.options = list(range(len(self.items))) or [0]
        self.item_cycle.index = min(self.sel, len(self.item_cycle.options) - 1)
        self.fill_about()

    def data(self) -> dict:
        g, fam = self.circuit.graph, self.family
        if fam == "graph":
            return dict(graph=g, src=self.src, dst=self.dst, preset=self.preset)
        if fam == "knapsack":
            return dict(items=list(self.items), budget=self.budget)
        if fam == "backtrack":
            return dict(circuit=self.circuit, k=self.k, gap=self.gap)
        if fam == "kruskal":
            return dict(graph=g)
        return dict(circuit=self.circuit)

    def entries(self) -> list:
        if self.sort_data.startswith("Championship"):
            flow = getattr(self.app, "flow", None)
            if flow is not None and flow.champ.results:
                return list(flow.champ.entries.values())
        return L.sample_entries(24 if "24" in self.sort_data else 12)

    def load_items(self) -> None:
        if self.kn_preset in L.KNAPSACK_PRESETS:
            rows, self.budget = L.KNAPSACK_PRESETS[self.kn_preset]
            self.items = L.items_from(rows)
        else:
            from smart_racing import config
            from smart_racing.engine.resources import pickup_plan
            from smart_racing.engine.routing import plan_route
            g = self.circuit.graph
            plan = plan_route(g, g.start.id, 1, 1, self.preset, "astar")
            pk = pickup_plan(g, g.start.id, plan.edges, 50.0, config.NITRO_START_CHARGES, config.PICKUP_DETOUR_BUDGET, "dp")
            self.items = [Item(i, o.item.cost, o.item.benefit, chr(65 + i)) for i, o in enumerate(pk.options)]
            self.pickup_note = "; ".join(f"{chr(65 + i)} = {o.kind} at v{o.vertex}" for i, o in enumerate(pk.options)) or \
                L.items_from(L.KNAPSACK_PRESETS[KNAPSACK_NAMES[0]][0])
            self.budget = pk.budget
        self.sel = 0

    @property
    def total(self) -> int:
        return max(len(r.steps) for r in (self.recs or [self.rec]))

    def fill_about(self) -> None:
        a = L.ALGOS[self.name]
        lines = [("What it does", ACCENT), a.explain, "", ("Complexity", ACCENT), a.complexity, "",
                 ("Role in the game", ACCENT), a.role, "", ("Data", ACCENT), self.data_line(), "",
                 ("Same code as gameplay", ACCENT),
                 f"Calls {a.fn.__module__}.{a.fn.__name__}: the function (or class) the game itself uses."]
        self.about.rect = pygame.Rect(790, 240, 472, 468)
        self.about.set_lines(lines)

    def data_line(self) -> str:
        g, fam = self.circuit.graph, self.family
        if fam == "graph":
            return (f"{nice(self.circuit_name)}: v{self.src} to v{self.dst}. Click a vertex for the destination, "
                    f"right-click for the start." + (f" Cost: {self.preset}." if self.name in ("Dijkstra", "A*") else ""))
        if fam == "knapsack":
            return (f"{len(self.items)} items, budget B = {self.budget}. Edit items and budget with the buttons."
                    + (f" {self.pickup_note}." if self.kn_preset not in L.KNAPSACK_PRESETS else ""))
        if fam == "backtrack":
            return (f"{self.k} fuel stations on the main route of {nice(self.circuit_name)}, at least {self.gap} "
                    f"positions apart, off checkpoints. Too many or too far apart: no solution exists.")
        if fam == "kruskal":
            return f"All {g.num_edges} roads of {nice(self.circuit_name)}, weighted by length."
        if fam == "heap":
            return f"The {len(self.circuit.events)} scripted events of {nice(self.circuit_name)}; one is cancelled."
        return f"{len(self.recs[0].data['entries'])} championship entries ordered by the championship comparator."

    # --- input / update ---------------------------------------------------------------------------------------
    def handle_event(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            k = {pygame.K_SPACE: self.toggle, pygame.K_RIGHT: lambda: self.step(1), pygame.K_LEFT: lambda: self.step(-1),
                 pygame.K_HOME: self.restart}.get(ev.key)
            if k:
                k()
                return True
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3) and self.family == "graph"
                and VIEW.collidepoint(ev.pos)):
            v = self.view.vertex_at(ev.pos)
            if v is not None:
                if ev.button == 3:
                    self.src = v
                else:
                    self.dst = v
                self.rebuild(keep_items=True)
                return True
        return super().handle_event(ev)

    def update(self, dt: float) -> None:
        if self.playing:
            self.acc += dt * self.speed.value
            n = int(self.acc)
            self.acc -= n
            self.pos = min(self.total, self.pos + n)
            if self.pos >= self.total:
                self.playing = False

    # --- drawing -----------------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        surf.fill((14, 18, 26))
        pygame.draw.rect(surf, (18, 23, 33), VIEW, border_radius=8)
        pygame.draw.rect(surf, BORDER, VIEW, 1, border_radius=8)
        self.play_btn.label = "Pause" if self.playing else "Play"
        getattr(self, "draw_" + self.family)(surf)
        for w in self.common + self.controls + self.options():
            w.draw(surf)
        bar = pygame.Rect(616, 508, 156, 28)
        draw_bar(surf, bar, self.pos / max(1, self.total), ACCENT, f"{self.pos} / {self.total}")
        self.draw_log(surf)
        self.panel_counters.draw(surf)
        self.draw_counters(surf)
        self.panel_about.draw(surf)
        self.about.draw(surf)
        if not self.options():
            text(surf, "Keys: Space play/pause, Left/Right step, Home restart.", (12, 556), 21, DIM)

    def draw_log(self, surf) -> None:
        box = pygame.Rect(12, 636, 760, 76)
        Panel(box).draw(surf)
        steps = self.rec.steps
        n = min(self.pos, len(steps))
        if n == 0:
            text(surf, "Press Play or Step to run the algorithm on this data.", (box.x + 12, box.y + 10), 22, DIM)
            return
        for i, idx in enumerate(range(max(0, n - 3), n)):
            newest = idx == n - 1
            line = f"{idx + 1:>4}  " + L.describe(self.name, steps[idx])
            text(surf, fit(line, 22 if newest else 20, box.w - 24), (box.x + 12, box.y + 8 + i * 23), 22 if newest else 20,
                 TEXT if newest else DIM, bold=newest)

    def draw_counters(self, surf) -> None:
        box = self.panel_counters.inner
        if self.family == "sort":
            for i, r in enumerate(self.recs):
                n = min(self.pos, len(r.steps))
                c = r.counters["comparisons"] if n >= len(r.steps) else L.live_counters(r.name, r.steps, n)["comparisons"]
                text(surf, r.name + " comparisons", (box.x, box.y + 4 + i * 30), 24, ACCENT if r.name == self.name else DIM)
                text(surf, str(c), (box.right - 10, box.y + 4 + i * 30), 26, TEXT, "topright", bold=True)
            return
        done = self.pos >= len(self.rec.steps)
        live = L.live_counters(self.name, self.rec.steps, self.pos)
        for i, (key, final) in enumerate(self.rec.counters.items()):
            value = final if done else live.get(key, "-")
            x, y = box.x + (i % 2) * 235, box.y + 2 + (i // 2) * 28
            text(surf, key.replace("_", " "), (x, y), 22, DIM)
            text(surf, f"{value:g}" if isinstance(value, float) else str(value), (x + 220, y), 24, TEXT, "topright", bold=True)
        if not done and any(k not in live for k in self.rec.counters):
            text(surf, "'-' counters are known when the run completes", (box.x, box.bottom - 16), 18, DIM)

    # graph searches -----------------------------------------------------------------------------------
    def draw_graph(self, surf) -> None:
        st = L.graph_state(self.name, self.rec.steps, self.pos)
        rings = {v: BLUE for v in st["visited"]}
        rings.update({v: WARN for v in st["frontier"]})
        if st["current"] is not None:
            rings[st["current"]] = (255, 255, 255)
        rings[self.src] = rings.get(self.src, GOOD) if st["current"] == self.src else GOOD
        if self.name != "DFS":
            rings[self.dst] = BAD
        ov = [Overlay(st["tree"], TREE, 3)]
        if st["examined"] is not None:
            ov.append(Overlay([st["examined"]], WARN, 8))
        if st["path"]:
            ov.append(Overlay(st["path"], GOOD, 8))
        tags = {v: s for v, s in st["frontier"].items() if s}
        tags[self.src] = "A"
        if self.name != "DFS":
            tags[self.dst] = "B"
        self.view.draw(surf, self.app.settings.show_ids, ov, rings, tags=tags)
        text(surf, "blue ring visited, yellow frontier, white current, cyan tree, green final path",
             (VIEW.x + 10, VIEW.bottom - 18), 19, DIM, "midleft")

    # Kruskal ---------------------------------------------------------------------------------------------------
    def draw_kruskal(self, surf) -> None:
        ok, no, cur = [], [], None
        for st in self.rec.steps[:self.pos]:
            if st["type"] == "edge":
                (ok if st["accepted"] else no).append(st["edge"])
                cur = st["edge"]
        ov = [Overlay(no, BAD, 3), Overlay(ok, GOOD, 7)] + ([Overlay([cur], WARN, 10, 0)] if cur is not None and self.pos < self.total else [])
        self.view.draw(surf, self.app.settings.show_ids, ov)
        text(surf, f"green = accepted ({len(ok)}), red = rejected ({len(no)}), yellow = road being tested",
             (VIEW.x + 10, VIEW.bottom - 18), 19, DIM, "midleft")

    # backtracking ------------------------------------------------------------------------------------------------
    def draw_backtrack(self, surf) -> None:
        route = L.station_problem(self.circuit, self.k, self.gap)["route"]
        placed, last = {}, None
        for st in self.rec.steps[:self.pos]:
            if st["type"] == "assign":
                placed[st["var"]] = st["value"]
            elif st["type"] == "backtrack":
                placed.pop(st["var"], None)
            last = st
        rings = {route[p]: GOOD for p in placed.values()}
        tags = {route[p]: f"S{v}" for v, p in placed.items()}
        if last and last["type"] in ("reject", "prune", "backtrack"):
            rings[route[last["value"]]] = BAD if last["type"] == "reject" else WARN
        self.view.draw(surf, self.app.settings.show_ids, [], rings, tags=tags)
        out = self.rec.result
        note = f"placed {len(placed)} of {self.k}"
        if self.pos >= self.total:
            note = "SOLVED: stations placed" if out.solved else "NO SOLUTION: every combination was tried and rejected"
        text(surf, note + "   green ring = placed, red = rejected, yellow = undone (backtrack)",
             (VIEW.x + 10, VIEW.bottom - 18), 19, GOOD if self.pos >= self.total and out.solved else DIM, "midleft")

    # knapsack -------------------------------------------------------------------------------------------------------
    def draw_knapsack(self, surf) -> None:
        steps, n = self.rec.steps[:self.pos], self.pos
        items, B = self.items, self.budget
        x0, y0 = VIEW.x + 10, VIEW.y + 10
        text(surf, f"Budget B = {B}", (x0, y0), 26, TEXT, bold=True)
        verdict = {st["item"]: st["picked"] for st in steps if st["type"] == "consider"}
        done = steps[-1] if steps and steps[-1]["type"] == "done" else None
        taken = set(done["selected"]) if done else set()
        rows, sw = [], []
        for it in items:
            status = ("taken" if it.id in taken else "-") if done else ""
            if self.name == "Greedy":
                status = ("picked" if verdict[it.id] else "rejected") if it.id in verdict else ("never (value 0)" if done else "")
            ratio = f"{it.benefit / it.cost:.2f}" if it.cost else "free"
            rows.append([f"{it.name}", str(it.cost), f"{it.benefit:g}", ratio, status])
            sw.append(GOOD if it.id in taken else None)
        draw_table(surf, (x0, y0 + 34, 330, 0), ["Item", "Cost", "Value", "v/c", "Result"], rows, [58, 52, 58, 62, 96], sw)
        ty = y0 + 34 + (len(items) + 1) * 22 + 20
        if self.name == "Greedy":
            self.draw_greedy(surf, steps, B, x0, ty)
        else:
            self.draw_dp(surf, steps, n, items, B, VIEW.x + 350, y0 + 8)
        other = "Greedy" if self.name == "Knapsack DP" else "Knapsack DP"
        res, _ = L.run(other, self.data())
        mine = self.rec.result
        text(surf, f"{self.name}: benefit {mine.total_benefit:g}   {other} (same data): benefit {res.total_benefit:g}",
             (VIEW.x + 10, VIEW.bottom - 18), 20, WARN if res.total_benefit != mine.total_benefit else DIM, "midleft")

    def draw_greedy(self, surf, steps, B, x, y) -> None:
        used = sum(st["cost"] for st in steps if st["type"] == "consider" and st["picked"])
        draw_bar(surf, (x, y, 330, 26), used / B if B else 0, GOOD, f"budget used {used} / {B}")
        order = [st for st in steps if st["type"] == "consider"]
        text(surf, "Order considered (best ratio first):", (x, y + 38), 21, ACCENT, bold=True)
        for i, st in enumerate(order[:9]):
            c = GOOD if st["picked"] else BAD
            text(surf, f"{i + 1}. item {chr(65 + st['item'] % 26)}: {'picked' if st['picked'] else 'rejected, does not fit'}",
                 (x, y + 64 + i * 24), 22, c)

    def draw_dp(self, surf, steps, n, items, B, x, y) -> None:
        cells = {(s["i"], s["b"]): s for s in steps if s["type"] == "cell"}
        trace = {(s["i"], s["b"]): s["taken"] for s in steps if s["type"] == "trace"}
        m = len(items)
        cw = max(9, min(44, (VIEW.right - x - 40) // (B + 2)))
        ch = max(18, min(30, (VIEW.h - 120) // (m + 2)))
        text(surf, "dp[i][b]: best benefit, first i items, budget b", (x, y), 20, DIM)
        gy = y + 26
        for b in range(B + 1):
            if cw >= 20 or b % 5 == 0:
                text(surf, str(b), (x + 36 + b * cw + cw // 2, gy + ch // 2), 17, DIM, "center")
        last = steps[-1] if steps and steps[-1]["type"] == "cell" else None
        for i in range(m + 1):
            ry = gy + (i + 1) * ch
            text(surf, "0" if i == 0 else items[i - 1].name, (x + 24, ry + ch // 2), 20, DIM, "center")
            for b in range(B + 1):
                r = pygame.Rect(x + 36 + b * cw, ry, cw - 1, ch - 1)
                s = cells.get((i, b))
                if i == 0:
                    val, fill = 0, (28, 36, 52)
                elif s is None:
                    pygame.draw.rect(surf, (20, 26, 38), r)
                    continue
                else:
                    val = s["value"]
                    fill = blend((28, 40, 60), (40, 150, 90) if s["take"] else (50, 90, 170), 0.65)
                pygame.draw.rect(surf, fill, r)
                if s is last and last is not None:
                    pygame.draw.rect(surf, WARN, r, 2)
                if (i, b) in trace:
                    pygame.draw.rect(surf, GOOD if trace[(i, b)] else BAD, r, 2)
                if cw >= 26:
                    text(surf, f"{val:g}", r.center, 19 if cw < 34 else 21, TEXT, "center")
        ly = gy + (m + 2) * ch + 10
        text(surf, "green: item taken, blue: skipped, yellow box: latest.", (x, ly), 19, DIM)
        text(surf, "outlined: traceback (green taken, red not taken).", (x, ly + 20), 19, DIM)
        text(surf, "dp[i][b] = max(dp[i-1][b], dp[i-1][b - c_i] + v_i)", (x, ly + 48), 22, TEXT)
        text(surf, "dp[0][b] = 0; the answer is dp[m][B].", (x, ly + 72), 20, DIM)

    # event heap -----------------------------------------------------------------------------------------------------------
    def draw_heap(self, surf) -> None:
        g = self.circuit.graph
        steps = self.rec.steps[:self.pos]
        L.restore_snapshot(g, steps[-1]["snapshot"] if steps else self.initial)
        last = steps[-1] if steps else None
        rings, ov = {}, []
        if last and last["event"] is not None:
            t = last["event"].target
            if last["event"].type in ("station_outage", "nitro_spawn") or (last["type"] == "expire" and g.has_vertex(t) and not g.has_edge(t)):
                rings[t] = WARN
            elif g.has_edge(t):
                ov.append(Overlay([t], WARN, 10))
        self.view.draw(surf, self.app.settings.show_ids, ov, rings)
        px = VIEW.x + 480
        text(surf, "Heap: pending events", (px, VIEW.y + 10), 22, ACCENT, bold=True)
        text(surf, "time  type  target  prio", (px, VIEW.y + 36), 19, DIM)
        pend = last["pending"] if last else []
        for i, (eid, typ, t, pr, target) in enumerate(pend[:15]):
            y = VIEW.y + 58 + i * 22
            cur = last is not None and last["event"] is not None and last["event"].event_id == eid
            if cur:
                pygame.draw.rect(surf, (70, 60, 20), (px - 4, y - 2, 280, 21), border_radius=4)
            name = typ.replace("_", " ")
            text(surf, fit(f"{t:5.1f} {name} @{target}", 20, 236), (px, y), 20, TEXT if i else GOOD)
            text(surf, str(pr), (px + 270, y), 20, DIM, "topright")
        if len(pend) > 15:
            text(surf, f"... {len(pend) - 15} more", (px, VIEW.y + 58 + 15 * 22), 19, DIM)
        if not pend:
            text(surf, "(empty)", (px, VIEW.y + 58), 20, DIM)
        text(surf, "top row = next to fire. Blocked/oil/speed effects shown on the map; yellow = event just handled.",
             (VIEW.x + 10, VIEW.bottom - 18), 19, DIM, "midleft")

    # sorts, side by side -----------------------------------------------------------------------------------------------------
    def draw_sort(self, surf) -> None:
        w = VIEW.w // 3
        for col, rec in enumerate(self.recs):
            box = pygame.Rect(VIEW.x + col * w + 4, VIEW.y + 6, w - 8, VIEW.h - 12)
            n = min(self.pos, len(rec.steps))
            mine = rec.name == self.name
            pygame.draw.rect(surf, PANEL_HI if mine else PANEL, box, border_radius=8)
            pygame.draw.rect(surf, ACCENT if mine else BORDER, box, 1, border_radius=8)
            comps = rec.counters["comparisons"] if n >= len(rec.steps) else L.live_counters(rec.name, rec.steps, n)["comparisons"]
            text(surf, rec.name, (box.centerx, box.y + 8), 26, TEXT, "midtop", bold=True)
            finished = n >= len(rec.steps)
            text(surf, f"{comps} comparisons" + ("  DONE" if finished else ""), (box.centerx, box.y + 36), 22,
                 GOOD if finished else WARN, "midtop")
            self.draw_bars(surf, rec, n, pygame.Rect(box.x + 6, box.y + 62, box.w - 12, box.h - 66))

    def draw_bars(self, surf, rec, n, box) -> None:
        entries = rec.data["entries"]
        steps = rec.steps[:n]
        arr, cmp_ids = list(entries), ()
        for st in steps:
            if st["type"] in ("pass", "partition"):
                arr = list(st["items"])
            elif st["type"] == "compare":
                cmp_ids = (st["a"].racer_id, st["b"].racer_id)
        extracted = [st["item"] for st in steps if st["type"] == "extract"]
        if rec.name == "Heap sort" and extracted:
            gone = {e.racer_id for e in extracted}
            arr = [e for e in entries if e.racer_id not in gone] + extracted[::-1]
        done = bool(steps) and steps[-1]["type"] == "done"
        if done:
            arr, cmp_ids = list(steps[-1]["items"]), ()
        top, m = max(1, max(e.total_points for e in entries)), len(arr)
        bw = max(6, (box.w - 8) // m)
        base = box.bottom - 78
        x0 = box.x + (box.w - bw * m) // 2
        for i, e in enumerate(arr):
            h = 4 + int((base - box.y - 70) * e.total_points / top)
            r = pygame.Rect(x0 + i * bw, base - h, bw - 2, h)
            sorted_part = bool(extracted) and rec.name == "Heap sort" and i >= m - len(extracted)
            color = WARN if e.racer_id in cmp_ids else GOOD if (done or sorted_part) else blend(BLUE, TEXT, 0.15)
            pygame.draw.rect(surf, color, r, border_radius=2)
            if bw >= 18:
                text(surf, str(e.racer_id), (r.centerx, base + 4), 18, TEXT, "midtop")
        note = "unsorted part in input order" if rec.name == "Heap sort" else "yellow: being compared"
        text(surf, "bar = points, label = racer id", (box.centerx, box.bottom - 52), 18, DIM, "midtop")
        text(surf, note, (box.centerx, box.bottom - 34), 18, DIM, "midtop")
        if done:
            ids = " ".join(str(e.racer_id) for e in arr[:9]) + (" .." if len(arr) > 9 else "")
            text(surf, fit("ranking: " + ids, 19, box.w - 8), (box.centerx, box.bottom - 17), 19, TEXT, "midtop")

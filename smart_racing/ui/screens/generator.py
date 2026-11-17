"""Track Generator view (Challenge 1): generate from a seed, step through the pipeline, see the validator
verdict and every rejected candidate with the reasons. Everything comes from `tracks.generator.generate`
and `tracks.validator.validate_circuit`; this file only lays the results out.
"""
from __future__ import annotations

from pathlib import Path

import pygame

from smart_racing import config
from smart_racing.tracks.generator import generate
from smart_racing.tracks.loader import route_edges, save_circuit
from smart_racing.tracks.validator import validate_circuit
from smart_racing.ui.app import Screen
from smart_racing.ui.render import GraphView, Overlay
from smart_racing.ui.widgets import (ACCENT, BAD, BORDER, DIM, GOOD, TEXT, WARN, Button, Panel, ScrollText, Tabs, fit,
                                     text)

SAVE_DIR = Path.home() / ".smart_racing"          # tests point this at a temporary folder
VIEW = pygame.Rect(12, 100, 760, 560)
RIGHT = pygame.Rect(782, 56, 486, 596)
DEMO_SEED = 29                                    # attempt 1 is rejected (fuel), attempt 2 accepted
STAGES = ["vertices", "candidates", "mst", "extras", "loop", "one_way", "placement"]
STAGE_TITLES = ["1 Vertices", "2 Candidates", "3 MST", "4 Extras", "5 Loop", "6 One-way", "7 Placement"]


class Generator(Screen):
    def __init__(self, app, seed: int = DEMO_SEED, **kw) -> None:
        super().__init__(app)
        self.seed, self.typed = seed, ""
        self.message = ""
        b = lambda x, w, label, fn, **k: Button((x, 8, w, 40), label, fn, **k)  # noqa: E731
        self.top = [b(12, 96, "Back", lambda: app.goto("menu")), b(120, 56, "-10", lambda: self.bump(-10)),
                    b(180, 50, "-1", lambda: self.bump(-1)), b(404, 50, "+1", lambda: self.bump(1)),
                    b(458, 56, "+10", lambda: self.bump(10)), b(522, 120, "Generate", self.generate, color=(40, 120, 70)),
                    b(650, 150, "Demo: seed 29", lambda: self.bump(DEMO_SEED - self.seed, True))]
        self.tabs = Tabs((12, 56, 760, 36), STAGE_TITLES, len(STAGES) - 1, lambda n: self.show(STAGE_TITLES.index(n)))
        self.text = ScrollText((RIGHT.x + 4, RIGHT.y + 30, RIGHT.w - 8, RIGHT.h - 34))
        self.actions = [Button((RIGHT.x, 664, 150, 46), "Save circuit", self.save),
                        Button((RIGHT.x + 168, 664, 150, 46), "Race on it", self.race, color=(40, 120, 70)),
                        Button((RIGHT.x + 336, 664, 150, 46), "Open in Explorer", self.explore)]
        self.widgets = self.top + [self.tabs, self.text] + self.actions
        self.generate()

    # --- actions -----------------------------------------------------------------------------------
    def bump(self, d: int, generate_now: bool = False) -> None:
        self.seed = max(0, self.seed + d)
        self.typed = ""
        if generate_now:
            self.generate()

    def generate(self) -> None:
        if self.typed:
            self.seed, self.typed = int(self.typed), ""
        self.circuit, self.report = generate(self.seed)
        self.message = ""
        for b in self.actions:
            b.enabled = self.circuit is not None
        self.verdict = validate_circuit(self.circuit) if self.circuit else None
        self.show(len(self.report.stages) - 1)
        self.tabs.index = self.stage

    def show(self, i: int) -> None:
        self.stage = min(i, len(self.report.stages) - 1)
        if not self.report.stages:
            return
        st = self.report.stages[self.stage]
        self.view = GraphView(st.graph, VIEW, 36)
        self.overlays = []
        if st.name == "extras":
            self.overlays = [Overlay(st.info["extras"], WARN, 6)]
        elif st.name == "loop":
            loop = st.info["loop"]
            self.overlays = [Overlay(route_edges(st.graph, loop + loop[:1]), GOOD, 6)]
        elif st.name == "one_way":
            self.overlays = [Overlay(st.info["one_way"], WARN, 6)]
        self.fill_text()

    def fill_text(self) -> None:
        r, st = self.report, self.report.stages[self.stage]
        lines = [(f"Seed {r.seed}: " + (f"accepted on attempt {r.attempts} of {config.GEN_MAX_ATTEMPTS}" if r.success
                                        else f"FAILED, all {r.attempts} attempts rejected"), GOOD if r.success else BAD)]
        lines += ["", (f"Rejected candidates: {len(r.rejected)}", WARN if r.rejected else DIM)]
        for rej in r.rejected:
            lines.append((f"Attempt {rej.attempt} rejected at {rej.stage}:", WARN))
            lines += [f"  {why}" for why in rej.reasons]
        if not r.rejected:
            lines.append("None for this seed. Seed 29 rejects attempt 1 because the fuel plan is infeasible.")
        lines += ["", (f"Stage {self.stage + 1}: {st.name}", ACCENT), st.description]
        info = st.info
        if st.name == "mst":
            lines += [f"Kruskal: {info['edges_examined']} roads examined, {info['comparisons']} sort comparisons, "
                      f"{info['finds']} finds, {info['unions']} unions, total length {info['total_weight']:.0f}."]
        elif st.name == "extras":
            lines += [f"Extra roads {info['extras']}; vertex {info['dead_end']} stays a dead end."]
        elif st.name == "one_way":
            lines += [f"One-way roads: {info['one_way']}."]
        elif st.name == "placement":
            lines += [f"Critical bridges never closed by an event: {info['bridges']}."]
        lines += ["", ("Backtracking solver counters", ACCENT)]
        for name, res in r.solver.items():
            lines.append(f"{name}: {res.nodes} candidates tried, {res.prunes} pruned, {res.backtracks} backtracks"
                         + (", node limit hit" if res.limit_hit else ""))
        if not r.solver:
            lines.append("none: the search never started")
        lines += ["", ("Validator verdict", ACCENT)]
        v = self.verdict
        if v is None:
            lines.append(("No circuit to validate.", BAD))
        else:
            lines.append(("PASS: every playability rule holds" if v.ok else "FAIL", GOOD if v.ok else BAD))
            lines += [f"{k}: {n}" for k, n in v.info["counts"].items()]
            lines += [f"Start-to-Finish routes: {v.info['start_finish_routes']}, dead ends {v.info['dead_ends']}",
                      f"Fuel plan feasible: {'yes' if v.info['fuel_plan'].feasible else 'no'}"] if v.ok else v.failures
        self.text.offset = 0
        self.text.set_lines(lines)

    def save(self) -> None:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        path = SAVE_DIR / f"generated_seed{self.seed}.json"
        save_circuit(self.circuit, path)
        self.saved_path = path
        self.message = f"Saved to {path}"

    def race(self) -> None:
        self.app.goto("race", circuit=self.circuit)

    def explore(self) -> None:
        self.app.goto("explorer", circuit=self.circuit)

    # --- input ---------------------------------------------------------------------------------------
    def handle_event(self, ev) -> bool:
        if ev.type == pygame.KEYDOWN:
            if ev.unicode.isdigit() and len(self.typed) < 6:
                self.typed += ev.unicode
                return True
            if ev.key == pygame.K_BACKSPACE:
                self.typed = self.typed[:-1]
                return True
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.generate()
                return True
            if ev.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.report.stages:
                self.tabs.index = max(0, min(len(STAGES) - 1, self.tabs.index + (1 if ev.key == pygame.K_RIGHT else -1)))
                self.show(self.tabs.index)
                return True
        return super().handle_event(ev)

    # --- drawing -----------------------------------------------------------------------------------------
    def draw(self, surf) -> None:
        surf.fill((14, 18, 26))
        for w in self.top + self.actions + [self.tabs]:
            w.draw(surf)
        text(surf, f"Seed {self.typed + '_' if self.typed else self.seed}", (240, 28), 28, TEXT, "midleft", bold=True)
        pygame.draw.rect(surf, (18, 23, 33), VIEW, border_radius=8)
        pygame.draw.rect(surf, BORDER, VIEW, 1, border_radius=8)
        if self.report.stages:
            st = self.report.stages[self.stage]
            self.view.draw(surf, False, self.overlays)
            text(surf, st.description, (VIEW.x + 10, VIEW.bottom + 14), 21, DIM, "midleft")
        Panel(RIGHT, "Pipeline report").draw(surf)
        self.text.draw(surf)
        text(surf, fit(self.message or "Type digits for a seed, Enter to generate, Left/Right to change stage.", 19, 760),
             (12, 696), 19, GOOD if self.message else DIM, "midleft")

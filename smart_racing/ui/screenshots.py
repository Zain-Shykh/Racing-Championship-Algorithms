"""Scripted screenshots: drive the real screens with synthetic input and save the window surface.

    SDL_VIDEODRIVER=dummy .venv/bin/python -m smart_racing.ui.screenshots [out_dir]

The same helpers (`run_until`, `click_vertex`) are used by tests/test_ui_smoke.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if __name__ == "__main__":                     # headless unless the caller already chose a driver
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from smart_racing.ui.app import App  # noqa: E402


def run_until(app: App, pred, dt: float = 0.1, limit: int = 6000) -> bool:
    """Pump frames until `pred()` is true. Returns False when `limit` frames pass first."""
    for _ in range(limit):
        if pred():
            return True
        app.step(dt)
    return pred()


def click_vertex(app: App, vertex: int) -> None:
    app.click(app.screen.view.pt(vertex))


def click_edge(app: App, edge_id: int) -> None:
    e = app.screen.g.edge(edge_id)
    app.click(app.screen.view.edge_mid(e))


def shoot_all(out: str | Path, app: App | None = None) -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    own = app is None
    app = app or App()
    app.goto("menu")
    saved: list[Path] = []

    def snap(name: str) -> None:
        app.pump(frames=2)
        path = out / f"{name}.png"
        app.save(str(path))
        saved.append(path)

    snap("menu")
    app.click_label("Quick Race")
    snap("quick_race_setup")

    app.click_label("Explore this circuit")
    click_vertex(app, 0)                                   # start
    click_vertex(app, 12)                                  # destination
    app.click_label("Run BFS")
    snap("explorer_bfs")
    app.click_label("Run DFS")
    snap("explorer_dfs")
    click_tab(app, "Routes")
    snap("explorer_routes")
    click_tab(app, "Compare")
    app.screen.mode.step(1)                                # cost presets, full lap
    snap("explorer_compare_presets")
    click_tab(app, "Resources")
    snap("explorer_resources")

    app.goto("race", circuit="harbor_eight", laps=2, autopilot=True)
    e = app.screen.engine
    run_until(app, lambda: e.clock > 36.5, 0.05)
    snap("race_blocked_road")

    app.goto("race", circuit="harbor_eight", laps=2, autopilot=False)
    e = app.screen.engine
    app.pump(frames=60)
    run_until(app, lambda: e.clock > 4 and len(e.legal_choices(0)) > 1 and e.human.edge_id is None, 0.05)
    snap("race_junction_prompt")

    app.goto("race", circuit="grand_ring", laps=1, autopilot=True)
    app.screen.set_speed(4)
    run_until(app, lambda: app.screen.results is not None, 0.25)
    snap("race_results")
    if own:
        pygame.quit()
    return saved


def click_tab(app: App, name: str) -> None:
    tabs = app.screen.tabs
    app.click(tabs._tab(tabs.names.index(name)).center)


if __name__ == "__main__":
    for p in shoot_all(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots"):
        print("saved", p)

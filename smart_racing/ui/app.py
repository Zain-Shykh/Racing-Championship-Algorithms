"""Application shell: window, screen manager, shared settings, error banner.

A screen is any `Screen` subclass. Screens are registered by name in
`smart_racing/ui/screens/__init__.py` (`SCREENS`); `app.goto(name, **kwargs)` builds one and makes it
current. Every screen callback runs through `App._guard`, so an unexpected exception becomes an
on-screen banner plus a stderr traceback instead of closing the window.
"""
from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass

import pygame

from smart_racing import config
from smart_racing.ui.widgets import BAD, BG, TEXT, _fonts, text

W, H = 1280, 720
FPS = 60


@dataclass
class Settings:
    """Shared, in-memory options. Quick Race and Settings both edit these."""
    laps: int = config.LAPS_PER_RACE
    preset: str = "Balanced"
    speed: int = 1
    show_ids: bool = True
    circuit: str = config.BUILTIN_CIRCUITS[0]
    opponents: int = config.NUM_OPPONENTS
    autopilot: bool = True
    pickup_solver: str = "dp"             # pickup planner the autopilot applies: "dp", "greedy" or "none"


class Screen:
    """Screen interface: handle_event(ev), update(dt), draw(surf). Widgets in `self.widgets` get events
    and are drawn automatically; override `all_widgets` when the set changes."""
    title = ""

    def __init__(self, app: "App", **kw) -> None:
        self.app = app
        self.widgets: list = []

    def all_widgets(self) -> list:
        return self.widgets

    def handle_event(self, ev) -> bool:
        if ev.type == pygame.MOUSEBUTTONDOWN or ev.type == pygame.MOUSEWHEEL or ev.type == pygame.KEYDOWN:
            for w in reversed(self.all_widgets()):
                if w.visible and w.handle_event(ev):
                    return True
            return False
        for w in self.all_widgets():           # motion and releases reach everything
            if w.visible:
                w.handle_event(ev)
        return False

    def on_escape(self) -> None:
        self.app.goto("menu")

    def update(self, dt: float) -> None:
        pass

    def draw(self, surf: pygame.Surface) -> None:
        surf.fill(BG)
        for w in self.all_widgets():
            if w.visible:
                w.draw(surf)


class App:
    def __init__(self) -> None:
        pygame.init()
        _fonts.clear()                   # fonts of an earlier pygame.quit() are dead (tests open several Apps)
        pygame.display.set_caption("Smart Racing Championship")
        try:
            self.surface = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:
            self.surface = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.settings = Settings()
        self.flow = None                 # the championship in progress (screens/championship.py ChampFlow)
        self.running = True
        self.screen: Screen | None = None
        self.screen_name = ""
        self.error: tuple[str, float] | None = None      # (message, seconds left)
        self._last_log = ("", 0.0)
        self.goto("menu")

    # --- navigation ---------------------------------------------------------------
    def goto(self, name: str, **kw) -> None:
        """Make the registered screen `name` current. If it fails to build, stay where we are."""
        from smart_racing.ui.screens import SCREENS
        screen = self._guard(f"opening {name}", lambda: SCREENS[name](self, **kw))
        if screen is not None:
            self.screen, self.screen_name = screen, name

    def quit(self) -> None:
        self.running = False

    # --- error handling --------------------------------------------------------------
    def _guard(self, what: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:                       # noqa: BLE001 - the whole point is to keep the window alive
            msg = f"{what}: {type(exc).__name__}: {exc}"
            if msg != self._last_log[0] or time.time() - self._last_log[1] > 2.0:
                print(f"[ui error] {msg}", file=sys.stderr)
                traceback.print_exc()
                self._last_log = (msg, time.time())
            self.error = (msg, 6.0)
            return None

    # --- frame ---------------------------------------------------------------------------
    def step(self, dt: float = 1 / FPS) -> None:
        """One frame: events, update, draw. The main loop, the tests and the screenshot helper all use this."""
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self._guard("escape", self.screen.on_escape)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_F12:
                self.save(f"screenshot_{int(time.time())}.png")
            elif self.screen is not None:
                self._guard("event", self.screen.handle_event, ev)
        if self.screen is not None:
            self._guard("update", self.screen.update, dt)
        self.draw()
        if self.error:
            msg, left = self.error
            self.error = (msg, left - dt) if left - dt > 0 else None

    def draw(self) -> None:
        if self.screen is not None:
            self._guard("draw", self.screen.draw, self.surface)
            # Modern cyber neon accent bar at the very top of the window
            pygame.draw.line(self.surface, (56, 189, 248), (0, 0), (W, 0), 2)
        if self.error:
            msg = self.error[0]
            bar = pygame.Rect(0, H - 34, W, 34)
            pygame.draw.rect(self.surface, (120, 25, 25), bar)
            pygame.draw.rect(self.surface, BAD, bar, 2)
            text(self.surface, "Error (logged to stderr): " + msg[:150], (12, H - 17), 21, TEXT, "midleft")
        pygame.display.flip()

    def run(self) -> None:
        while self.running:
            self.step(min(self.clock.tick(FPS) / 1000.0, 0.25))
        pygame.quit()

    # --- scripting helpers (tests and screenshots) ------------------------------------------
    def pump(self, seconds: float = 0.0, dt: float = 1 / FPS, frames: int = 1) -> None:
        for _ in range(max(frames, int(seconds / dt))):
            self.step(dt)

    def click(self, pos, button: int = 1) -> None:
        pos = (int(pos[0]), int(pos[1]))
        for kind in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if kind == pygame.MOUSEMOTION:
                pygame.event.post(pygame.event.Event(kind, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
            else:
                pygame.event.post(pygame.event.Event(kind, pos=pos, button=button))
        self.step(0.0)

    def press(self, key: int) -> None:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
        self.step(0.0)

    def click_label(self, label: str) -> None:
        """Click the visible button of the current screen whose label is `label`."""
        from smart_racing.ui.widgets import Button
        for w in self.screen.all_widgets():
            if isinstance(w, Button) and w.visible and w.label == label:
                return self.click(w.rect.center)
        raise KeyError(f"no button {label!r} on {self.screen_name}")

    def save(self, path: str) -> None:
        self.draw()
        pygame.image.save(self.surface, path)

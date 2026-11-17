"""Shared theme and small widgets. Fonts come from pygame's default font, so no asset files.

Every widget has `rect`, `visible`, `handle_event(ev) -> bool` (True = consumed) and `draw(surf)`.
Hover is tracked from MOUSEMOTION events, so synthetic events work the same as real ones.
"""
from __future__ import annotations

from typing import Callable, Sequence

import pygame

# --- theme ---------------------------------------------------------------------
BG = (14, 18, 26)
PANEL = (24, 30, 42)
PANEL_HI = (34, 43, 60)
BORDER = (62, 76, 102)
TEXT = (230, 235, 245)
DIM = (150, 160, 178)
ACCENT = (70, 160, 255)
GOOD = (90, 205, 125)
WARN = (250, 190, 70)
BAD = (240, 90, 90)
ROUTE_COLORS = [(0, 225, 255), (255, 90, 225), (255, 255, 255), (160, 120, 255)]

_fonts: dict[tuple[int, bool], pygame.font.Font] = {}


def font(size: int = 22, bold: bool = False) -> pygame.font.Font:
    if (size, bold) not in _fonts:
        if not pygame.font.get_init():
            pygame.font.init()
        f = pygame.font.Font(None, size)
        f.set_bold(bold)
        _fonts[(size, bold)] = f
    return _fonts[(size, bold)]


def text(surf: pygame.Surface, s: str, pos, size: int = 22, color=TEXT, anchor: str = "topleft",
         bold: bool = False) -> pygame.Rect:
    """Draw one line; `anchor` is any pygame.Rect attribute (topleft, center, midtop, topright...)."""
    img = font(size, bold).render(str(s), True, color)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def wrap(s: str, size: int, width: int) -> list[str]:
    """Greedy word wrap of one paragraph to `width` pixels."""
    f, lines, cur = font(size), [], ""
    for word in s.split(" "):
        trial = f"{cur} {word}" if cur else word
        if cur and f.size(trial)[0] > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def fit(s: str, size: int, width: int) -> str:
    """Truncate with '..' so the text fits in `width` pixels."""
    f = font(size)
    if f.size(s)[0] <= width:
        return s
    while s and f.size(s + "..")[0] > width:
        s = s[:-1]
    return s + ".."


def blend(a, b, t: float):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def draw_bar(surf, rect, frac: float, color, label: str = "") -> None:
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, (10, 13, 19), rect, border_radius=4)
    inner = rect.inflate(-4, -4)
    inner.w = int(inner.w * max(0.0, min(1.0, frac)))
    if inner.w > 0:
        pygame.draw.rect(surf, color, inner, border_radius=3)
    pygame.draw.rect(surf, BORDER, rect, 1, border_radius=4)
    if label:
        text(surf, label, rect.center, 20, TEXT, "center")


class Widget:
    visible = True

    def __init__(self, rect) -> None:
        self.rect = pygame.Rect(rect)
        self.hover = False

    def _track(self, ev) -> None:
        if ev.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(ev.pos)

    def handle_event(self, ev) -> bool:
        self._track(ev)
        return False

    def draw(self, surf) -> None:
        pass


class Panel(Widget):
    def __init__(self, rect, title: str = "") -> None:
        super().__init__(rect)
        self.title = title

    @property
    def inner(self) -> pygame.Rect:
        top = 30 if self.title else 8
        return pygame.Rect(self.rect.x + 10, self.rect.y + top, self.rect.w - 20, self.rect.h - top - 8)

    def draw(self, surf) -> None:
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surf, BORDER, self.rect, 1, border_radius=8)
        if self.title:
            text(surf, self.title, (self.rect.x + 12, self.rect.y + 8), 22, ACCENT, bold=True)


class Button(Widget):
    def __init__(self, rect, label: str, on_click: Callable[[], None] | None = None,
                 toggled: bool = False, color=None) -> None:
        super().__init__(rect)
        self.label, self.on_click, self.toggled, self.color = label, on_click, toggled, color
        self.enabled = True

    def handle_event(self, ev) -> bool:
        self._track(ev)
        if (ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.enabled
                and self.rect.collidepoint(ev.pos)):
            if self.on_click:
                self.on_click()
            return True
        return False

    def draw(self, surf) -> None:
        base = self.color or (ACCENT if self.toggled else PANEL_HI)
        fill = blend(base, (255, 255, 255), 0.15) if self.hover and self.enabled else base
        if not self.enabled:
            fill = blend(PANEL, BG, 0.5)
        pygame.draw.rect(surf, fill, self.rect, border_radius=7)
        pygame.draw.rect(surf, ACCENT if self.hover and self.enabled else BORDER, self.rect, 1, border_radius=7)
        size = 24 if self.rect.h >= 40 else 21
        text(surf, fit(self.label, size, self.rect.w - 10), self.rect.center, size,
             TEXT if self.enabled else DIM, "center")


class Cycle(Widget):
    """`caption  < value >`: click the left or right half of the value box to step."""

    def __init__(self, rect, caption: str, options: Sequence, index: int = 0,
                 on_change: Callable | None = None, fmt: Callable = str, caption_w: int | None = None) -> None:
        super().__init__(rect)
        self.caption, self.options, self.index = caption, list(options), index
        self.on_change, self.fmt = on_change, fmt
        self.caption_w = caption_w if caption_w is not None else int(self.rect.w * 0.4) if caption else 0

    @property
    def value(self):
        return self.options[self.index]

    def set_value(self, value) -> None:
        self.index = self.options.index(value)

    @property
    def box(self) -> pygame.Rect:
        return pygame.Rect(self.rect.x + self.caption_w, self.rect.y, self.rect.w - self.caption_w, self.rect.h)

    def step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.options)
        if self.on_change:
            self.on_change(self.value)

    def handle_event(self, ev) -> bool:
        self._track(ev)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.box.collidepoint(ev.pos):
            self.step(-1 if ev.pos[0] < self.box.centerx else 1)
            return True
        return False

    def draw(self, surf) -> None:
        box = self.box
        if self.caption:
            text(surf, self.caption, (self.rect.x, self.rect.centery), 21, DIM, "midleft")
        pygame.draw.rect(surf, PANEL_HI if not self.hover else blend(PANEL_HI, (255, 255, 255), 0.1),
                         box, border_radius=7)
        pygame.draw.rect(surf, BORDER, box, 1, border_radius=7)
        cy, h = box.centery, 6
        pygame.draw.polygon(surf, ACCENT, [(box.x + 18, cy), (box.x + 18 + h, cy - h), (box.x + 18 + h, cy + h)])
        pygame.draw.polygon(surf, ACCENT, [(box.right - 18, cy), (box.right - 18 - h, cy - h),
                                           (box.right - 18 - h, cy + h)])
        text(surf, fit(self.fmt(self.value), 22, box.w - 64), box.center, 22, TEXT, "center")


class Tabs(Widget):
    def __init__(self, rect, names: Sequence[str], index: int = 0, on_change: Callable | None = None) -> None:
        super().__init__(rect)
        self.names, self.index, self.on_change = list(names), index, on_change

    def _tab(self, i: int) -> pygame.Rect:
        w = self.rect.w / len(self.names)
        return pygame.Rect(int(self.rect.x + i * w), self.rect.y, int(w) - 3, self.rect.h)

    def handle_event(self, ev) -> bool:
        self._track(ev)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i in range(len(self.names)):
                if self._tab(i).collidepoint(ev.pos):
                    if i != self.index:
                        self.index = i
                        if self.on_change:
                            self.on_change(self.names[i])
                    return True
        return False

    def draw(self, surf) -> None:
        for i, name in enumerate(self.names):
            r = self._tab(i)
            on = i == self.index
            pygame.draw.rect(surf, ACCENT if on else PANEL_HI, r, border_top_left_radius=7, border_top_right_radius=7)
            text(surf, name, r.center, 22, TEXT if on else DIM, "center", bold=on)


class ScrollText(Widget):
    """Wrapped, scrollable lines (mouse wheel or Up/Down/PageUp/PageDown while hovered).
    A line is `str` or `(str, colour)`."""

    SIZE, LINE = 20, 22

    def __init__(self, rect, lines: Sequence = ()) -> None:
        super().__init__(rect)
        self.offset = 0
        self.rows: list[tuple[str, tuple]] = []
        self.set_lines(lines)

    def set_lines(self, lines: Sequence) -> None:
        width = self.rect.w - 22
        self.rows = []
        for line in lines:
            s, color = (line, TEXT) if isinstance(line, str) else line
            indent = "  " if s.startswith("  ") else ""
            for part in wrap(s.strip(" "), self.SIZE, width - 8 * len(indent)) if s else [""]:
                self.rows.append((indent + part, color))
        self.offset = min(self.offset, self.max_offset)

    @property
    def visible_rows(self) -> int:
        return max(1, (self.rect.h - 8) // self.LINE)

    @property
    def max_offset(self) -> int:
        return max(0, len(self.rows) - self.visible_rows)

    def scroll(self, rows: int) -> None:
        self.offset = max(0, min(self.max_offset, self.offset + rows))

    def handle_event(self, ev) -> bool:
        self._track(ev)
        if ev.type == pygame.MOUSEWHEEL and (self.hover or self.rect.collidepoint(pygame.mouse.get_pos())):
            self.scroll(-ev.y * 3)
            return True
        if ev.type == pygame.KEYDOWN and self.hover:
            step = {pygame.K_UP: -1, pygame.K_DOWN: 1, pygame.K_PAGEUP: -self.visible_rows,
                    pygame.K_PAGEDOWN: self.visible_rows}.get(ev.key)
            if step:
                self.scroll(step)
                return True
        return False

    def draw(self, surf) -> None:
        pygame.draw.rect(surf, (18, 23, 33), self.rect, border_radius=6)
        pygame.draw.rect(surf, BORDER, self.rect, 1, border_radius=6)
        old = surf.get_clip()
        surf.set_clip(self.rect.inflate(-4, -4))
        for i, (s, color) in enumerate(self.rows[self.offset:self.offset + self.visible_rows]):
            text(surf, s, (self.rect.x + 8, self.rect.y + 6 + i * self.LINE), self.SIZE, color)
        surf.set_clip(old)
        if self.max_offset:
            track = pygame.Rect(self.rect.right - 8, self.rect.y + 4, 4, self.rect.h - 8)
            pygame.draw.rect(surf, (40, 50, 68), track, border_radius=2)
            h = max(16, int(track.h * self.visible_rows / len(self.rows)))
            y = track.y + int((track.h - h) * self.offset / self.max_offset)
            pygame.draw.rect(surf, ACCENT, (track.x, y, 4, h), border_radius=2)


def draw_table(surf, rect, header: Sequence[str], rows: Sequence[Sequence[str]], widths: Sequence[int],
               swatches: Sequence | None = None, row_h: int = 22) -> int:
    """Simple grid. Column 0 is left-aligned, the others right-aligned. `swatches` gives a
    colour square before each row's first cell. Returns the table height in pixels."""
    rect = pygame.Rect(rect)
    total = (len(rows) + 1) * row_h + 4
    pygame.draw.rect(surf, (18, 23, 33), (rect.x, rect.y, rect.w, total), border_radius=6)
    pygame.draw.rect(surf, BORDER, (rect.x, rect.y, rect.w, total), 1, border_radius=6)
    for r, cells in enumerate([header] + [list(x) for x in rows]):
        y = rect.y + 4 + r * row_h
        if r == 0:
            pygame.draw.line(surf, BORDER, (rect.x + 4, y + row_h - 2), (rect.right - 4, y + row_h - 2))
        x = rect.x + 8
        for c, cell in enumerate(cells):
            color = ACCENT if r == 0 else TEXT
            if c == 0:
                if r and swatches and swatches[r - 1] is not None:
                    pygame.draw.rect(surf, swatches[r - 1], (x, y + 5, 12, 12), border_radius=3)
                    pygame.draw.rect(surf, BORDER, (x, y + 5, 12, 12), 1, border_radius=3)
                    text(surf, fit(cell, 20, widths[c] - 24), (x + 18, y + 3), 20, color)
                else:
                    text(surf, fit(cell, 20, widths[c] - 10), (x, y + 3), 20, color)
            else:
                text(surf, fit(cell, 20, widths[c] - 10), (x + widths[c] - 12, y + 3), 20, color, "topright")
            x += widths[c]
    return total

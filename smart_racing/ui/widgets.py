"""Shared theme and small widgets. Modern, accessible, polished UI according to ui-skills design principles.

Every widget has `rect`, `visible`, `handle_event(ev) -> bool` (True = consumed) and `draw(surf)`.
Hover is tracked from MOUSEMOTION events, so synthetic events work the same as real ones.
"""
from __future__ import annotations

from typing import Callable, Sequence

import pygame

# --- Modern, cohesive dark racing theme (Cyber-precision palette) -----------------
BG = (10, 14, 22)           # Deep obsidian slate
PANEL = (17, 24, 38)        # Modern elevated card surface
PANEL_HI = (28, 38, 58)     # Interactive surface base
PANEL_HOVER = (38, 52, 78)  # Hover surface
BORDER = (46, 62, 90)       # Refined structural border
BORDER_HI = (76, 105, 150)  # Highlighted border
TEXT = (246, 248, 254)      # High-contrast crisp white
DIM = (148, 162, 185)       # Clean slate secondary text
ACCENT = (56, 189, 248)     # Vibrant electric cyan
ACCENT_BG = (18, 48, 76)    # Accent pill background
GOOD = (52, 211, 153)       # High-octane racing green
WARN = (251, 146, 60)       # Warm amber
BAD = (240, 90, 90)         # Clean coral crimson
PURPLE = (192, 132, 252)    # Nitro / shortcut lavender
ROUTE_COLORS = [(56, 189, 248), (244, 114, 182), (255, 255, 255), (167, 139, 250)]

_fonts: dict[tuple[int, bool], pygame.font.Font] = {}
_font_family: str | None = None


def _resolve_font_family() -> str | None:
    global _font_family
    if _font_family is None:
        if not pygame.font.get_init():
            pygame.font.init()
        # Look for clean modern system fonts
        for candidate in ["segoeui", "calibri", "arial", "dejavusans", "helvetica"]:
            if pygame.font.match_font(candidate):
                _font_family = candidate
                break
        if _font_family is None:
            _font_family = ""
    return _font_family or None


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
    """Draw an aesthetic progress / telemetry bar with gloss highlight and border."""
    rect = pygame.Rect(rect)
    # Recessed track slot
    pygame.draw.rect(surf, (10, 14, 22), rect, border_radius=5)
    inner = rect.inflate(-4, -4)
    inner.w = int(inner.w * max(0.0, min(1.0, frac)))
    if inner.w > 0:
        pygame.draw.rect(surf, color, inner, border_radius=4)
        # Subtle top-edge gloss
        if inner.h > 6:
            gloss = pygame.Rect(inner.x, inner.y, inner.w, inner.h // 2)
            gloss_color = blend(color, (255, 255, 255), 0.25)
            pygame.draw.rect(surf, gloss_color, gloss, border_top_left_radius=4, border_top_right_radius=4)
    pygame.draw.rect(surf, BORDER, rect, 1, border_radius=5)
    if label:
        text(surf, label, rect.center, 20, TEXT, "center", bold=True)


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
        top = 32 if self.title else 8
        return pygame.Rect(self.rect.x + 10, self.rect.y + top, self.rect.w - 20, self.rect.h - top - 8)

    def draw(self, surf) -> None:
        # Subtle card shadow
        shadow_rect = pygame.Rect(self.rect.x + 2, self.rect.y + 3, self.rect.w, self.rect.h)
        pygame.draw.rect(surf, (5, 8, 14), shadow_rect, border_radius=9)
        # Card body
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=8)
        pygame.draw.rect(surf, BORDER, self.rect, 1, border_radius=8)
        if self.title:
            # Header accent marker pill
            pygame.draw.rect(surf, ACCENT, (self.rect.x + 12, self.rect.y + 9, 4, 16), border_radius=2)
            text(surf, self.title, (self.rect.x + 22, self.rect.y + 8), 22, TEXT, bold=True)
            # Header divider line
            pygame.draw.line(surf, (28, 38, 58), (self.rect.x + 10, self.rect.y + 29),
                             (self.rect.right - 10, self.rect.y + 29), 1)


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
        base = self.color or (blend(ACCENT, PANEL, 0.6) if self.toggled else PANEL_HI)
        fill = blend(base, (255, 255, 255), 0.18) if self.hover and self.enabled else base
        if not self.enabled:
            fill = blend(PANEL, BG, 0.5)

        # Drop shadow for card elevation
        if self.enabled:
            shadow = pygame.Rect(self.rect.x + 2, self.rect.y + 3, self.rect.w, self.rect.h)
            pygame.draw.rect(surf, (5, 8, 14), shadow, border_radius=8)

        pygame.draw.rect(surf, fill, self.rect, border_radius=7)

        # Border styling with hover glow
        border_col = ACCENT if (self.hover and self.enabled) else (ACCENT if self.toggled else BORDER)
        pygame.draw.rect(surf, border_col, self.rect, 2 if (self.hover and self.enabled) else 1, border_radius=7)

        # Sleek left accent indicator strip
        if self.enabled:
            strip_col = ACCENT if (self.hover or self.toggled) else (self.color or (55, 75, 110))
            pygame.draw.rect(surf, strip_col, (self.rect.x + 1, self.rect.y + 4, 4, self.rect.h - 8), border_radius=2)

        size = 24 if self.rect.h >= 40 else 21
        label_col = (255, 255, 255) if (self.hover and self.enabled) else (TEXT if self.enabled else DIM)
        text(surf, fit(self.label, size, self.rect.w - 18), self.rect.center, size,
             label_col, "center", bold=(self.toggled or self.hover))


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
            text(surf, self.caption, (self.rect.x, self.rect.centery), 21, DIM, "midleft", bold=True)

        # Value pill
        fill = blend(PANEL_HI, (255, 255, 255), 0.12) if self.hover else PANEL_HI
        pygame.draw.rect(surf, fill, box, border_radius=7)
        pygame.draw.rect(surf, ACCENT if self.hover else BORDER, box, 1, border_radius=7)

        cy, h = box.centery, 6
        # Left chevron
        arrow_col = ACCENT if self.hover else DIM
        pygame.draw.polygon(surf, arrow_col, [(box.x + 16, cy), (box.x + 16 + h, cy - h), (box.x + 16 + h, cy + h)])
        # Right chevron
        pygame.draw.polygon(surf, arrow_col, [(box.right - 16, cy), (box.right - 16 - h, cy - h),
                                              (box.right - 16 - h, cy + h)])
        text(surf, fit(self.fmt(self.value), 22, box.w - 64), box.center, 22, TEXT, "center", bold=True)


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
            bg_col = blend(ACCENT, PANEL, 0.6) if on else PANEL_HI
            pygame.draw.rect(surf, bg_col, r, border_top_left_radius=7, border_top_right_radius=7)
            pygame.draw.rect(surf, ACCENT if on else BORDER, r, 1, border_top_left_radius=7, border_top_right_radius=7)
            if on:
                # Active indicator bar
                pygame.draw.rect(surf, ACCENT, (r.x + 6, r.bottom - 3, r.w - 12, 3), border_radius=1)
            text(surf, name, (r.centerx, r.centery - (1 if on else 0)), 22, TEXT if on else DIM, "center", bold=on)


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
        pygame.draw.rect(surf, (14, 19, 30), self.rect, border_radius=7)
        pygame.draw.rect(surf, BORDER, self.rect, 1, border_radius=7)
        old = surf.get_clip()
        surf.set_clip(self.rect.inflate(-4, -4))
        for i, (s, color) in enumerate(self.rows[self.offset:self.offset + self.visible_rows]):
            text(surf, s, (self.rect.x + 8, self.rect.y + 6 + i * self.LINE), self.SIZE, color)
        surf.set_clip(old)
        if self.max_offset:
            track = pygame.Rect(self.rect.right - 8, self.rect.y + 4, 4, self.rect.h - 8)
            pygame.draw.rect(surf, (30, 42, 62), track, border_radius=2)
            h = max(16, int(track.h * self.visible_rows / len(self.rows)))
            y = track.y + int((track.h - h) * self.offset / self.max_offset)
            pygame.draw.rect(surf, ACCENT, (track.x, y, 4, h), border_radius=2)


def draw_table(surf, rect, header: Sequence[str], rows: Sequence[Sequence[str]], widths: Sequence[int],
               swatches: Sequence | None = None, row_h: int = 22) -> int:
    """Modern alternating table grid. Column 0 is left-aligned, the others right-aligned.
    `swatches` gives a colour square before each row's first cell. Returns the table height in pixels."""
    rect = pygame.Rect(rect)
    total = (len(rows) + 1) * row_h + 4
    pygame.draw.rect(surf, (14, 19, 30), (rect.x, rect.y, rect.w, total), border_radius=7)
    pygame.draw.rect(surf, BORDER, (rect.x, rect.y, rect.w, total), 1, border_radius=7)
    for r, cells in enumerate([header] + [list(x) for x in rows]):
        y = rect.y + 4 + r * row_h
        # Alternating row background for enhanced readability
        if r > 0 and r % 2 == 1:
            row_bg = pygame.Rect(rect.x + 2, y, rect.w - 4, row_h)
            pygame.draw.rect(surf, (19, 26, 42), row_bg, border_radius=3)
        if r == 0:
            # Header bottom accent rule
            pygame.draw.line(surf, ACCENT, (rect.x + 6, y + row_h - 2), (rect.right - 6, y + row_h - 2), 2)
        x = rect.x + 8
        for c, cell in enumerate(cells):
            color = ACCENT if r == 0 else TEXT
            bold_flag = (r == 0)
            if c == 0:
                if r and swatches and swatches[r - 1] is not None:
                    pygame.draw.rect(surf, swatches[r - 1], (x, y + 5, 12, 12), border_radius=3)
                    pygame.draw.rect(surf, BORDER, (x, y + 5, 12, 12), 1, border_radius=3)
                    text(surf, fit(cell, 20, widths[c] - 24), (x + 18, y + 3), 20, color, bold=bold_flag)
                else:
                    text(surf, fit(cell, 20, widths[c] - 10), (x, y + 3), 20, color, bold=bold_flag)
            else:
                text(surf, fit(cell, 20, widths[c] - 10), (x + widths[c] - 12, y + 3), 20, color, "topright", bold=bold_flag)
            x += widths[c]
    return total

"""Graph renderer shared by every screen: scales circuit coordinates into a viewport and draws
roads, vertices, route overlays, cars and a legend. Hit-testing returns the nearest vertex or road.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable

import pygame

from smart_racing.core.graph import (CHECKPOINT, DEAD_END, FINISH, FUEL_STATION, INTERSECTION,
                                     NITRO_PICKUP, START, Edge, TrackGraph)
from smart_racing.ui.widgets import BAD, BG, BORDER, DIM, GOOD, PANEL, TEXT, WARN, blend, font, text

DIFF_COLORS = {1: (70, 205, 120), 2: (165, 215, 70), 3: (250, 195, 50), 4: (245, 120, 45), 5: (215, 60, 60)}
CAR_COLORS = [(255, 255, 255), (251, 146, 60), (244, 114, 182), (74, 222, 128), (250, 204, 21),
              (56, 189, 248), (248, 113, 113), (192, 132, 252), (45, 212, 191), (251, 191, 36)]
HALO = {"oil": (160, 100, 235), "speed": (255, 205, 40)}
ROAD_BG = (10, 14, 22)
ASPHALT = (20, 27, 40)


@dataclass
class Overlay:
    """A highlighted route: edge ids drawn on top of the roads, shifted sideways by `offset` px."""
    edges: Iterable[int]
    color: tuple
    width: int = 5
    offset: float = 0.0


def road_width(edge: Edge) -> int:
    """Easier roads are wider: 8 px at difficulty 1 down to 4 px at difficulty 5."""
    return 9 - edge.effective_difficulty


# --- icons (shared with the legend) ----------------------------------------------
def draw_vertex_icon(surf, vtype: str, center, r: int = 13, order: int | None = None, active: bool = True) -> None:
    cx, cy = int(center[0]), int(center[1])
    dim = (lambda c: c) if active else (lambda c: blend(c, BG, 0.65))
    ink = TEXT if active else DIM

    def label(s, color=(255, 255, 255)):
        text(surf, s, (cx, cy), 21 if r >= 12 else 17, color if active else ink, "center", bold=True)

    if vtype == INTERSECTION:
        pygame.draw.circle(surf, dim((100, 115, 140)), (cx, cy), max(5, r // 2))
        pygame.draw.circle(surf, dim((25, 35, 50)), (cx, cy), max(5, r // 2), 2)
    elif vtype == FINISH:
        box = pygame.Rect(cx - r, cy - r, 2 * r, 2 * r)
        n = 4
        for i in range(n):
            for j in range(n):
                shade = (245, 245, 250) if (i + j) % 2 == 0 else (25, 30, 42)
                pygame.draw.rect(surf, dim(shade), (box.x + i * box.w // n, box.y + j * box.h // n,
                                                   box.w // n + 1, box.h // n + 1))
        pygame.draw.rect(surf, dim((255, 255, 255)), box, 2)
    elif vtype == FUEL_STATION:
        pygame.draw.rect(surf, dim((239, 68, 68)), (cx - r, cy - r, 2 * r, 2 * r), border_radius=5)
        pygame.draw.rect(surf, dim((254, 202, 202)), (cx - r, cy - r, 2 * r, 2 * r), 2, border_radius=5)
        label("F")
    elif vtype == NITRO_PICKUP:
        pts = [(cx, cy - r - 3), (cx + r + 3, cy), (cx, cy + r + 3), (cx - r - 3, cy)]
        pygame.draw.polygon(surf, dim((56, 189, 248)), pts)
        pygame.draw.polygon(surf, dim((224, 242, 254)), pts, 2)
        label("N")
    else:
        fill, rim, mark = {START: ((46, 204, 113), (220, 252, 231), "S"),
                           CHECKPOINT: ((251, 191, 36), (254, 240, 138), str(order or "")),
                           DEAD_END: ((168, 85, 247), (243, 232, 255), "D")}[vtype]
        pygame.draw.circle(surf, dim(fill), (cx, cy), r)
        pygame.draw.circle(surf, dim(rim), (cx, cy), r, 2)
        label(mark, (15, 20, 28) if vtype == CHECKPOINT else (255, 255, 255))
    if not active:
        pygame.draw.line(surf, (110, 118, 135), (cx - r, cy + r), (cx + r, cy - r), 2)


def _dashed(surf, color, a, b, width, dash=11, gap=7) -> None:
    length = math.dist(a, b)
    if length < 1:
        return
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    d = 0.0
    while d < length:
        e = min(d + dash, length)
        pygame.draw.line(surf, color, (a[0] + ux * d, a[1] + uy * d), (a[0] + ux * e, a[1] + uy * e), width)
        d += dash + gap


def _arrow(surf, color, mid, ux, uy, size=9) -> None:
    tip = (mid[0] + ux * size, mid[1] + uy * size)
    left = (mid[0] - ux * size - uy * size * 0.85, mid[1] - uy * size + ux * size * 0.85)
    right = (mid[0] - ux * size + uy * size * 0.85, mid[1] - uy * size - ux * size * 0.85)
    pygame.draw.polygon(surf, ROAD_BG, [tip, left, right])
    pygame.draw.polygon(surf, color, [tip, left, right], 2)


class GraphView:
    """Scales a TrackGraph into `rect` (aspect ratio kept) and draws it."""

    def __init__(self, graph: TrackGraph, rect, margin: int = 28) -> None:
        self.graph, self.rect = graph, pygame.Rect(rect)
        xs = [v.x for v in graph.vertices()]
        ys = [v.y for v in graph.vertices()]
        w, h = max(max(xs) - min(xs), 1.0), max(max(ys) - min(ys), 1.0)
        self.scale = min((self.rect.w - 2 * margin) / w, (self.rect.h - 2 * margin) / h)
        ox = self.rect.x + (self.rect.w - w * self.scale) / 2 - min(xs) * self.scale
        oy = self.rect.y + (self.rect.h - h * self.scale) / 2 - min(ys) * self.scale
        self.origin = (ox, oy)
        self.points = {v.id: self.to_screen(v.x, v.y) for v in graph.vertices()}

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        """Circuit coordinates (e.g. `RaceEngine.xy`) to window pixels."""
        return self.origin[0] + x * self.scale, self.origin[1] + y * self.scale

    def pt(self, vertex_id: int) -> tuple[float, float]:
        return self.points[vertex_id]

    def edge_mid(self, edge: Edge, t: float = 0.5) -> tuple[float, float]:
        a, b = self.points[edge.src], self.points[edge.dst]
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t

    # --- hit-testing --------------------------------------------------------------
    def vertex_at(self, pos, radius: float = 18) -> int | None:
        best = min(self.points, key=lambda i: (math.dist(pos, self.points[i]), i))
        return best if math.dist(pos, self.points[best]) <= radius else None

    def edge_at(self, pos, tol: float = 9, only: Iterable[int] | None = None) -> int | None:
        allowed = None if only is None else set(only)
        best, best_d = None, tol
        for e in self.graph.edges():
            if allowed is not None and e.id not in allowed:
                continue
            a, b = self.points[e.src], self.points[e.dst]
            dx, dy = b[0] - a[0], b[1] - a[1]
            span = dx * dx + dy * dy or 1.0
            t = max(0.0, min(1.0, ((pos[0] - a[0]) * dx + (pos[1] - a[1]) * dy) / span))
            d = math.dist(pos, (a[0] + t * dx, a[1] + t * dy))
            if d < best_d:
                best, best_d = e.id, d
        return best

    # --- drawing ---------------------------------------------------------------------
    def draw(self, surf, show_ids: bool = False, overlays: Iterable[Overlay] = (),
             rings: dict[int, tuple] | None = None, flash: dict[int, float] | None = None,
             tags: dict[int, str] | None = None) -> None:
        """Roads, overlays, then vertices. `rings`: vertex id -> ring colour. `flash`: edge id -> 0..1
        pulse for a road that just changed. `tags`: vertex id -> short text drawn above the vertex."""
        g = self.graph
        old = surf.get_clip()
        surf.set_clip(self.rect)
        for e in g.edges():
            self._road(surf, e, (flash or {}).get(e.id, 0.0))
        for ov in overlays:
            for edge_id in ov.edges:
                self._overlay_edge(surf, g.edge(edge_id), ov)
        for e in g.edges():
            self._marks(surf, e, show_ids)
        for v in g.vertices():
            p = self.points[v.id]
            if rings and v.id in rings:
                pygame.draw.circle(surf, rings[v.id], p, 21, 3)
            draw_vertex_icon(surf, v.type, p, 13 if v.type != INTERSECTION else 11, v.checkpoint_order, v.active)
            if show_ids:
                text(surf, str(v.id), (p[0] + 14, p[1] - 22), 17, (170, 180, 200))
            if tags and v.id in tags:
                text(surf, tags[v.id], (p[0], p[1] - 24), 22, WARN, "midbottom", bold=True)
        surf.set_clip(old)

    def _road(self, surf, e: Edge, pulse: float = 0.0) -> None:
        a, b = self.points[e.src], self.points[e.dst]
        w = road_width(e)
        if pulse > 0:
            pygame.draw.line(surf, blend(BG, (255, 255, 255), min(1.0, pulse)), a, b, w + 14)
        if e.blocked:
            pygame.draw.line(surf, (35, 20, 24), a, b, w + 4)
            pygame.draw.line(surf, (70, 72, 84), a, b, 6)
            return
        # Asphalt road foundation casing for clean visual track depth
        pygame.draw.line(surf, ASPHALT, a, b, w + 6)
        for kind in e.effects.values():
            pygame.draw.line(surf, HALO[kind], a, b, w + 8)
        color = DIFF_COLORS[e.effective_difficulty]
        if e.is_shortcut:
            pygame.draw.line(surf, (30, 42, 60), a, b, w + 2)
            _dashed(surf, color, a, b, w)
        else:
            pygame.draw.line(surf, color, a, b, w)

    def _overlay_edge(self, surf, e: Edge, ov: Overlay) -> None:
        a, b = self.points[e.src], self.points[e.dst]
        length = math.dist(a, b) or 1.0
        nx, ny = -(b[1] - a[1]) / length * ov.offset, (b[0] - a[0]) / length * ov.offset
        pygame.draw.line(surf, ov.color, (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), ov.width)

    def _marks(self, surf, e: Edge, show_ids: bool) -> None:
        a, b = self.points[e.src], self.points[e.dst]
        mid = self.edge_mid(e)
        length = math.dist(a, b) or 1.0
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        if e.blocked:
            s = 11
            pygame.draw.circle(surf, (40, 10, 10), mid, s + 4)
            pygame.draw.line(surf, BAD, (mid[0] - s, mid[1] - s), (mid[0] + s, mid[1] + s), 5)
            pygame.draw.line(surf, BAD, (mid[0] - s, mid[1] + s), (mid[0] + s, mid[1] - s), 5)
        elif e.directed:
            _arrow(surf, (245, 248, 255), mid, ux, uy)
        elif e.effects:
            pygame.draw.circle(surf, ROAD_BG, mid, 9)
            text(surf, "!", mid, 22, HALO[next(iter(e.effects.values()))], "center", bold=True)
        if show_ids:
            off = (mid[0] - uy * 15, mid[1] + ux * 15)
            text(surf, str(e.id), off, 17, (130, 200, 255), "center")

    # --- cars -----------------------------------------------------------------------------
    def draw_car(self, surf, pos, heading: float, color, label: str = "", player: bool = False,
                 boost: bool = False, faded: bool = False) -> None:
        """A small car polygon pointing along `heading` (radians, screen coordinates)."""
        c, s = math.cos(heading), math.sin(heading)

        def pts(shape):
            return [(pos[0] + 1.35 * (x * c - y * s), pos[1] + 1.35 * (x * s + y * c)) for x, y in shape]

        if faded:
            color = blend(color, BG, 0.6)
        if boost:
            # Dual-stage flame exhaust for nitro boost
            pygame.draw.polygon(surf, (56, 189, 248), pts([(-9, -2), (-24, 0), (-9, 2)]))
            pygame.draw.polygon(surf, (255, 200, 50), pts([(-9, -1.2), (-15, 0), (-9, 1.2)]))
        body = pts([(12, 0), (7, -6), (-9, -6), (-9, 6), (7, 6)])
        pygame.draw.polygon(surf, color, body)
        pygame.draw.polygon(surf, (255, 255, 255) if player else (20, 25, 35), body, 2)
        # Cockpit windshield
        pygame.draw.polygon(surf, (15, 25, 45), pts([(5, -3.5), (-3, -3.5), (-3, 3.5), (5, 3.5)]))
        # Rear spoiler
        pygame.draw.line(surf, (255, 255, 255) if player else (40, 50, 70),
                         pts([(-9, -6.5)])[0], pts([(-9, 6.5)])[0], 2)
        if player:
            x, y = int(pos[0]), int(pos[1]) - 22
            # Glowing double chevron for player indicator
            pygame.draw.polygon(surf, WARN, [(x - 6, y - 6), (x + 6, y - 6), (x, y + 2)])
            pygame.draw.polygon(surf, (255, 255, 255), [(x - 4, y - 5), (x + 4, y - 5), (x, y)])
        if label:
            text(surf, label, (pos[0], pos[1] + 16), 17, color, "center", bold=True)


# --- legend -----------------------------------------------------------------------------
def _swatch(color, width=8, dashed=False, halo=None, cross=False, arrow=False) -> Callable:
    def draw(surf, cx, cy):
        a, b = (cx - 14, cy), (cx + 14, cy)
        if halo:
            pygame.draw.line(surf, halo, a, b, width + 8)
        if cross:
            pygame.draw.line(surf, (70, 72, 84), a, b, 6)
            pygame.draw.line(surf, BAD, (cx - 7, cy - 7), (cx + 7, cy + 7), 4)
            pygame.draw.line(surf, BAD, (cx - 7, cy + 7), (cx + 7, cy - 7), 4)
        elif dashed:
            _dashed(surf, color, a, b, width, 6, 4)
        else:
            pygame.draw.line(surf, color, a, b, width)
        if arrow:
            _arrow(surf, (235, 240, 250), (cx, cy), 1, 0, 6)
    return draw


def _icon(vtype, order=None, active=True) -> Callable:
    return lambda surf, cx, cy: draw_vertex_icon(surf, vtype, (cx, cy), 9, order, active)


LEGEND_ITEMS = [
    (_icon(START), "Start"), (_icon(FINISH), "Finish"), (_icon(CHECKPOINT, 1), "Checkpoint"),
    (_icon(FUEL_STATION), "Fuel"), (_icon(NITRO_PICKUP), "Nitro"), (_icon(DEAD_END), "Dead end"),
    (_icon(INTERSECTION), "Junction"), (_icon(FUEL_STATION, active=False), "Inactive"),
    (_swatch(DIFF_COLORS[1], 8), "Easy"), (_swatch(DIFF_COLORS[3], 6), "Medium"),
    (_swatch(DIFF_COLORS[5], 4), "Hard"), (_swatch(DIFF_COLORS[3], 6, dashed=True), "Shortcut"),
    (_swatch(DIFF_COLORS[2], 6, arrow=True), "One-way"), (_swatch(None, cross=True), "Blocked"),
    (_swatch(DIFF_COLORS[2], 6, halo=HALO["oil"]), "Oil"), (_swatch(DIFF_COLORS[2], 6, halo=HALO["speed"]), "Speed limit"),
]


def draw_legend(surf, rect) -> None:
    """Wraps the legend items into `rect`. Needs roughly 40 px per row."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surf, PANEL, rect, border_radius=8)
    pygame.draw.rect(surf, BORDER, rect, 1, border_radius=8)
    x, y = rect.x + 12, rect.y + 20
    for draw, label in LEGEND_ITEMS:
        width = 40 + font(19).size(label)[0] + 10
        if x + width > rect.right - 6:
            x, y = rect.x + 12, y + 30
        draw(surf, x + 16, y)
        text(surf, label, (x + 38, y), 19, TEXT, "midleft")
        x += width

"""Track graph: vertices, edges and adjacency lists (Project.md 3.1, SPEC 4.5).

Adjacency lists use O(V + E) memory. Dynamic changes (edge effects, service
vertex activation) are O(1) and never rebuild the graph.
"""
from __future__ import annotations

import math
from bisect import insort
from dataclasses import dataclass, field
from typing import Hashable, Iterator

from smart_racing import config

START, FINISH, CHECKPOINT = "Start", "Finish", "Checkpoint"
INTERSECTION, FUEL_STATION, NITRO_PICKUP, DEAD_END = (
    "Intersection", "FuelStation", "NitroPickup", "DeadEnd")
VERTEX_TYPES = (START, FINISH, CHECKPOINT, INTERSECTION, FUEL_STATION, NITRO_PICKUP, DEAD_END)

OPEN, BLOCKED, RESTRICTED = "Open", "Blocked", "Restricted"


@dataclass
class Vertex:
    id: int
    x: float
    y: float
    type: str = INTERSECTION
    checkpoint_order: int | None = None
    active: bool = True            # availability of a service vertex

    @property
    def is_mandatory(self) -> bool:
        return self.type in (START, FINISH, CHECKPOINT)


@dataclass
class Edge:
    """A road. `effects` maps effect id -> effect kind (config.EDGE_EFFECTS).

    Every `effective_*` value and `status` is derived from the active effects,
    so removing one effect never disturbs another (SPEC 4.5). Each derived
    property is O(k) for k active effects on the edge.
    """
    id: int
    src: int
    dst: int
    distance: float
    base_time: float
    fuel_cost: float
    difficulty: int = 1
    is_shortcut: bool = False
    directed: bool = False
    effects: dict[Hashable, str] = field(default_factory=dict)

    def other(self, vertex_id: int) -> int:
        return self.dst if vertex_id == self.src else self.src

    def _active(self, column: int):
        return [config.EDGE_EFFECTS[kind][column] for kind in self.effects.values()]

    @property
    def blocked(self) -> bool:
        return any(self._active(0))

    @property
    def effective_difficulty(self) -> int:
        bump = max(self._active(1), default=0)
        return min(config.MAX_DIFFICULTY, self.difficulty + bump)

    @property
    def time_multiplier(self) -> float:
        return max(self._active(2), default=1.0)

    @property
    def effective_time(self) -> float:
        return self.base_time * self.time_multiplier

    @property
    def effective_fuel(self) -> float:
        step = config.FUEL_DIFFICULTY_STEP
        return self.fuel_cost * (1.0 + step * (self.effective_difficulty - 1))

    @property
    def obstacle_penalty(self) -> float:
        return max(self._active(3), default=0.0)

    @property
    def status(self) -> str:
        if self.blocked:
            return BLOCKED
        return RESTRICTED if self.effects else OPEN


class TrackGraph:
    """Mixed directed/undirected multigraph stored as adjacency lists."""

    def __init__(self) -> None:
        self._vertices: dict[int, Vertex] = {}
        self._edges: dict[int, Edge] = {}
        self._adj: dict[int, list[int]] = {}   # vertex id -> incident edge ids, ascending

    # --- construction -------------------------------------------------------
    def add_vertex(self, id: int, x: float = 0.0, y: float = 0.0, type: str = INTERSECTION,
                   checkpoint_order: int | None = None, active: bool = True) -> Vertex:
        if id in self._vertices:
            raise ValueError(f"duplicate vertex id {id}")
        if type not in VERTEX_TYPES:
            raise ValueError(f"unknown vertex type {type!r}")
        vertex = Vertex(id, x, y, type, checkpoint_order, active)
        self._vertices[id] = vertex
        self._adj[id] = []
        return vertex

    def add_edge(self, id: int, src: int, dst: int, distance: float, base_time: float | None = None,
                 fuel_cost: float | None = None, difficulty: int = 1, is_shortcut: bool = False,
                 directed: bool = False) -> Edge:
        """Add a road. `base_time` and `fuel_cost` default to `distance`. O(deg)."""
        if id in self._edges:
            raise ValueError(f"duplicate edge id {id}")
        if src not in self._vertices or dst not in self._vertices:
            raise ValueError(f"edge {id}: unknown endpoint {src} or {dst}")
        base_time = distance if base_time is None else base_time
        fuel_cost = distance if fuel_cost is None else fuel_cost
        if min(distance, base_time, fuel_cost) < 0:
            raise ValueError(f"edge {id}: distance, time and fuel must be non-negative")
        if not config.MIN_DIFFICULTY <= difficulty <= config.MAX_DIFFICULTY:
            raise ValueError(f"edge {id}: difficulty must be 1..5")
        edge = Edge(id, src, dst, distance, base_time, fuel_cost, difficulty, is_shortcut, directed)
        self._edges[id] = edge
        insort(self._adj[src], id)
        if dst != src:
            insort(self._adj[dst], id)
        return edge

    # --- lookup -------------------------------------------------------------
    def has_vertex(self, vertex_id: int) -> bool:
        return vertex_id in self._vertices

    def has_edge(self, edge_id: int) -> bool:
        return edge_id in self._edges

    def vertex(self, vertex_id: int) -> Vertex:
        return self._vertices[vertex_id]

    def edge(self, edge_id: int) -> Edge:
        return self._edges[edge_id]

    def vertex_ids(self) -> list[int]:
        return sorted(self._vertices)

    def vertices(self) -> list[Vertex]:
        return [self._vertices[i] for i in sorted(self._vertices)]

    def edges(self) -> list[Edge]:
        """Every edge in ascending id order, whatever its status or direction."""
        return [self._edges[i] for i in sorted(self._edges)]

    @property
    def num_vertices(self) -> int:
        return len(self._vertices)

    @property
    def num_edges(self) -> int:
        return len(self._edges)

    def vertices_of_type(self, type: str) -> list[Vertex]:
        return [v for v in self.vertices() if v.type == type]

    def _single(self, type: str) -> Vertex | None:
        found = self.vertices_of_type(type)
        return found[0] if found else None

    @property
    def start(self) -> Vertex | None:
        return self._single(START)

    @property
    def finish(self) -> Vertex | None:
        return self._single(FINISH)

    def checkpoints(self) -> list[Vertex]:
        """Mandatory checkpoints in required order."""
        points = [v for v in self.vertices_of_type(CHECKPOINT) if v.checkpoint_order is not None]
        return sorted(points, key=lambda v: v.checkpoint_order)

    def straight_line(self, a: int, b: int) -> float:
        va, vb = self._vertices[a], self._vertices[b]
        return math.hypot(va.x - vb.x, va.y - vb.y)

    # --- iteration ----------------------------------------------------------
    def incident(self, vertex_id: int) -> Iterator[tuple[Edge, int]]:
        """All `(edge, other endpoint)` pairs at a vertex, ignoring status and
        direction, in ascending edge id order. O(deg)."""
        for edge_id in self._adj[vertex_id]:
            edge = self._edges[edge_id]
            yield edge, edge.other(vertex_id)

    def neighbors(self, vertex_id: int) -> Iterator[tuple[Edge, int]]:
        """Currently traversable `(edge, neighbour)` pairs in ascending edge id
        order: blocked edges and wrong-way one-way edges are skipped. O(deg)."""
        for edge, other in self.incident(vertex_id):
            if edge.blocked or (edge.directed and edge.src != vertex_id):
                continue
            yield edge, other

    # --- dynamic updates (no rebuild) ---------------------------------------
    def add_effect(self, edge_id: int, effect_id: Hashable, kind: str) -> None:
        """Attach an independent effect to an edge. O(1)."""
        if kind not in config.EDGE_EFFECTS:
            raise ValueError(f"unknown effect kind {kind!r}")
        self._edges[edge_id].effects[effect_id] = kind

    def remove_effect(self, edge_id: int, effect_id: Hashable) -> bool:
        """Remove one effect record only. Returns False if it was not active. O(1)."""
        return self._edges[edge_id].effects.pop(effect_id, None) is not None

    def block_edge(self, edge_id: int, effect_id: Hashable = config.EFFECT_BLOCK) -> None:
        self.add_effect(edge_id, effect_id, config.EFFECT_BLOCK)

    def unblock_edge(self, edge_id: int, effect_id: Hashable = config.EFFECT_BLOCK) -> bool:
        return self.remove_effect(edge_id, effect_id)

    def set_vertex_active(self, vertex_id: int, active: bool) -> None:
        self._vertices[vertex_id].active = active

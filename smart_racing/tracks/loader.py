"""Circuit files: JSON <-> TrackGraph plus the per-circuit race data.

File format (one JSON object):
  name                display name
  vertices            [{id, x, y, type, checkpoint_order?, active?}]
  edges               [{id, from, to, distance, base_time, fuel_cost, difficulty,
                        shortcut?, directed?}]
  main_route          vertex ids Start..Finish: Opponent 1's fixed lap
  detour              vertex ids: Opponent 1's fixed bypass, from one main-route
                      vertex to a later one
  opponent_shortcuts  edge ids Opponent 2 takes whenever they are open
  events              [{time, type, target, duration?}] default event script
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from smart_racing import config
from smart_racing.core.graph import TrackGraph

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class Circuit:
    name: str
    graph: TrackGraph
    main_route: list[int] = field(default_factory=list)
    detour: list[int] = field(default_factory=list)
    opponent_shortcuts: list[int] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


def circuit_from_dict(data: dict) -> Circuit:
    """Build a circuit. Bad data raises KeyError/ValueError from the graph. O(V + E)."""
    graph = TrackGraph()
    for v in data["vertices"]:
        graph.add_vertex(v["id"], v["x"], v["y"], v["type"], v.get("checkpoint_order"),
                         v.get("active", True))
    for e in data["edges"]:
        graph.add_edge(e["id"], e["from"], e["to"], e["distance"], e["base_time"], e["fuel_cost"],
                       e["difficulty"], e.get("shortcut", False), e.get("directed", False))
    return Circuit(data["name"], graph, list(data.get("main_route", [])),
                   list(data.get("detour", [])), list(data.get("opponent_shortcuts", [])),
                   [dict(event) for event in data.get("events", [])])


def circuit_to_dict(circuit: Circuit) -> dict:
    """The base track: active edge effects are not saved. O(V + E)."""
    vertices = []
    for v in circuit.graph.vertices():
        record = {"id": v.id, "x": v.x, "y": v.y, "type": v.type}
        if v.checkpoint_order is not None:
            record["checkpoint_order"] = v.checkpoint_order
        if not v.active:
            record["active"] = False
        vertices.append(record)
    edges = []
    for e in circuit.graph.edges():
        record = {"id": e.id, "from": e.src, "to": e.dst, "distance": e.distance,
                  "base_time": e.base_time, "fuel_cost": e.fuel_cost, "difficulty": e.difficulty}
        if e.is_shortcut:
            record["shortcut"] = True
        if e.directed:
            record["directed"] = True
        edges.append(record)
    return {"name": circuit.name, "vertices": vertices, "edges": edges,
            "main_route": list(circuit.main_route), "detour": list(circuit.detour),
            "opponent_shortcuts": list(circuit.opponent_shortcuts),
            "events": [dict(event) for event in circuit.events]}


def load_circuit(path: str | Path) -> Circuit:
    with open(path, encoding="utf-8") as handle:
        return circuit_from_dict(json.load(handle))


def save_circuit(circuit: Circuit, path: str | Path) -> None:
    """Write the circuit with one vertex, edge or event per line."""
    data = circuit_to_dict(circuit)
    parts = []
    for key, value in data.items():
        if key in ("vertices", "edges", "events") and value:
            rows = ",\n".join("    " + json.dumps(row) for row in value)
            parts.append(f'  "{key}": [\n{rows}\n  ]')
        else:
            parts.append(f'  "{key}": {json.dumps(value)}')
    Path(path).write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8")


def list_circuits() -> list[str]:
    """Names of the built-in circuits in championship order."""
    return list(config.BUILTIN_CIRCUITS)


def load_builtin(name: str) -> Circuit:
    if name not in config.BUILTIN_CIRCUITS:
        raise ValueError(f"unknown circuit {name!r}; choose from {config.BUILTIN_CIRCUITS}")
    return load_circuit(DATA_DIR / f"{name}.json")


def route_edges(graph: TrackGraph, vertex_path: list[int]) -> list[int]:
    """Edge ids along a vertex path: for each step the lowest-id road that may
    be driven in that direction (blockages are ignored, one-way roads are not).
    Raises ValueError when two consecutive vertices are not joined. O(sum deg)."""
    edges = []
    for u, w in zip(vertex_path, vertex_path[1:]):
        for edge, other in graph.incident(u):
            if other == w and not (edge.directed and edge.src != u):
                edges.append(edge.id)
                break
        else:
            raise ValueError(f"no road from vertex {u} to vertex {w}")
    return edges

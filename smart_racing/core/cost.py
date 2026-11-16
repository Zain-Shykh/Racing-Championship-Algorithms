"""Scalar edge cost (SPEC 4.3): cost = wD*D/Dref + wT*T/Tref + wF*F/Fref + wR*R + wO*O.

Every term and weight is non-negative, so Dijkstra applies. All functions are O(1)
per edge and read the edge's *effective* values, so costs follow active events.
"""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

from smart_racing import config
from smart_racing.core.graph import Edge, TrackGraph

CostFn = Callable[[Edge], float]


def cost_components(edge: Edge) -> tuple[float, float, float, float, float]:
    """Normalized (D, T, F, R, O) of an edge."""
    span = config.MAX_DIFFICULTY - config.MIN_DIFFICULTY
    return (
        edge.distance / config.DIST_REF,
        edge.effective_time / config.TIME_REF,
        edge.effective_fuel / config.FUEL_REF,
        (edge.effective_difficulty - config.MIN_DIFFICULTY) / span,
        edge.obstacle_penalty,
    )


def resolve_weights(weights: str | Sequence[float]) -> tuple[float, ...]:
    """Preset name or (wD, wT, wF, wR, wO) -> validated weight tuple."""
    resolved = tuple(config.COST_PRESETS[weights] if isinstance(weights, str) else weights)
    if len(resolved) != 5 or min(resolved) < 0:
        raise ValueError("weights must be five non-negative numbers (wD, wT, wF, wR, wO)")
    return resolved


def edge_cost(edge: Edge, weights: str | Sequence[float] = "Balanced") -> float:
    return sum(w * c for w, c in zip(resolve_weights(weights), cost_components(edge)))


def make_cost_fn(weights: str | Sequence[float] = "Balanced") -> CostFn:
    """Cost function for Dijkstra/A* from a preset name or a weight tuple."""
    resolved = resolve_weights(weights)
    return lambda edge: sum(w * c for w, c in zip(resolved, cost_components(edge)))


def distance_cost(edge: Edge) -> float:
    """Distance-only routing (opponent 3)."""
    return edge.distance


def time_cost(edge: Edge) -> float:
    return edge.effective_time


def route_summary(graph: TrackGraph, edge_path: Iterable[int], cost_fn: CostFn) -> dict[str, float]:
    """Totals shown to the player for a route given as edge ids. O(len(path))."""
    edges = [graph.edge(edge_id) for edge_id in edge_path]
    return {
        "distance": sum(e.distance for e in edges),
        "time": sum(e.effective_time for e in edges),
        "fuel": sum(e.effective_fuel for e in edges),
        "cost": sum(cost_fn(e) for e in edges),
    }

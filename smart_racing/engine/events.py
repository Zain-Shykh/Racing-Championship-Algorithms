"""Race event queue (Project.md 4.5, SPEC 4.5): a min-heap of events keyed
`(trigger_time, priority, insertion_sequence)` that mutates the track graph.

Every effect is an independent record keyed by the id of the event that
created it, so overlapping effects compose and ending one never erases
another. Cancellation is lazy: a cancelled event stays in the heap and is
skipped when it reaches the top (simple, O(1) to cancel, at the price of dead
entries occupying heap memory until their trigger time).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable, Iterable

from smart_racing import config as C
from smart_racing.algorithms.heap import MinHeap
from smart_racing.core.graph import FUEL_STATION, NITRO_PICKUP, TrackGraph
from smart_racing.core.models import Event

EDGE_EVENTS = (C.EVENT_ROAD_BLOCK, C.EVENT_ROAD_CLEAR, C.EVENT_SHORTCUT_OPEN,
               C.EVENT_SHORTCUT_CLOSE, C.EVENT_OIL_SPILL, C.EVENT_SPEED_RESTRICTION)
# event type -> (edge effect kind, feed text when it starts, feed text when it expires)
_EDGE_EFFECT = {
    C.EVENT_ROAD_BLOCK: (C.EFFECT_BLOCK, "Road blocked", "Road reopened"),
    C.EVENT_SHORTCUT_CLOSE: (C.EFFECT_BLOCK, "Shortcut closed", "Shortcut reopened"),
    C.EVENT_OIL_SPILL: (C.EFFECT_OIL, "Oil spill", "Oil spill cleaned up"),
    C.EVENT_SPEED_RESTRICTION: (C.EFFECT_SPEED, "Speed restriction", "Speed restriction lifted"),
}
# reversing event -> (event type whose effects it ends, feed text, reason when there is nothing to end)
_REVERSES = {
    C.EVENT_ROAD_CLEAR: (C.EVENT_ROAD_BLOCK, "Road reopened", "is not blocked"),
    C.EVENT_SHORTCUT_OPEN: (C.EVENT_SHORTCUT_CLOSE, "Shortcut reopened", "is already open"),
}


@dataclass
class EventRecord:
    """One processed event, for the engine (who must re-plan) and the event feed."""
    event: Event
    applied: bool
    description: str      # feed line when applied, rejection reason otherwise
    target_kind: str      # "edge" or "vertex"

    @property
    def target(self) -> Hashable:
        return self.event.target


class EventQueue:
    """Schedule O(log n), cancel O(1), pop O(log n) per event."""

    def __init__(self, graph: TrackGraph) -> None:
        self.graph = graph
        self.heap = MinHeap()                       # counters used by Experiment 4
        self.applied: list[EventRecord] = []        # full history, in application order
        self.rejected: list[EventRecord] = []       # events refused, with the reason
        self._pending: dict[int, Event] = {}        # live (not cancelled, not popped) events
        self._next_id = 1
        self._sequence = 0
        self._active: dict[tuple[str, Hashable], list[int]] = {}   # (event type, target) -> effect ids
        self._expiry_of: dict[int, int] = {}        # effect id -> its pending expiry event id
        self._expires: dict[int, tuple[str, int]] = {}             # expiry event id -> (event type, effect id)

    # --- scheduling -----------------------------------------------------------
    def schedule(self, type: str, trigger_time: float, target: Hashable,
                 duration: float | None = None) -> Event:
        """Queue an event. `duration=None` takes the default of
        `config.EVENT_DURATION`; `math.inf` means "no automatic expiry".
        The target is checked when the event fires, not here."""
        if type not in C.EVENT_PRIORITY:
            raise ValueError(f"unknown event type {type!r}")
        if duration is None:
            duration = C.EVENT_DURATION[type]
        return self._push(type, trigger_time, target, duration, C.EVENT_PRIORITY[type])

    def _push(self, type, trigger_time, target, duration, priority) -> Event:
        event = Event(self._next_id, type, float(trigger_time), priority, self._sequence,
                      target, duration)
        self._next_id += 1
        self._sequence += 1
        self._pending[event.event_id] = event
        self.heap.push(event.key, event)
        return event

    def cancel(self, event_id: int) -> bool:
        """Lazy deletion. False if the event is not pending."""
        event = self._pending.pop(event_id, None)
        if event is None:
            return False
        event.cancelled = True
        return True

    def load_script(self, events: Iterable[dict]) -> list[Event]:
        """Schedule a circuit's event list: dicts with time, type, target, optional duration."""
        return [self.schedule(e["type"], e["time"], e["target"], e.get("duration")) for e in events]

    # --- inspection -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._pending)

    def has_pending_changes(self) -> bool:
        """True while a live event could still change the graph (SPEC 4.6: a
        stuck racer keeps waiting only while this holds)."""
        return bool(self._pending)

    def pending(self) -> list[Event]:
        """Live events in firing order. O(n log n)."""
        return sorted(self._pending.values(), key=lambda event: event.key)

    def next_time(self) -> float | None:
        """Trigger time of the next live event, dropping cancelled heap tops."""
        while self.heap and self.heap.peek()[1].cancelled:
            self.heap.pop()
        return self.heap.peek()[1].trigger_time if self.heap else None

    # --- processing -----------------------------------------------------------
    def pop_due(self, now: float) -> list[EventRecord]:
        """Apply every live event with `trigger_time <= now` in heap order and
        return the applied ones. Rejected events go to `self.rejected` and
        change nothing. An expiry that falls due within `now` is processed in
        the same call."""
        done = []
        while self.heap and self.heap.peek()[0][0] <= now:
            _, event = self.heap.pop()
            if event.cancelled:
                continue
            del self._pending[event.event_id]
            kind = "edge" if event.type in EDGE_EVENTS else "vertex"
            if event.type == C.EVENT_EXPIRE:
                kind = "edge" if self._expires[event.event_id][0] in EDGE_EVENTS else "vertex"
            ok, text = self._apply(event)
            record = EventRecord(event, ok, text, kind)
            (done if ok else self.rejected).append(record)
        self.applied.extend(done)
        return done

    def collect_nitro(self, vertex_id: int, now: float, respawn: bool = True) -> Event | None:
        """A racer took the pickup: deactivate it, drop its pending booster
        expiry, and (SPEC 4.2) schedule a lasting respawn after NITRO_RESPAWN_TIME."""
        for effect_id in self._active.pop((C.EVENT_NITRO_SPAWN, vertex_id), []):
            self.cancel(self._expiry_of.pop(effect_id, -1))
        self.graph.set_vertex_active(vertex_id, False)
        if not respawn:
            return None
        return self.schedule(C.EVENT_NITRO_SPAWN, now + C.NITRO_RESPAWN_TIME, vertex_id, math.inf)

    # --- effects --------------------------------------------------------------
    def _edge_label(self, edge_id) -> str:
        edge = self.graph.edge(edge_id)
        return f"road {edge_id} ({edge.src}-{edge.dst})"

    def _start(self, event: Event) -> None:
        """Record the effect of `event` and schedule its expiry if it is temporary."""
        self._active.setdefault((event.type, event.target), []).append(event.event_id)
        if event.duration is not None and event.duration != math.inf:
            expiry = self._push(C.EVENT_EXPIRE, event.trigger_time + event.duration,
                                event.target, None, event.priority)
            self._expiry_of[event.event_id] = expiry.event_id
            self._expires[expiry.event_id] = (event.type, event.event_id)

    def _apply(self, event: Event) -> tuple[bool, str]:
        g, kind, target = self.graph, event.type, event.target
        if kind == C.EVENT_EXPIRE:
            return self._expire(event)
        if kind in EDGE_EVENTS:
            if not g.has_edge(target):
                return False, f"{kind}: road {target} does not exist"
            label = self._edge_label(target)
            if kind in _REVERSES:
                source, text, problem = _REVERSES[kind]
                if source == C.EVENT_SHORTCUT_CLOSE and not g.edge(target).is_shortcut:
                    return False, f"{kind}: {label} is not a shortcut"
                effect_ids = self._active.pop((source, target), [])
                if not effect_ids:
                    return False, f"{kind}: {label} {problem}"
                for effect_id in effect_ids:
                    g.remove_effect(target, effect_id)
                    self.cancel(self._expiry_of.pop(effect_id, -1))
                return True, f"{text}: {label}"
            if kind == C.EVENT_SHORTCUT_CLOSE and not g.edge(target).is_shortcut:
                return False, f"{kind}: {label} is not a shortcut"
            if kind in (C.EVENT_ROAD_BLOCK, C.EVENT_SHORTCUT_CLOSE) and self._active.get((kind, target)):
                return False, f"{kind}: {label} is already closed by an earlier {kind}"
            effect, text, _ = _EDGE_EFFECT[kind]
            g.add_effect(target, event.event_id, effect)
            self._start(event)
            return True, f"{text}: {label}"
        if not g.has_vertex(target):
            return False, f"{kind}: vertex {target} does not exist"
        vertex = g.vertex(target)
        if kind == C.EVENT_STATION_OUTAGE:
            if vertex.type != FUEL_STATION:
                return False, f"{kind}: vertex {target} is not a fuel station"
            g.set_vertex_active(target, False)
            self._start(event)
            return True, f"Fuel station {target} out of service"
        if vertex.type != NITRO_PICKUP:
            return False, f"{kind}: vertex {target} is not a nitro pickup"
        if vertex.active:
            return False, f"{kind}: nitro pickup {target} is already active"
        g.set_vertex_active(target, True)
        self._start(event)
        return True, f"Nitro booster available at vertex {target}"

    def _expire(self, event: Event) -> tuple[bool, str]:
        """Remove exactly the one effect this expiry belongs to."""
        source, effect_id = self._expires.pop(event.event_id)
        target = event.target
        del self._expiry_of[effect_id]
        remaining = self._active[(source, target)]
        remaining.remove(effect_id)
        if not remaining:
            del self._active[(source, target)]
        if source in _EDGE_EFFECT:
            self.graph.remove_effect(target, effect_id)
            return True, f"{_EDGE_EFFECT[source][2]}: {self._edge_label(target)}"
        if source == C.EVENT_STATION_OUTAGE:
            if remaining:                      # another outage still holds the station closed
                return True, f"Fuel station {target}: one outage over, still out of service"
            self.graph.set_vertex_active(target, True)
            return True, f"Fuel station {target} back in service"
        self.graph.set_vertex_active(target, False)
        return True, f"Nitro booster at vertex {target} expired"

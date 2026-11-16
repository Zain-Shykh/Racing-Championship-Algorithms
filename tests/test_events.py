"""EventQueue: ordering, ties, cancellation, expiry, validation, overlapping effects."""
import math

import pytest

from smart_racing import config as C
from smart_racing.core.graph import BLOCKED, OPEN, RESTRICTED, TrackGraph
from smart_racing.engine.events import EventQueue


def track():
    """0 -1- 1 -2- 2 plus shortcut 3 (0-2); vertex 3 is a station, 4 an inactive nitro pickup."""
    g = TrackGraph()
    for vid, kind, active in ((0, "Start", True), (1, "Intersection", True), (2, "Finish", True),
                              (3, "FuelStation", True), (4, "NitroPickup", False)):
        g.add_vertex(vid, vid * 10.0, 0.0, kind, active=active)
    g.add_edge(1, 0, 1, 10, difficulty=2)
    g.add_edge(2, 1, 2, 10)
    g.add_edge(3, 0, 2, 15, is_shortcut=True)
    return g, EventQueue(g)


def test_pop_order_is_time_then_priority_then_insertion():
    g, q = track()
    late = q.schedule(C.EVENT_OIL_SPILL, 9.0, 1)
    speed = q.schedule(C.EVENT_SPEED_RESTRICTION, 5.0, 1)       # priority 4
    block = q.schedule(C.EVENT_ROAD_BLOCK, 5.0, 2)              # priority 1: first at t=5
    oil_a = q.schedule(C.EVENT_OIL_SPILL, 5.0, 1)               # priority 3
    oil_b = q.schedule(C.EVENT_OIL_SPILL, 5.0, 2)               # same key but later insertion
    assert [e.event_id for e in q.pending()] == [block.event_id, oil_a.event_id, oil_b.event_id,
                                                 speed.event_id, late.event_id]
    assert q.next_time() == 5.0
    assert q.pop_due(4.9) == []
    done = q.pop_due(5.0)                                       # the whole batch of simultaneous events
    assert [r.event for r in done] == [block, oil_a, oil_b, speed]
    assert [r.event.insertion_sequence for r in done] == [2, 3, 4, 1]
    assert all(r.applied and r.target_kind == "edge" and r.description for r in done)
    assert "Road blocked" in done[0].description and "road 2 (1-2)" in done[0].description
    assert [r.event for r in q.pop_due(9.0)] == [late]
    assert q.applied[:4] == done


def test_cancelled_events_are_skipped_lazily():
    g, q = track()
    a = q.schedule(C.EVENT_ROAD_BLOCK, 1.0, 1)
    b = q.schedule(C.EVENT_ROAD_BLOCK, 2.0, 2)
    assert q.cancel(a.event_id) and not q.cancel(a.event_id) and not q.cancel(999)
    assert a.cancelled and len(q) == 1 and len(q.heap) == 2     # still in the heap
    assert q.next_time() == 2.0 and len(q.heap) == 1            # dropped when it reached the top
    assert [r.event for r in q.pop_due(10)] == [b]
    assert not g.edge(1).blocked and g.edge(2).blocked
    assert not q.has_pending_changes() and q.next_time() is None


def test_temporary_effect_schedules_its_own_expiry():
    g, q = track()
    oil = q.schedule(C.EVENT_OIL_SPILL, 10.0, 1)
    assert oil.duration == C.EVENT_DURATION[C.EVENT_OIL_SPILL] == 20.0
    q.pop_due(10.0)
    edge = g.edge(1)
    assert edge.status == RESTRICTED and edge.effective_difficulty == 4 and edge.time_multiplier == 1.5
    (expiry,) = q.pending()
    assert (expiry.type, expiry.trigger_time, expiry.priority) == (C.EVENT_EXPIRE, 30.0, oil.priority)
    assert q.has_pending_changes()
    assert q.pop_due(29.9) == []
    (record,) = q.pop_due(30.0)
    assert record.target_kind == "edge" and "cleaned up" in record.description
    assert edge.status == OPEN and edge.effects == {} and not q.has_pending_changes()


def test_expiry_falling_due_in_the_same_call_is_processed():
    g, q = track()
    q.schedule(C.EVENT_SPEED_RESTRICTION, 0.0, 1, duration=5.0)
    assert [r.event.type for r in q.pop_due(100.0)] == [C.EVENT_SPEED_RESTRICTION, C.EVENT_EXPIRE]
    assert g.edge(1).status == OPEN


@pytest.mark.parametrize("kind,target,reason", [
    (C.EVENT_ROAD_BLOCK, 99, "road 99 does not exist"),
    (C.EVENT_OIL_SPILL, None, "does not exist"),
    (C.EVENT_STATION_OUTAGE, 99, "vertex 99 does not exist"),
    (C.EVENT_ROAD_CLEAR, 1, "is not blocked"),
    (C.EVENT_SHORTCUT_CLOSE, 1, "is not a shortcut"),
    (C.EVENT_SHORTCUT_OPEN, 3, "is already open"),
    (C.EVENT_STATION_OUTAGE, 1, "is not a fuel station"),
    (C.EVENT_NITRO_SPAWN, 3, "is not a nitro pickup"),
])
def test_missing_target_or_invalid_state_is_rejected_with_a_reason(kind, target, reason):
    g, q = track()
    q.schedule(kind, 1.0, target)
    assert q.pop_due(1.0) == [] and q.applied == []
    (record,) = q.rejected
    assert not record.applied and reason in record.description
    assert all(e.effects == {} for e in g.edges()) and len(q) == 0     # no effect, no expiry scheduled


def test_double_block_and_double_spawn_are_rejected():
    g, q = track()
    for kind, target in ((C.EVENT_ROAD_BLOCK, 1), (C.EVENT_ROAD_BLOCK, 1),
                         (C.EVENT_NITRO_SPAWN, 4), (C.EVENT_NITRO_SPAWN, 4)):
        q.schedule(kind, 1.0, target)
    assert len(q.pop_due(1.0)) == 2
    assert ["already closed" in r.description or "already active" in r.description for r in q.rejected] == [True, True]
    with pytest.raises(ValueError):
        q.schedule("meteor", 1.0, 1)


def test_overlapping_effects_compose_and_expire_independently():
    g, q = track()
    edge = g.edge(1)                                    # base difficulty 2
    q.schedule(C.EVENT_OIL_SPILL, 0.0, 1)               # until 20
    q.schedule(C.EVENT_SPEED_RESTRICTION, 10.0, 1)      # until 25
    q.schedule(C.EVENT_OIL_SPILL, 15.0, 1)              # until 35
    q.schedule(C.EVENT_ROAD_BLOCK, 16.0, 1)
    q.pop_due(16.0)
    assert len(edge.effects) == 4 and edge.status == BLOCKED
    assert edge.effective_difficulty == 4 and edge.time_multiplier == 1.5 and edge.obstacle_penalty == 1.0
    q.pop_due(20.0)                                     # first oil gone, second still there
    assert len(edge.effects) == 3 and edge.effective_difficulty == 4
    q.schedule(C.EVENT_ROAD_CLEAR, 22.0, 1)
    q.pop_due(22.0)
    assert edge.status == RESTRICTED and not edge.blocked
    q.pop_due(25.0)                                     # speed restriction gone, oil keeps the multiplier
    assert list(edge.effects.values()) == [C.EFFECT_OIL] and edge.time_multiplier == 1.5
    q.pop_due(35.0)
    assert edge.status == OPEN and edge.effective_difficulty == 2 and q.rejected == []


def test_road_block_and_shortcut_close_are_separate_blocks():
    g, q = track()
    q.schedule(C.EVENT_SHORTCUT_CLOSE, 1.0, 3)
    q.schedule(C.EVENT_ROAD_BLOCK, 2.0, 3)
    q.schedule(C.EVENT_SHORTCUT_OPEN, 3.0, 3)
    q.pop_due(3.0)
    assert g.edge(3).blocked                            # the road block is still active
    q.schedule(C.EVENT_ROAD_CLEAR, 4.0, 3)
    q.pop_due(4.0)
    assert g.edge(3).status == OPEN and q.rejected == []


def test_timed_block_is_ended_early_by_a_clear_and_its_expiry_dropped():
    g, q = track()
    q.schedule(C.EVENT_ROAD_BLOCK, 0.0, 1, duration=50.0)
    q.schedule(C.EVENT_ROAD_CLEAR, 10.0, 1)
    q.pop_due(10.0)
    assert not g.edge(1).blocked and not q.has_pending_changes()
    assert q.pop_due(60.0) == [] and q.rejected == []


def test_station_outages_overlap():
    g, q = track()
    q.schedule(C.EVENT_STATION_OUTAGE, 0.0, 3)          # until 30
    q.schedule(C.EVENT_STATION_OUTAGE, 20.0, 3)         # until 50
    q.pop_due(20.0)
    assert not g.vertex(3).active
    (record,) = q.pop_due(30.0)
    assert record.target_kind == "vertex" and not g.vertex(3).active
    q.pop_due(50.0)
    assert g.vertex(3).active


def test_nitro_booster_expires_or_is_collected():
    g, q = track()
    q.schedule(C.EVENT_NITRO_SPAWN, 5.0, 4)
    q.pop_due(5.0)
    assert g.vertex(4).active
    q.pop_due(30.0)                                     # 25 s later, nobody took it
    assert not g.vertex(4).active

    q.schedule(C.EVENT_NITRO_SPAWN, 40.0, 4)
    q.pop_due(40.0)
    respawn = q.collect_nitro(4, 45.0)
    assert not g.vertex(4).active
    assert (respawn.trigger_time, respawn.duration) == (45.0 + C.NITRO_RESPAWN_TIME, math.inf)
    assert [e.event_id for e in q.pending()] == [respawn.event_id]      # booster expiry was cancelled
    q.pop_due(200.0)
    assert g.vertex(4).active and not q.has_pending_changes() and q.rejected == []
    assert q.collect_nitro(4, 210.0, respawn=False) is None and not g.vertex(4).active


def test_load_script_and_heap_counters():
    g, q = track()
    events = q.load_script([{"time": 3, "type": C.EVENT_ROAD_BLOCK, "target": 1},
                            {"time": 1, "type": C.EVENT_OIL_SPILL, "target": 2, "duration": 4}])
    assert [e.event_id for e in events] == [1, 2] and [e.insertion_sequence for e in events] == [0, 1]
    assert events[1].duration == 4 and q.heap.pushes == 2
    assert [r.event.type for r in q.pop_due(5)] == [C.EVENT_OIL_SPILL, C.EVENT_ROAD_BLOCK, C.EVENT_EXPIRE]

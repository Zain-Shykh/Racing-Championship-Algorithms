"""Plain records of Project.md section 3.2."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable

from smart_racing import config


@dataclass
class Racer:
    id: int
    name: str
    is_human: bool = False
    strategy_type: str = "human"
    current_vertex: int | None = None
    fuel: float = config.TANK_CAPACITY
    nitro_charges: int = config.NITRO_START_CHARGES
    lap: int = 0                   # laps completed
    next_checkpoint: int = 1       # checkpoint_order the racer must reach next
    total_time: float = 0.0


@dataclass
class RaceResult:
    race_id: int
    racer_id: int
    finish_position: int
    finish_time: float | None      # None = did not finish
    fastest_lap: float | None
    bonus_points: int = 0
    points_awarded: int = 0


@dataclass
class ChampionshipEntry:
    racer_id: int
    total_points: int = 0
    wins: int = 0
    sum_of_finish_positions: int = 0
    best_fastest_lap: float = math.inf


@dataclass
class Event:
    event_id: int
    type: str
    trigger_time: float
    priority: int
    insertion_sequence: int
    target: Hashable               # edge id or vertex id
    duration: float | None = None
    cancelled: bool = False

    @property
    def key(self) -> tuple[float, int, int]:
        """Min-heap key (SPEC 4.5)."""
        return (self.trigger_time, self.priority, self.insertion_sequence)

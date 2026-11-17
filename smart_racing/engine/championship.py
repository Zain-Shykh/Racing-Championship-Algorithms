"""Championship (Project.md 4.6 and 5.5, SPEC 4.7): race results, points,
standings by the three sorts with the one comparator, and heap top-k.

Run `python -m smart_racing.engine.championship` for a headless championship.
"""
from __future__ import annotations

from smart_racing import config
from smart_racing.algorithms.sorting import SortResult, heap_sort, merge_sort, quick_sort
from smart_racing.algorithms.topk import TopKResult, top_k
from smart_racing.core.models import ChampionshipEntry, RaceResult
from smart_racing.engine.race import FINISHED, RaceEngine, RacerSpec, create_race, default_racers

SORTS = {"merge": merge_sort, "quick": quick_sort, "heap": heap_sort}


def score_race(race_id: int, engine: RaceEngine) -> list[RaceResult]:
    """Results in finishing order. Points go to finishers only; the bonus goes
    to the finisher with the fastest lap among finishers (ties: lower id)."""
    order = engine.classification()
    finishers = [r for r in order if r.status == FINISHED]
    best = min(finishers, key=lambda r: (r.fastest_lap, r.id), default=None)
    results = []
    for position, r in enumerate(order, start=1):
        done = r.status == FINISHED
        points = config.POINTS_TABLE[position - 1] if done and position <= len(config.POINTS_TABLE) else 0
        results.append(RaceResult(race_id, r.id, position, r.finish_time, r.fastest_lap,
                                  config.FASTEST_LAP_BONUS if r is best else 0, points))
    return results


class Championship:
    """The circuits in fixed order with running standings.

    Typical use: `race = champ.next_race()`, drive it (GUI or
    `run_to_completion()`), `champ.record(race)`, repeat until `champ.finished`.
    """

    def __init__(self, circuits=config.BUILTIN_CIRCUITS, laps: int = config.LAPS_PER_RACE,
                 preset: str = "Balanced", racers: list[RacerSpec] | None = None, **race_options) -> None:
        self.circuits = list(circuits)
        self.laps, self.preset, self.race_options = laps, preset, race_options
        self.specs = default_racers() if racers is None else [RacerSpec(*s) for s in racers]
        self.names = {i: spec.name for i, spec in enumerate(self.specs)}
        self.entries = {i: ChampionshipEntry(i) for i in self.names}
        self.results: list[list[RaceResult]] = []      # one list per recorded race
        self.races: list[RaceEngine] = []              # the recorded engines, for statistics

    @property
    def race_number(self) -> int:
        """1-based number of the next race to run."""
        return len(self.results) + 1

    @property
    def finished(self) -> bool:
        return len(self.results) >= len(self.circuits)

    def next_race(self) -> RaceEngine | None:
        """A fresh engine for the next circuit, or None after the last race."""
        if self.finished:
            return None
        return create_race(self.circuits[len(self.results)], self.laps, self.preset, self.specs,
                           **self.race_options)

    def record(self, engine: RaceEngine) -> list[RaceResult]:
        """Score a finished race and update every ChampionshipEntry. O(n log n)."""
        if not engine.finished:
            raise ValueError("the race is still running")
        results = score_race(self.race_number, engine)
        for res in results:
            entry = self.entries[res.racer_id]
            entry.total_points += res.points_awarded + res.bonus_points
            entry.wins += res.finish_position == 1 and res.finish_time is not None
            entry.sum_of_finish_positions += res.finish_position
            if res.fastest_lap is not None:
                entry.best_fastest_lap = min(entry.best_fastest_lap, res.fastest_lap)
        self.results.append(results)
        self.races.append(engine)
        return results

    def standings(self, algorithm: str = "merge") -> SortResult:
        """Entries best first by "merge" (default), "quick" or "heap" sort;
        `.comparisons` is the comparator-call count."""
        return SORTS[algorithm](list(self.entries.values()))

    def top(self, k: int) -> TopKResult:
        """Leading `k` entries by the size-k heap, without a full sort."""
        return top_k(self.entries.values(), k)

    @property
    def champion(self) -> ChampionshipEntry | None:
        """The leader once every race is recorded."""
        return self.standings().items[0] if self.finished and self.entries else None

    def run(self) -> "Championship":
        """Simulate every remaining race headless."""
        while not self.finished:
            self.record(self.next_race().run_to_completion())
        return self


def summary(champ: Championship) -> str:
    """One-screen text summary of the recorded races and the standings."""
    lines = []
    for engine, results in zip(champ.races, champ.results):
        lines.append(f"Race {results[0].race_id}: {engine.circuit.name}  ({engine.laps} laps, "
                     f"{len(engine.feed)} track events, clock {engine.clock:.2f} s)")
        for res in results:
            r = engine.racer(res.racer_id)
            time = f"{res.finish_time:8.2f} s" if res.finish_time is not None else f"{r.status.upper():>10}"
            lap = f"{res.fastest_lap:7.2f}" if res.fastest_lap is not None else "      -"
            lines.append(f"  {res.finish_position}. {r.name:<11} {time}  best lap {lap}  "
                         f"fuel stops {r.fuel_stops}  reroutes {r.reroutes}  nitro {r.nitro_used}  "
                         f"waited {r.waited:5.1f} s  pts {res.points_awarded}+{res.bonus_points}")
    table = champ.standings()
    lines.append(f"Standings (merge sort, {table.comparisons} comparisons)")
    for place, e in enumerate(table.items, start=1):
        lines.append(f"  {place}. {champ.names[e.racer_id]:<11} {e.total_points:3d} pts  wins {e.wins}  "
                     f"position sum {e.sum_of_finish_positions}  best lap {e.best_fastest_lap:.2f}")
    if champ.champion:
        lines.append(f"Champion: {champ.names[champ.champion.racer_id]}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(Championship().run()))

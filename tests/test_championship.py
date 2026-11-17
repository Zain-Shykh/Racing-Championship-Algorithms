"""Phase 4: scoring, standings by three sorts, top-k and the full championship."""
import pytest

from smart_racing import config as C
from smart_racing.algorithms.sorting import championship_less
from smart_racing.engine.championship import SORTS, Championship, score_race, summary
from smart_racing.engine.race import DNF, FINISHED, create_race, default_racers


@pytest.fixture(scope="module")
def champ():
    return Championship().run()


def test_full_three_race_championship(champ):
    assert champ.finished and champ.next_race() is None and champ.race_number == 4
    assert [e.circuit.name for e in champ.races] == ["Harbor Eight", "Grand Ring", "Serpent Pass"]
    for number, results in enumerate(champ.results, start=1):
        assert [r.race_id for r in results] == [number] * 4
        assert [r.finish_position for r in results] == [1, 2, 3, 4]
        assert [r.points_awarded for r in results] == list(C.POINTS_TABLE[:4])
        assert [r.finish_time for r in results] == sorted(r.finish_time for r in results)
        assert sum(r.bonus_points for r in results) == C.FASTEST_LAP_BONUS
        holder = next(r for r in results if r.bonus_points)
        assert holder.fastest_lap == min(r.fastest_lap for r in results)
    for racer_id, entry in champ.entries.items():
        mine = [r for results in champ.results for r in results if r.racer_id == racer_id]
        assert entry.total_points == sum(r.points_awarded + r.bonus_points for r in mine)
        assert entry.wins == sum(r.finish_position == 1 for r in mine)
        assert entry.sum_of_finish_positions == sum(r.finish_position for r in mine)
        assert entry.best_fastest_lap == min(r.fastest_lap for r in mine)
    assert sum(e.wins for e in champ.entries.values()) == 3


def test_all_sorts_agree_and_top_k_is_the_prefix(champ):
    table = champ.standings()
    assert table.algorithm.lower().startswith("merge") and table.comparisons > 0
    ranked = table.items
    assert all(championship_less(a, b) for a, b in zip(ranked, ranked[1:]))
    for name in SORTS:
        other = champ.standings(name)
        assert other.items == ranked and other.comparisons > 0
    for k in range(0, 6):
        assert champ.top(k).items == ranked[:k]
    assert champ.champion is ranked[0]
    assert champ.names[champ.champion.racer_id] in summary(champ)


def test_championship_is_deterministic_and_stepwise(champ):
    again = Championship()
    assert again.champion is None and not again.finished
    race = again.next_race()
    with pytest.raises(ValueError):
        again.record(race)                           # still running
    again.record(race.run_to_completion())
    assert again.race_number == 2 and again.champion is None
    again.run()
    assert again.results == champ.results
    assert again.standings().items == champ.standings().items


def test_unfinished_racers_score_nothing():
    engine = create_race("grand_ring", time_limit=120.0).run_to_completion()
    results = score_race(1, engine)
    assert all(r.finish_time is None and r.points_awarded == 0 and r.bonus_points == 0 for r in results)
    order = [engine.racer(r.racer_id) for r in results]
    keys = [(-r.lap, -r.checkpoints_done, r.end_time, r.id) for r in order]
    assert keys == sorted(keys) and len(set(keys)) == 4
    champ = Championship(circuits=["grand_ring"], time_limit=120.0).run()
    assert all(e.total_points == 0 and e.wins == 0 for e in champ.entries.values())
    assert [e.racer_id for e in champ.standings().items] == [r.racer_id for r in results]  # position sums decide


def test_finishers_rank_ahead_of_dnf_and_bonus_needs_a_finish():
    block = [{"time": 90, "type": C.EVENT_ROAD_BLOCK, "target": e} for e in range(35)]
    engine = create_race("harbor_eight", laps=1, events=block).run_to_completion()
    done = [r for r in engine.racers if r.status == FINISHED]
    out = [r for r in engine.racers if r.status == DNF]
    assert done and out                               # some were home before the track closed
    results = score_race(7, engine)
    assert [r.finish_time is not None for r in results] == [True] * len(done) + [False] * len(out)
    assert [r.points_awarded for r in results] == list(C.POINTS_TABLE[:len(done)]) + [0] * len(out)
    assert sum(r.bonus_points for r in results) == 1 and results[0].race_id == 7


def test_ten_racer_championship_uses_the_whole_points_table():
    champ = Championship(circuits=["grand_ring"], racers=default_racers(9)).run()
    assert [r.points_awarded for r in champ.results[0]] == list(C.POINTS_TABLE)
    ranked = champ.standings().items
    assert champ.standings("quick").items == ranked == champ.standings("heap").items
    assert champ.top(3).items == ranked[:3] and champ.top(3).comparisons > 0

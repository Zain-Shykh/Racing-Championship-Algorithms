import itertools
import random

import pytest

from smart_racing import config
from smart_racing.algorithms.refuel import plan_refuel, replay_plan


def plan_and_replay(demands, available, **kw):
    res = plan_refuel(demands, available, **kw)
    kw.pop("scale", None)
    if res.feasible:
        replay = replay_plan(demands, available, res.purchases, **kw)
        assert replay.feasible, replay.reason
        assert replay.total_stop_time == res.total_stop_time
        assert replay.final_fuel >= res.final_fuel - 1e-9      # the DP fuel is a lower bound
        assert res.stops_made * kw.get("stop_time", config.REFUEL_STOP_TIME) == res.total_stop_time
    else:
        assert res.purchases == [] and res.reason and res.failed_leg is not None
    return res


def test_full_tank_needs_no_stop():
    res = plan_and_replay([30, 30, 30], [True, True, True])
    assert res.feasible and res.purchases == [0, 0, 0]
    assert res.total_stop_time == 0 and res.final_fuel == 10 and res.arrival_fuel == [100, 70, 40, 10]


def test_insufficient_fuel_forces_one_stop():
    res = plan_and_replay([30, 30], [True, True], start_fuel=20)
    assert res.feasible and res.stops_made == 1 and res.total_stop_time == config.REFUEL_STOP_TIME
    assert res.purchases == [40, 0] and res.final_fuel == 0       # 20 + 40 - 60


def test_insufficient_fuel_without_a_station_is_infeasible():
    res = plan_and_replay([30, 30], [False, False], start_fuel=50)
    assert not res.feasible and res.failed_leg == 1 and "leg 1" in res.reason


def test_unavailable_station_moves_or_kills_the_plan():
    demands, start = [20, 20, 20], 30
    assert plan_and_replay(demands, [True, True, True], start_fuel=start).stops_made == 1
    moved = plan_and_replay(demands, [True, False, True], start_fuel=start)
    assert moved.feasible and moved.purchases[1] == 0 and moved.stops_made == 1
    dead = plan_and_replay(demands, [False, False, True], start_fuel=start)
    assert not dead.feasible and dead.failed_leg == 1


def test_capacity_limit():
    # A full tank cannot take more fuel, so the first station is useless.
    res = plan_and_replay([10, 95], [True, True])
    assert res.feasible and res.purchases == [0, 10]              # tank room at stop 1 is exactly 10
    # No tank can hold a leg longer than the capacity.
    assert not plan_and_replay([10, 101], [True, True]).feasible
    # The 40-unit purchase limit, not the tank, is binding here.
    assert not plan_and_replay([80], [True], start_fuel=30).feasible
    assert plan_and_replay([70], [True], start_fuel=30).purchases == [40]


def test_two_stops_only_when_one_cannot_do_it():
    res = plan_and_replay([50, 50, 50], [True, True, True], start_fuel=70)
    assert res.feasible and res.stops_made == 2 and res.total_purchased >= 80
    assert plan_and_replay([50, 50, 50], [True, True, True], start_fuel=60).stops_made == 3


def test_fractional_demands_round_up():
    # 0.25 rounds up to 0.3 per leg: four legs need 1.2 discrete units, not 1.0.
    assert not plan_and_replay([0.25] * 4, [False] * 4, start_fuel=1.0).feasible
    assert replay_plan([0.25] * 4, [False] * 4, [0] * 4, start_fuel=1.0).feasible
    assert plan_and_replay([0.7, 0.3], [False, False], start_fuel=1.0).feasible   # 0.7 * 10 float noise


def test_empty_route_and_validation():
    res = plan_refuel([], [], start_fuel=12.5)
    assert res.feasible and res.purchases == [] and res.final_fuel == 12.5
    for demands, available, start in (([1], [], 5), ([-1], [True], 5), ([1], [True], 101), ([1], [True], -1)):
        with pytest.raises(ValueError):
            plan_refuel(demands, available, start_fuel=start)


def test_replay_checker_rejects_rule_violations():
    demands, available = [30, 30], [True, False]
    assert replay_plan(demands, available, [40, 0], start_fuel=20).feasible
    for bad in ([0, 0], [41, 0], [0, 40], [-1, 0], [1.5, 0], [40]):
        assert not replay_plan(demands, available, bad, start_fuel=20).feasible


def test_matches_brute_force_on_small_instances():
    rng = random.Random(11)
    rules = dict(capacity=6, max_purchase=3, stop_time=2.0)
    feasible = 0
    for _ in range(300):
        m = rng.randint(1, 4)
        demands = [rng.randint(0, 5) for _ in range(m)]
        available = [rng.random() < 0.6 for _ in range(m)]
        start = rng.randint(0, 6)
        best = None
        for plan in itertools.product(range(4), repeat=m):
            replay = replay_plan(demands, available, plan, start_fuel=start, **rules)
            # the DP never buys beyond the tank, so do not let the oracle waste fuel on the cap either
            fuel, fits = start, True
            for d, a in zip(demands, plan):
                fits = fits and fuel + a <= 6
                fuel = fuel + a - d
            if replay.feasible and fits and (best is None or replay.total_stop_time < best):
                best = replay.total_stop_time
        res = plan_and_replay(demands, available, start_fuel=start, scale=1, **rules)
        assert res.feasible == (best is not None)
        if res.feasible:
            feasible += 1
            assert res.total_stop_time == best
    assert 50 < feasible < 250


def test_random_plans_replay_and_observer_ends_with_done():
    rng = random.Random(3)
    for _ in range(40):
        m = rng.randint(1, 8)
        demands = [round(rng.uniform(0, 60), 2) for _ in range(m)]
        steps = []
        res = plan_and_replay(demands, [rng.random() < 0.7 for _ in range(m)],
                              start_fuel=round(rng.uniform(0, 100), 2))
        plan_refuel(demands, [True] * m, observer=steps.append)
        assert steps[-1]["type"] == "done" and res.states > 0

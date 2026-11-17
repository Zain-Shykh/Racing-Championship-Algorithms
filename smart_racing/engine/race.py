"""RaceEngine: the headless, deterministic race simulation (SPEC 4.1 to 4.6, 5).

Time advances in fixed ticks of `config.SIM_DT`. In one tick the engine first
applies every due event, re-plans the racers those events affect, then moves
each racer (in id order) through the tick. Inside a tick a racer spends its
time exactly: arriving at a vertex, stopping for fuel and entering the next
road happen at their true times, so lap times do not depend on the tick size.

Everything a screen needs is public: `racers` (RacerState), `clock`, `feed`,
`log`, `running_order()`, `live_top_k()`, `legal_choices()`, `xy()`. Treat
RacerState fields as read-only and change the race only through the input
methods `set_autopilot`, `choose_edge`, `fire_nitro` and `refuel`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from smart_racing import config as C
from smart_racing.algorithms.sorting import merge_sort
from smart_racing.algorithms.topk import TopKResult, top_k
from smart_racing.core.graph import CHECKPOINT, FINISH, FUEL_STATION, NITRO_PICKUP
from smart_racing.core.models import Racer
from smart_racing.engine.events import EventQueue
from smart_racing.engine.opponents import STRATEGIES, fill_amount, wants_nitro
from smart_racing.engine.resources import fuel_to_next_station
from smart_racing.engine.routing import RoutePlan, nearest_station, route_affected
from smart_racing.tracks.loader import Circuit, load_builtin

RACING, WAITING, REFUELLING, FINISHED, DNF = "racing", "waiting", "refuelling", "finished", "dnf"
EPS = 1e-9
_REOPENING = (C.EVENT_ROAD_CLEAR, C.EVENT_SHORTCUT_OPEN, C.EVENT_EXPIRE)


class LogEntry(NamedTuple):
    time: float
    racer_id: int | None           # None for track events
    kind: str                      # event type, or reroute/refuel/nitro/pickup/checkpoint/lap/finish/wait/dnf
    text: str


class Choice(NamedTuple):
    """One road the player may take from a junction."""
    edge_id: int
    to_vertex: int
    distance: float
    time: float
    fuel: float
    recommended: bool


class RacerSpec(NamedTuple):
    name: str
    strategy: str = "human"        # key of opponents.STRATEGIES
    is_human: bool = False


@dataclass
class RacerState(Racer):
    """A racer during a race: the Project.md 3.2 record plus live state."""
    strategy: object = None
    autopilot: bool = True
    status: str = RACING
    edge_id: int | None = None     # road being driven; None while at `current_vertex`
    from_vertex: int | None = None
    to_vertex: int | None = None
    progress: float = 0.0          # fraction of the current road covered
    edge_fuel: float = 0.0         # fuel price of the current road, fixed on entry
    route: list[int] = field(default_factory=list)   # planned edge ids after the current road
    plan: RoutePlan | None = None  # the plan `route` came from (totals for the HUD)
    nitro_left: float = 0.0        # seconds of boost remaining
    stop_left: float = 0.0         # seconds of fuel stop remaining
    wait_time: float = 0.0         # continuous waiting, s (DNF at DNF_WAIT_TIME)
    wait_reason: str = ""
    idle: float = 0.0              # manual player: time spent undecided at this vertex
    chosen_edge: int | None = None
    station_done: bool = False     # the automatic purchase decision here is made (reset after a stop)
    retry: bool = False            # a waiting racer re-plans on its next move
    lap_times: list[float] = field(default_factory=list)
    lap_start: float = 0.0
    finish_time: float | None = None
    end_time: float | None = None  # when an unfinished racer stopped (DNF or time limit)
    fuel_stops: int = 0
    fuel_bought: float = 0.0
    reroutes: int = 0
    nitro_used: int = 0
    waited: float = 0.0            # total waiting, s
    distance: float = 0.0
    driven: list[int] = field(default_factory=list)   # edge ids entered so far, in order

    @property
    def nitro_active(self) -> bool:
        return self.nitro_left > 0

    @property
    def checkpoints_done(self) -> int:
        """Checkpoints passed in the current lap."""
        return self.next_checkpoint - 1

    @property
    def fastest_lap(self) -> float | None:
        return min(self.lap_times) if self.lap_times else None

    @property
    def active(self) -> bool:
        return self.status not in (FINISHED, DNF)

    @property
    def position(self) -> tuple:
        """("vertex", id) or ("edge", edge id, progress, from vertex, to vertex)."""
        if self.edge_id is None:
            return ("vertex", self.current_vertex)
        return ("edge", self.edge_id, self.progress, self.from_vertex, self.to_vertex)


class RaceEngine:
    def __init__(self, circuit: Circuit, racers: list[RacerState], laps: int = C.LAPS_PER_RACE,
                 events: list[dict] | None = None, time_limit: float = C.RACE_TIME_LIMIT) -> None:
        """`circuit.graph` is mutated by the race (events, pickups): give every
        race a freshly loaded circuit. `events=None` uses the circuit's script."""
        self.circuit, self.graph = circuit, circuit.graph
        self.laps, self.time_limit = laps, time_limit
        self.events = EventQueue(self.graph)
        self.events.load_script(circuit.events if events is None else events)
        self.racers = merge_sort(racers, lambda a, b: a.id < b.id).items
        self._by_id = {r.id: r for r in self.racers}
        self.num_checkpoints = len(self.graph.checkpoints())
        self.ticks = 0
        self.finished = False
        self.feed: list[LogEntry] = []     # applied track events
        self.log: list[LogEntry] = []      # notable racer events
        self._acc = 0.0
        for r in self.racers:
            r.current_vertex = self.graph.start.id
            self._replan(r)

    # --- clock ----------------------------------------------------------------
    @property
    def clock(self) -> float:
        return self.ticks * C.SIM_DT

    def update(self, dt: float) -> None:
        """Feed real (or scaled) frame time; runs as many fixed ticks as fit."""
        self._acc += dt
        while self._acc >= C.SIM_DT - EPS and not self.finished:
            self._acc -= C.SIM_DT
            self.step()

    def run_to_completion(self) -> "RaceEngine":
        """Tick until the race is over. Bounded by the time limit, so it always returns."""
        while not self.finished:
            self.step()
        return self

    def step(self) -> None:
        """One fixed tick: due events, one re-plan pass, then every racer moves."""
        if self.finished:
            return
        now = self.clock
        records = self.events.pop_due(now)
        if records:
            self.feed += [LogEntry(now, None, rec.event.type, rec.description) for rec in records]
            changed = {rec.target for rec in records if rec.target_kind == "edge"}
            reopened = any(rec.event.type in _REOPENING for rec in records if rec.target_kind == "edge")
            for r in self.racers:
                if not r.active:
                    continue
                r.retry = True
                if changed and (reopened or route_affected(r.route, changed)):
                    self._replan(r)
        for r in self.racers:
            if r.active:
                self._advance(r, C.SIM_DT, now)
        self.ticks += 1
        if self.clock >= self.time_limit - EPS or not any(r.active for r in self.racers):
            self.finished = True
            for r in self.racers:
                if r.active:
                    r.end_time = r.total_time = self.clock

    # --- queries ----------------------------------------------------------------
    def racer(self, racer_id: int) -> RacerState:
        return self._by_id[racer_id]

    @property
    def human(self) -> RacerState | None:
        return next((r for r in self.racers if r.is_human), None)

    def xy(self, racer_id: int) -> tuple[float, float]:
        """Interpolated map position."""
        r = self._by_id[racer_id]
        if r.edge_id is None:
            v = self.graph.vertex(r.current_vertex)
            return v.x, v.y
        a, b = self.graph.vertex(r.from_vertex), self.graph.vertex(r.to_vertex)
        return a.x + (b.x - a.x) * r.progress, a.y + (b.y - a.y) * r.progress

    def next_target(self, r: RacerState) -> int:
        """Vertex id of the racer's next mandatory vertex."""
        cps = self.graph.checkpoints()
        return cps[r.next_checkpoint - 1].id if r.next_checkpoint <= len(cps) else self.graph.finish.id

    def time_to_target(self, r: RacerState) -> float:
        """Planned driving time to the next mandatory vertex. O(route)."""
        target, vertex, total = self.next_target(r), r.current_vertex, 0.0
        if r.edge_id is not None:
            total, vertex = (1.0 - r.progress) * self.graph.edge(r.edge_id).effective_time, r.to_vertex
        for edge_id in r.route:
            if vertex == target:
                break
            edge = self.graph.edge(edge_id)
            total, vertex = total + edge.effective_time, edge.other(vertex)
        return total

    def _rank_key(self, r: RacerState) -> tuple:
        if r.status == FINISHED:
            return (0, r.finish_time, r.id)
        if r.end_time is not None:             # DNF, or the race is over
            return (1, -r.lap, -r.checkpoints_done, 1, r.end_time, r.id)
        return (1, -r.lap, -r.checkpoints_done, 0, self.time_to_target(r), r.id)

    def race_less(self, a: RacerState, b: RacerState) -> bool:
        """Running-order comparator (SPEC 4.7): finishers by time; then laps,
        checkpoints, and while racing the planned time to the next checkpoint
        (elapsed time once stopped); racer id last."""
        return self._rank_key(a) < self._rank_key(b)

    def running_order(self) -> list[RacerState]:
        """Racers in race position (merge sort). The final classification once finished."""
        return merge_sort(self.racers, self.race_less).items

    classification = running_order

    def live_top_k(self, k: int) -> TopKResult:
        """Leading `k` racers by the size-k heap (Challenge 3)."""
        return top_k(self.racers, k, self.race_less)

    def race_position(self, racer_id: int) -> int:
        return [r.id for r in self.running_order()].index(racer_id) + 1

    def _decision_point(self, r: RacerState) -> tuple[int, float]:
        """Vertex of the racer's next decision and the fuel it will have there."""
        if r.edge_id is None:
            return r.current_vertex, r.fuel
        return r.to_vertex, r.fuel - r.edge_fuel * (1.0 - r.progress)

    def legal_choices(self, racer_id: int) -> list[Choice]:
        """Open, correctly directed roads the racer can afford from its vertex,
        or from the vertex it is driving to (so a choice can be made early)."""
        r = self._by_id[racer_id]
        if not r.active:
            return []
        vertex, fuel = self._decision_point(r)
        return [Choice(e.id, other, e.distance, e.effective_time, e.effective_fuel,
                       bool(r.route) and r.route[0] == e.id)
                for e, other in self.graph.neighbors(vertex) if fuel + EPS >= e.effective_fuel]

    def station_offer(self, racer_id: int) -> tuple[int, int] | None:
        """(most units purchasable, recommended units) while the racer stands
        at an active station and is not in a stop; else None."""
        r = self._by_id[racer_id]
        if not self._can_buy(r):
            return None
        return fill_amount(r.fuel), r.strategy.refuel_amount(self.graph, r.current_vertex, r.route, r.fuel)

    # --- player input -----------------------------------------------------------
    def set_autopilot(self, racer_id: int, on: bool) -> None:
        r = self._by_id[racer_id]
        r.autopilot, r.retry = on, True

    def choose_edge(self, racer_id: int, edge_id: int) -> bool:
        """Take `edge_id` at the current (or upcoming) vertex. Accepted only if
        it is one of `legal_choices`; re-checked when the car actually leaves."""
        r = self._by_id[racer_id]
        if edge_id not in [c.edge_id for c in self.legal_choices(racer_id)]:
            return False
        r.chosen_edge, r.retry = edge_id, True
        return True

    def fire_nitro(self, racer_id: int) -> bool:
        r = self._by_id[racer_id]
        if r.status != RACING or r.nitro_charges <= 0 or r.nitro_active:
            return False
        self._fire(r, self.clock)
        return True

    def refuel(self, racer_id: int, amount: int) -> bool:
        """Buy `amount` whole units (1..40) at an active station; one 3 s stop.
        The amount is capped by the room left in the tank."""
        r = self._by_id[racer_id]
        if not self._can_buy(r) or amount != int(amount) or not 1 <= amount <= C.STATION_MAX_PURCHASE:
            return False
        amount = min(amount, C.TANK_CAPACITY - r.fuel)
        if amount <= 0:
            return False
        r.station_done, r.retry = True, True
        self._buy(r, amount, self.clock)
        return True

    # --- internals --------------------------------------------------------------
    def _note(self, time: float, r: RacerState, kind: str, text: str) -> None:
        self.log.append(LogEntry(time, r.id, kind, f"{r.name}: {text}"))

    def _can_buy(self, r: RacerState) -> bool:
        if not r.active or r.edge_id is not None or r.stop_left > 0 or r.station_done:
            return False
        vertex = self.graph.vertex(r.current_vertex)
        return vertex.type == FUEL_STATION and vertex.active

    def _progress(self, vertex_id: int, checkpoint: int, lap: int) -> tuple[int, int]:
        """(next checkpoint, laps completed) after arriving at a vertex."""
        vertex = self.graph.vertex(vertex_id)
        if vertex.type == CHECKPOINT and vertex.checkpoint_order == checkpoint:
            return checkpoint + 1, lap
        if vertex.type == FINISH and checkpoint > self.num_checkpoints:
            return 1, lap + 1
        return checkpoint, lap

    def _replan(self, r: RacerState) -> None:
        """Ask the strategy for a route from the racer's next decision vertex."""
        vertex, checkpoint, lap = r.current_vertex, r.next_checkpoint, r.lap
        if r.edge_id is not None:
            vertex = r.to_vertex
            checkpoint, lap = self._progress(vertex, checkpoint, lap)
        if lap >= self.laps:
            r.route = []
            return
        plan = r.strategy.plan(self.circuit, vertex, checkpoint, self.laps - lap, r)
        new = plan.edges if plan.found else []
        if r.route and new and new != r.route:
            r.reroutes += 1
            self._note(self.clock, r, "reroute", "route recalculated")
        r.route, r.plan = new, plan

    def _drivable(self, vertex: int, edge_id: int) -> bool:
        return any(edge.id == edge_id for edge, _ in self.graph.neighbors(vertex))

    def _advance(self, r: RacerState, budget: float, t: float) -> None:
        for _ in range(10_000):                # bound on zero-time steps: nothing can hang
            if budget <= EPS or not r.active:
                break
            dt = min(budget, r.nitro_left) if r.nitro_active else budget
            if r.stop_left > 0:
                used = min(dt, r.stop_left)
                r.stop_left -= used
                if r.stop_left <= EPS:
                    r.stop_left, r.status = 0.0, RACING
                    r.station_done = False     # a further stop at the same station is allowed
            elif r.edge_id is not None:
                used = self._drive(r, dt, t)
            else:
                used = self._at_vertex(r, dt, t)
            r.nitro_left = max(0.0, r.nitro_left - used)
            if r.nitro_left <= EPS:
                r.nitro_left = 0.0
            budget -= used
            t += used
        if r.active:
            r.total_time = t

    def _drive(self, r: RacerState, dt: float, t: float) -> float:
        edge = self.graph.edge(r.edge_id)
        boost = r.nitro_active
        speed = C.NITRO_SPEED_MULT if boost else 1.0
        left = 1.0 - r.progress
        duration = edge.effective_time
        step = left if duration <= 0 else min(left, dt * speed / duration)
        used = step * duration / speed
        drain = r.edge_fuel * step * (C.NITRO_FUEL_MULT if boost else 1.0)
        if boost and r.fuel - drain < r.edge_fuel * (left - step) - EPS:
            r.nitro_left = 0.0                 # the boost would strand the car on this road
            self._note(t, r, "nitro", "nitro cut out to save fuel")
            return 0.0
        r.fuel = max(0.0, r.fuel - drain)
        r.progress += step
        r.distance += edge.distance * step
        if r.progress >= 1.0 - EPS:
            self._arrive(r, t + used)
        return used

    def _arrive(self, r: RacerState, t: float) -> None:
        vertex = self.graph.vertex(r.to_vertex)
        r.current_vertex, r.edge_id, r.progress = vertex.id, None, 0.0
        r.station_done, r.idle = False, 0.0
        checkpoint, lap = self._progress(vertex.id, r.next_checkpoint, r.lap)
        if lap > r.lap:
            r.lap_times.append(t - r.lap_start)
            r.lap_start = t
            self._note(t, r, "lap", f"lap {lap} in {r.lap_times[-1]:.2f} s")
        elif checkpoint > r.next_checkpoint:
            self._note(t, r, "checkpoint", f"checkpoint {r.next_checkpoint}")
        r.next_checkpoint, r.lap = checkpoint, lap
        if vertex.type == NITRO_PICKUP and vertex.active and r.nitro_charges < C.NITRO_MAX_CHARGES:
            r.nitro_charges += 1
            self.events.collect_nitro(vertex.id, t)
            self._note(t, r, "pickup", f"nitro collected at vertex {vertex.id}")
        if r.lap >= self.laps:
            r.status, r.finish_time, r.total_time, r.route = FINISHED, t, t, []
            self._note(t, r, "finish", f"finished in {t:.2f} s")

    def _at_vertex(self, r: RacerState, dt: float, t: float) -> float:
        """Decide what a racer standing at a vertex does. Returns the time used
        (0 when it started a fuel stop or entered a road)."""
        g, v = self.graph, r.current_vertex
        if r.status == WAITING and not r.retry:
            return self._wait(r, dt, t, r.wait_reason)
        r.retry = False
        if not r.route or not self._drivable(v, r.route[0]):
            self._replan(r)                    # recovery rule 1
        can_buy = self._can_buy(r)
        if r.chosen_edge is not None:
            edge_id, r.chosen_edge = r.chosen_edge, None
            if self._drivable(v, edge_id) and r.fuel + EPS >= g.edge(edge_id).effective_fuel:
                return self._enter(r, edge_id, t)
        manual = r.is_human and not r.autopilot
        if manual and C.PLAYER_CHOICE_GRACE - r.idle > EPS and (can_buy or len(self.legal_choices(r.id)) > 1):
            used = min(dt, C.PLAYER_CHOICE_GRACE - r.idle)     # give the player time to decide
            r.idle += used
            return used
        if can_buy:
            r.station_done = True
            amount = r.strategy.refuel_amount(g, v, r.route, r.fuel)
            if amount > 0:
                self._buy(r, amount, t)
                return 0.0
        if not r.route or not self._drivable(v, r.route[0]):
            return self._wait(r, dt, t, "no open route")       # recovery rule 2
        short = r.fuel + EPS < g.edge(r.route[0]).effective_fuel
        if short or self._must_divert(r):
            # recovery rule 3: the nearest open station; failing that wait at a
            # closed one (here, or the nearest) for the event that reopens it
            detour, here = nearest_station(g, v, r.fuel), g.vertex(v)
            if detour is None and here.type == FUEL_STATION and not here.active:
                return self._wait(r, dt, t, "fuel station closed")
            if detour is None and here.type != FUEL_STATION:
                detour = nearest_station(g, v, r.fuel, include_closed=True)
            if detour is not None:
                r.route, r.plan = detour.edges, detour
                r.reroutes += 1
                self._note(t, r, "reroute", f"heading for fuel station {detour.vertices[-1]}")
            elif short:
                return self._wait(r, dt, t, "out of fuel")
        return self._enter(r, r.route[0], t)

    def _must_divert(self, r: RacerState) -> bool:
        """The fuel cannot cover the route to its next active station (or its
        end), and after the next road no station would be reachable any more.
        A station that is out of service counts here: outages are temporary,
        so the racer drives on to it and waits there (see _at_vertex)."""
        g, v = self.graph, r.current_vertex
        if fuel_to_next_station(g, v, r.route)[0] <= r.fuel:
            return False
        edge = g.edge(r.route[0])
        ahead = g.vertex(edge.other(v))
        if ahead.type == FUEL_STATION:
            return False
        return nearest_station(g, ahead.id, r.fuel - edge.effective_fuel, include_closed=True) is None

    def _enter(self, r: RacerState, edge_id: int, t: float) -> float:
        edge, v = self.graph.edge(edge_id), r.current_vertex
        on_route = bool(r.route) and r.route[0] == edge_id
        r.route = r.route[1:] if on_route else []
        r.edge_id, r.from_vertex, r.to_vertex = edge_id, v, edge.other(v)
        r.progress, r.edge_fuel = 0.0, edge.effective_fuel
        r.driven.append(edge_id)
        r.status, r.wait_time, r.idle = RACING, 0.0, 0.0
        if not on_route:
            self._replan(r)
        if ((r.autopilot or not r.is_human) and not r.nitro_active
                and wants_nitro(self.graph, v, edge, r.route, r.fuel, r.nitro_charges,
                                C.NITRO_AUTO_MAX_DIFFICULTY[r.strategy.name])):
            self._fire(r, t)
        return 0.0

    def _fire(self, r: RacerState, t: float) -> None:
        r.nitro_charges -= 1
        r.nitro_left = C.NITRO_DURATION
        r.nitro_used += 1
        self._note(t, r, "nitro", "nitro fired")

    def _buy(self, r: RacerState, amount: float, t: float) -> None:
        r.fuel = min(C.TANK_CAPACITY, r.fuel + amount)
        r.stop_left, r.status, r.wait_time = C.REFUEL_STOP_TIME, REFUELLING, 0.0
        r.fuel_stops += 1
        r.fuel_bought += amount
        self._note(t, r, "refuel", f"bought {amount:g} fuel at station {r.current_vertex}")

    def _wait(self, r: RacerState, dt: float, t: float, reason: str) -> float:
        if r.status != WAITING or r.wait_reason != reason:
            r.status, r.wait_reason = WAITING, reason
            self._note(t, r, "wait", f"waiting at vertex {r.current_vertex} ({reason})")
        r.wait_time += dt
        r.waited += dt
        if r.wait_time >= C.DNF_WAIT_TIME - EPS or not self.events.has_pending_changes():
            r.status, r.end_time, r.total_time = DNF, t + dt, t + dt      # recovery rule 4
            why = "waited too long" if self.events.has_pending_changes() else "no event can help"
            self._note(t + dt, r, "dnf", f"did not finish: {reason}, {why}")
        return dt


def default_racers(opponents: int = C.NUM_OPPONENTS) -> list[RacerSpec]:
    """The player plus `opponents` opponents, strategies repeating in order."""
    if not 0 <= opponents < C.MAX_RACERS:
        raise ValueError(f"opponents must be 0..{C.MAX_RACERS - 1}")
    kinds = C.OPPONENT_STRATEGIES
    return [RacerSpec("Player", "human", True)] + [
        RacerSpec(f"{kinds[i % len(kinds)].capitalize()} {i // len(kinds) + 1}", kinds[i % len(kinds)])
        for i in range(opponents)]


def create_race(circuit: Circuit | str, laps: int = C.LAPS_PER_RACE, preset: str = "Balanced",
                racers: list[RacerSpec] | None = None, events: list[dict] | None = None,
                autopilot: bool = True, pickup_solver: str | None = "dp",
                pickup_budget: float = C.PICKUP_DETOUR_BUDGET,
                time_limit: float = C.RACE_TIME_LIMIT) -> RaceEngine:
    """Start a race in one call. `circuit` is a built-in name (loaded fresh) or
    a Circuit the caller no longer needs untouched. Racer ids are positions in
    `racers` (default: player = 0, opponents 1..3). `preset`,
    `pickup_solver` ("dp", "greedy", None) and `pickup_budget` (seconds of
    detour) configure the player's autopilot line."""
    if isinstance(circuit, str):
        circuit = load_builtin(circuit)
    specs = default_racers() if racers is None else list(racers)
    if not 1 <= len(specs) <= C.MAX_RACERS:
        raise ValueError(f"a race takes 1..{C.MAX_RACERS} racers")
    states = []
    for i, spec in enumerate(specs):
        spec = RacerSpec(*spec)
        strategy = (STRATEGIES["human"](preset, pickup_solver, pickup_budget) if spec.strategy == "human"
                    else STRATEGIES[spec.strategy]())
        states.append(RacerState(i, spec.name, spec.is_human, spec.strategy, strategy=strategy,
                                 autopilot=autopilot or not spec.is_human))
    return RaceEngine(circuit, states, laps, events, time_limit)

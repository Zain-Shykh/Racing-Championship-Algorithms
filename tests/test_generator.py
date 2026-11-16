"""Track generator: pipeline stages, determinism, validity, rejected candidates."""
import pytest

from smart_racing import config as C
from smart_racing.algorithms.dfs import connected_components, find_cycle
from smart_racing.engine.events import EventQueue
from smart_racing.tracks.generator import generate
from smart_racing.tracks.loader import circuit_to_dict, load_circuit, save_circuit
from smart_racing.tracks.validator import validate_circuit

REJECT_SEED = 29     # its first candidate fails validation (fuel), the second is accepted


@pytest.mark.parametrize("seed", range(8))
def test_generated_track_passes_the_validator(seed):
    circuit, report = generate(seed)
    assert report.success and report.attempts == len(report.rejected) + 1 <= C.GEN_MAX_ATTEMPTS
    result = validate_circuit(circuit)                      # default thresholds, same as the built-ins
    assert result.ok, result.failures
    g = circuit.graph
    assert len(g.checkpoints()) == 10 and sum(e.is_shortcut for e in g.edges()) == 2
    assert max(sum(1 for _ in g.incident(v)) for v in g.vertex_ids()) <= C.GEN_MAX_DEGREE
    assert all(e.distance >= g.straight_line(e.src, e.dst) for e in g.edges())
    # road closures in the script never hit a bridge: the track stays in one piece
    for event in circuit.events:
        if event["type"] == C.EVENT_ROAD_BLOCK:
            g.block_edge(event["target"])
            assert len(connected_components(g).components) == 1
            g.unblock_edge(event["target"])
    queue = EventQueue(g)
    queue.load_script(circuit.events)
    queue.pop_due(1000.0)
    assert queue.rejected == []


def test_same_seed_same_track_and_different_seed_differs():
    a, b, c = generate(3)[0], generate(3)[0], generate(4)[0]
    assert circuit_to_dict(a) == circuit_to_dict(b) != circuit_to_dict(c)


def test_stages_are_inspectable():
    circuit, report = generate(3)
    stages = {stage.name: stage for stage in report.stages}
    assert list(stages) == ["vertices", "candidates", "mst", "extras", "loop", "one_way", "placement"]
    n = C.GEN_COLS * C.GEN_ROWS
    assert stages["vertices"].graph.num_vertices == n and stages["vertices"].graph.num_edges == 0
    assert len(connected_components(stages["candidates"].graph).components) == 1
    mst = stages["mst"].graph
    assert mst.num_edges == n - 1 and not find_cycle(mst).has_cycle
    assert len(connected_components(mst).components) == 1
    assert stages["extras"].graph.num_edges > mst.num_edges and find_cycle(stages["extras"].graph).has_cycle
    assert not any(e.directed for e in stages["extras"].graph.edges())      # one-way roads come after the MST
    assert sum(e.directed for e in stages["one_way"].graph.edges()) >= 1
    assert stages["loop"].info["loop"] == circuit.main_route
    assert stages["placement"].graph is circuit.graph and all(stage.description for stage in report.stages)
    for key in ("loop", "placement"):
        solved = report.solver[key]
        assert solved.solved and solved.nodes > 0 and solved.prunes > 0


def test_rejected_candidate_is_reported_with_the_validators_reason():
    circuit, report = generate(REJECT_SEED)
    assert report.success and report.attempts == 2
    (rejection,) = report.rejected
    assert rejection.attempt == 1 and rejection.stage == "validation"
    assert rejection.reasons[0].startswith("no feasible fuel plan for 2 lap(s)")
    nothing, failed = generate(REJECT_SEED, max_attempts=1)                  # retry limit reached
    assert nothing is None and not failed.success and failed.attempts == 1 and len(failed.rejected) == 1


def test_generated_track_uses_the_circuit_file_format(tmp_path):
    circuit, _ = generate(5)
    save_circuit(circuit, tmp_path / "generated.json")
    again = load_circuit(tmp_path / "generated.json")
    assert circuit_to_dict(again) == circuit_to_dict(circuit) and validate_circuit(again).ok
    assert again.main_route and again.detour and again.opponent_shortcuts and again.events

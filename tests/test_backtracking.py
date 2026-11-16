from smart_racing.algorithms.backtracking import solve
from smart_racing.algorithms.bfs import bfs
from tests.helpers import make_graph


def grid_graph(rows, cols):
    """Vertices 0..rows*cols-1 in row order, roads between grid neighbours."""
    edges = []
    for r in range(rows):
        for c in range(cols):
            v = r * cols + c
            if c + 1 < cols:
                edges.append((v, v + 1))
            if r + 1 < rows:
                edges.append((v, v + cols))
    return make_graph(list(range(rows * cols)), edges)


def place_stations(graph, k, min_hops, node_limit=10_000, use_prune=True, observer=None):
    """Put k fuel stations on distinct vertices, every pair at least `min_hops` roads apart."""
    hops = {v: bfs(graph, v).dist for v in graph.vertex_ids()}
    variables = [f"station{i}" for i in range(k)]
    domains = {var: graph.vertex_ids() for var in variables}

    def consistent(assignment, var, value):
        # ascending vertex ids break the symmetry between interchangeable stations
        return all(value > other and hops[value][other] >= min_hops for other in assignment.values())

    def too_few_sites_left(assignment, remaining):
        free = [v for v in graph.vertex_ids() if consistent(assignment, None, v)]
        return len(free) < len(remaining)

    res = solve(variables, domains, consistent, too_few_sites_left if use_prune else None,
                node_limit=node_limit, observer=observer)
    return res, hops


def test_station_placement_respects_spacing():
    graph = grid_graph(3, 3)
    steps = []
    res, hops = place_stations(graph, 5, 2, observer=steps.append)
    assert res.solved and not res.limit_hit
    sites = list(res.assignment.values())
    assert sites == [0, 2, 4, 6, 8]                    # corners and centre, the only solution
    assert all(hops[a][b] >= 2 for a in sites for b in sites if a != b)
    assert res.nodes > 5 and res.prunes > 0
    assert {s["type"] for s in steps} >= {"assign", "reject", "done"} and steps[-1]["solved"]


def test_unsatisfiable_placement_terminates_cleanly():
    res, _ = place_stations(grid_graph(3, 3), 6, 2)
    assert not res.solved and not res.limit_hit and res.assignment == {}
    assert res.backtracks > 0 and res.prunes > 0


def test_pruning_hook_cuts_the_search():
    graph = grid_graph(3, 3)
    plain, _ = place_stations(graph, 6, 2, use_prune=False)
    pruned, _ = place_stations(graph, 6, 2)
    assert not plain.solved and not pruned.solved
    assert pruned.nodes < plain.nodes


def test_node_limit_stops_the_search():
    res, _ = place_stations(grid_graph(3, 3), 6, 2, node_limit=20, use_prune=False)
    assert res.limit_hit and not res.solved and res.nodes == 20 and res.assignment == {}


def test_counters_on_a_tiny_instance():
    # x, y in {1, 2, 3} with x > y: (1,*) fails, (2,1) succeeds.
    res = solve(["x", "y"], {"x": [1, 2, 3], "y": [1, 2, 3]},
                lambda a, var, value: var == "x" or a["x"] > value)
    assert res.solved and res.assignment == {"x": 2, "y": 1}
    assert (res.nodes, res.prunes, res.backtracks) == (6, 3, 1)


def test_no_variables_and_empty_domain():
    assert solve([], {}, lambda *a: True).solved
    res = solve(["x", "y"], {"x": [1, 2], "y": []}, lambda *a: True)
    assert not res.solved and res.nodes == 2 and res.backtracks == 2

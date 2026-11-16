"""Small graph builders shared by the test suites."""
from smart_racing.core.graph import TrackGraph


def make_graph(vertices, edges, directed=False):
    """vertices: ids or (id, x, y) or (id, x, y, type); edges: (u, v) or (u, v, distance).
    Edge ids are 1..n in list order."""
    g = TrackGraph()
    for v in vertices:
        g.add_vertex(*((v,) if isinstance(v, int) else v))
    for i, (u, v, *rest) in enumerate(edges, start=1):
        g.add_edge(i, u, v, rest[0] if rest else 1.0, directed=directed)
    return g


def st_example():
    """Project.md 5.1: direct S-T of length 10, S-A-B-T with three edges of length 2."""
    return make_graph([0, 1, 2, 3], [(0, 3, 10), (0, 1, 2), (1, 2, 2), (2, 3, 2)])

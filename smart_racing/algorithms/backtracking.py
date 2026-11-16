"""Generic backtracking solver for constraint placement (Project.md 5.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Mapping, Sequence

from smart_racing import config

Observer = Callable[[dict], None]
Assignment = dict[Hashable, Any]


@dataclass
class BacktrackResult:
    solved: bool = False
    assignment: Assignment = field(default_factory=dict)   # variable -> value, empty if unsolved
    nodes: int = 0            # candidate (variable, value) pairs tried
    prunes: int = 0           # candidates rejected by `consistent` plus branches cut by `prune`
    backtracks: int = 0       # assignments undone
    limit_hit: bool = False   # stopped by `node_limit`; unsolved does not prove "no solution"


def solve(variables: Sequence[Hashable],
          domains: Mapping[Hashable, Sequence[Any]],
          consistent: Callable[[Assignment, Hashable, Any], bool],
          prune: Callable[[Assignment, Sequence[Hashable]], bool] | None = None,
          node_limit: int = config.BACKTRACK_NODE_LIMIT,
          observer: Observer | None = None) -> BacktrackResult:
    """Depth-first search for an assignment of every variable.

    Variables are assigned in the given order and values tried in domain
    order, so the first solution found is deterministic.
    `consistent(assignment, var, value)` sees the partial assignment without
    `var` and says whether `var = value` may be added. The optional
    `prune(assignment, remaining_vars)` runs after each assignment and returns
    True to abandon the branch early (forward checking); it must only cut
    branches that cannot be completed, or solutions are lost. The search stops
    with `limit_hit=True` after `node_limit` candidates.

    Worst case O(d^n) candidates for n variables with d values each; pruning
    only reduces the explored part. Space O(n) (recursion depth = n).
    """
    res = BacktrackResult()
    assignment: Assignment = {}

    def place(i: int) -> bool:
        if i == len(variables):
            return True
        var = variables[i]
        for value in domains[var]:
            if res.nodes >= node_limit:
                res.limit_hit = True
                return False
            res.nodes += 1
            if not consistent(assignment, var, value):
                res.prunes += 1
                if observer:
                    observer({"type": "reject", "var": var, "value": value})
                continue
            assignment[var] = value
            if observer:
                observer({"type": "assign", "var": var, "value": value, "depth": i})
            if prune is not None and prune(assignment, variables[i + 1:]):
                res.prunes += 1
                if observer:
                    observer({"type": "prune", "var": var, "value": value})
            elif place(i + 1):
                return True
            del assignment[var]
            res.backtracks += 1
            if observer:
                observer({"type": "backtrack", "var": var, "value": value})
            if res.limit_hit:
                return False
        return False

    res.solved = place(0)
    if res.solved:
        res.assignment = dict(assignment)
    if observer:
        observer({"type": "done", "solved": res.solved, "assignment": dict(res.assignment),
                  "nodes": res.nodes, "prunes": res.prunes, "backtracks": res.backtracks})
    return res

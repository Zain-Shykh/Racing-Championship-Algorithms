# Smart Racing Championship

University Design and Analysis of Algorithms project: a 2D top-down racing game
in Python/pygame whose gameplay is driven by 12 hand-implemented algorithms.

Read first, in this order: `docs/SPEC.md` (frozen design), the relevant phase in
`docs/IMPLEMENTATION_PLAN.md`, then `Project.md` sections that phase cites.

## Commands
- Run game: `.venv/bin/python main.py`
- Tests: `.venv/bin/pytest -q`
- Headless pygame: prefix with `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`
- Experiments: `.venv/bin/python -m smart_racing.experiments.run_all`

## Rules
- Mandatory algorithms and the heap are written by hand. No `heapq`, no
  `sorted`/`.sort` inside ranking code, no `networkx` (SPEC section 1).
- Algorithms follow SPEC section 3: pure functions, result dataclass with
  counters, optional `observer` callback. The Algorithm Lab and the experiments
  must call these same functions. Never write a second copy for display.
- `core`, `algorithms` and `engine` must not import `pygame`.
- Game constants live only in `smart_racing/config.py`.
- Deterministic: seeded `random.Random` only, stable tie-breaks by id.
- Type hints and short docstrings stating complexity on every algorithm.
- Keep it simple: no abstractions without a second user, no new dependencies.
- If the brief and the spec leave something open, decide, and record the
  decision in `docs/RULES.md`.

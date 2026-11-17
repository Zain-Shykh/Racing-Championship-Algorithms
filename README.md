# Smart Racing Championship

A 2D top-down racing game for the course *Design and Analysis of Algorithms*. The
cars drive on a road network (a graph), manage fuel and nitro, react to road
events and compete in a three-race championship against three deterministic
computer opponents. The game is a vehicle for 12 hand-written algorithms; each
one has a real job in the game, and the Algorithm Lab replays the very same
functions the race uses.

No machine learning or reinforcement learning is used. Opponents follow fixed
rules. All mandatory algorithms (BFS, DFS, Dijkstra, A*, knapsack DP, refuel DP,
greedy, backtracking, Kruskal, min-heap, merge sort, quick sort, heap sort) are
written by hand in `smart_racing/algorithms/`; no library implements any of them.

## Requirements

- Python 3.12 (3.10+ should work)
- `pygame-ce` (GUI), `matplotlib` (experiment charts), `pytest` (tests)
- A display for the game. Tests run headless (`SDL_VIDEODRIVER=dummy`).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Screens

| Menu entry | What it does |
|---|---|
| Championship | Three races (Harbor Eight, Grand Ring, Serpent Pass) with points, standings and a champion |
| Quick Race | One race on a circuit you pick, with chosen preset, laps and autopilot |
| Track Explorer | Graph view: reachability (BFS/DFS), alternative routes, route comparison (Dijkstra/A*, four cost presets), resource advice (knapsack, refuel DP) |
| Racing Screen | The race itself: cars, fuel, nitro, events, live order, junction choices |
| Algorithm Lab | Step through BFS, DFS, Dijkstra, A*, knapsack DP/greedy, backtracking, Kruskal, event heap and the three sorts, with live counters |
| Championship Dashboard | Results, standings (merge, quick or heap sort), live top-k |
| Track Generator | Seeded generated circuit (Kruskal backbone + backtracking placement) and rejected candidates |
| Instructions, Settings | In-game help; laps, default cost preset, simulation speed, id labels |

## Controls (Racing Screen)

| Key / mouse | Action |
|---|---|
| `A` | Toggle autopilot (follows the recommended A* route and refuel plan) |
| `1`-`9` or click a road | Choose the next road at a junction (manual driving) |
| `Space` | Fire nitro (1.5x speed, 2x fuel for 4 s, needs a charge) |
| `R` | Buy the recommended fuel amount at an active station |
| `F` | Fill the tank |
| `Up` / `Down` (or `+` / `-`), `Enter` | Set a custom fuel amount, then buy it |
| `Tab` | Change simulation speed |
| `P` / `Esc` | Pause (Esc also asks before leaving a race) |

With autopilot off and no input, the car waits 3 s at a junction or station and
then takes the recommended road/purchase, so an idle player still finishes.
The full rule set is in `docs/RULES.md` and `docs/SPEC.md`.

## Tests

```bash
python -m pytest -q
```

312 tests (about 50 s). The UI tests use a dummy video driver and need no display.

## Experiments

```bash
python -m smart_racing.experiments.run_all           # full run, about 200 s
python -m smart_racing.experiments.run_all --quick   # small smoke run, writes to experiments/results/quick/
```

Results (raw CSVs, summaries, PNG charts, `SUMMARY.md`, `environment.json`) are
written to `experiments/results/`. The committed results come from the full run.

## Project layout

```
main.py                    entry point
smart_racing/
  config.py                every frozen constant
  core/                    graph (adjacency lists), models, route cost and presets
  algorithms/              the 12 algorithms + MinHeap (no UI, return counters)
  engine/                  events, routing, resources, opponents, race, championship (no pygame)
  tracks/                  3 circuit JSON files, loader, validator, generator
  ui/                      pygame app, screens, Algorithm Lab registry, widgets
  experiments/             the five experimental studies
tests/                     pytest suites
docs/                      SPEC.md, RULES.md, IMPLEMENTATION_PLAN.md, screenshots/
experiments/results/       CSV, PNG, SUMMARY.md, environment.json
report/                    report.md, report.pdf
scripts/package.py         builds the submission ZIP
```

## Third-party libraries

- [pygame-ce](https://pyga.me/) for the GUI
- [matplotlib](https://matplotlib.org/) for experiment charts
- [pytest](https://pytest.org/) for tests

No third-party art or audio assets: everything is drawn with pygame primitives.

## Submission archive

Edit the group constant at the top of `scripts/package.py`, then run
`python scripts/package.py`. It writes `<group>.zip` to the repo root and verifies it.

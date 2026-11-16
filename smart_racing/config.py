"""Every frozen game constant (docs/SPEC.md section 4). Plain data, no logic."""

# --- 4.1 circuit structure -------------------------------------------------
MIN_CHECKPOINTS = 10
MIN_SHORTCUTS = 2
LAPS_PER_RACE = 2
RACE_TIME_LIMIT = 900.0        # simulated seconds

# --- 4.2 fuel and nitro ----------------------------------------------------
TANK_CAPACITY = 100.0
FUEL_DIFFICULTY_STEP = 0.1     # edge fuel = fuel_cost * (1 + step * (difficulty - 1))
STATION_MAX_PURCHASE = 40      # units per stop
REFUEL_STOP_TIME = 3.0         # seconds, for any positive purchase
LOW_FUEL_FRACTION = 0.25       # opponents look for a station below this (Project.md 4.4)
NITRO_MAX_CHARGES = 3
NITRO_START_CHARGES = 1
NITRO_RESPAWN_TIME = 25.0
NITRO_SPEED_MULT = 1.5
NITRO_DURATION = 4.0
NITRO_FUEL_MULT = 2.0
FUEL_SCALE = 10                # DP discretization: tenths of a fuel unit

# --- 4.3 route cost --------------------------------------------------------
MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
DIST_REF = 100.0
TIME_REF = 10.0
FUEL_REF = 10.0
# preset -> (wD, wT, wF, wR, wO)
COST_PRESETS = {
    "Balanced": (1.0, 1.0, 1.0, 1.0, 1.0),
    "Speed": (0.5, 3.0, 0.25, 0.5, 0.5),
    "Economy": (0.5, 0.5, 3.0, 0.5, 0.5),
    "Safety": (0.5, 0.5, 0.5, 3.0, 3.0),
}

# --- 4.5 events and edge effects -------------------------------------------
EFFECT_BLOCK = "block"
EFFECT_OIL = "oil"
EFFECT_SPEED = "speed"
# effect kind -> (blocks, difficulty bump, time multiplier, obstacle penalty)
EDGE_EFFECTS = {
    EFFECT_BLOCK: (True, 0, 1.0, 0.0),
    EFFECT_OIL: (False, 2, 1.5, 1.0),
    EFFECT_SPEED: (False, 0, 1.5, 0.5),
}

EVENT_ROAD_BLOCK = "road_block"
EVENT_ROAD_CLEAR = "road_clear"
EVENT_SHORTCUT_OPEN = "shortcut_open"
EVENT_SHORTCUT_CLOSE = "shortcut_close"
EVENT_OIL_SPILL = "oil_spill"
EVENT_SPEED_RESTRICTION = "speed_restriction"
EVENT_STATION_OUTAGE = "station_outage"
EVENT_NITRO_SPAWN = "nitro_spawn"
EVENT_EXPIRE = "expire"        # scheduled restore of a temporary effect

EVENT_PRIORITY = {
    EVENT_ROAD_BLOCK: 1,
    EVENT_ROAD_CLEAR: 1,
    EVENT_SHORTCUT_OPEN: 2,
    EVENT_SHORTCUT_CLOSE: 2,
    EVENT_OIL_SPILL: 3,
    EVENT_SPEED_RESTRICTION: 4,
    EVENT_STATION_OUTAGE: 5,
    EVENT_NITRO_SPAWN: 6,
}
# seconds; None = lasts until an explicit reversing event
EVENT_DURATION = {
    EVENT_ROAD_BLOCK: None,
    EVENT_ROAD_CLEAR: None,
    EVENT_SHORTCUT_OPEN: None,
    EVENT_SHORTCUT_CLOSE: None,
    EVENT_OIL_SPILL: 20.0,
    EVENT_SPEED_RESTRICTION: 15.0,
    EVENT_STATION_OUTAGE: 30.0,
    EVENT_NITRO_SPAWN: 25.0,
}

# --- 4.6 recovery ----------------------------------------------------------
DNF_WAIT_TIME = 60.0           # continuous waiting before DNF

# --- 4.7 scoring -----------------------------------------------------------
POINTS_TABLE = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
FASTEST_LAP_BONUS = 1
MAX_RACERS = 10
NUM_OPPONENTS = 3

# --- 5 determinism ---------------------------------------------------------
SIM_DT = 0.05

# --- Act 1 alternative-route panel (docs/RULES.md) --------------------------
ALT_ROUTE_LIMIT = 10           # max simple paths enumerated
ALT_PATH_MAX_EDGES = 40        # max edges in an enumerated path

# --- backtracking placement (docs/RULES.md) ---------------------------------
BACKTRACK_NODE_LIMIT = 200_000 # candidates tried before the solver gives up

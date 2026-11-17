"""Screen registry. `app.goto(name, **kwargs)` builds `SCREENS[name](app, **kwargs)`."""
from smart_racing.ui.screens.championship import ChampionshipScreen
from smart_racing.ui.screens.dashboard import Dashboard
from smart_racing.ui.screens.explorer import Explorer
from smart_racing.ui.screens.generator import Generator
from smart_racing.ui.screens.lab import Lab
from smart_racing.ui.screens.menu import Instructions, MainMenu, QuickRaceSetup, SettingsScreen
from smart_racing.ui.screens.race import RaceScreen

SCREENS = {
    "menu": MainMenu,
    "quick": QuickRaceSetup,
    "explorer": Explorer,
    "race": RaceScreen,
    "instructions": Instructions,
    "settings": SettingsScreen,
    "championship": ChampionshipScreen,
    "lab": Lab,
    "dashboard": Dashboard,
    "generator": Generator,
}

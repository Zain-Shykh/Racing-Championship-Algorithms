"""Screen registry. `app.goto(name, **kwargs)` builds `SCREENS[name](app, **kwargs)`.

To add a screen: write a `Screen` subclass and replace its entry below. The main menu already points at
the keys "championship", "lab" and "dashboard"; until those exist they open a placeholder.
"""
from smart_racing.ui.screens.explorer import Explorer
from smart_racing.ui.screens.menu import Instructions, MainMenu, Placeholder, QuickRaceSetup, SettingsScreen
from smart_racing.ui.screens.race import RaceScreen


def _placeholder(title: str):
    return lambda app, **kw: Placeholder(app, title=title)


SCREENS = {
    "menu": MainMenu,
    "quick": QuickRaceSetup,
    "explorer": Explorer,
    "race": RaceScreen,
    "instructions": Instructions,
    "settings": SettingsScreen,
    # Phase 6: replace these three with the real screen classes (same constructor signature as above).
    "championship": _placeholder("Championship"),
    "lab": _placeholder("Algorithm Lab"),
    "dashboard": _placeholder("Dashboard"),
}

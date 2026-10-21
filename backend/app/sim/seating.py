"""Where a guest chooses to spend their visit: the bar, the inside tables or the patio.

Pure functions, deterministic from their inputs, so tests need no director. Solo guests lean toward the bar, groups
toward tables, the patio follows the weather, and an area that is filling up gets less attractive.
"""
import random
from datetime import datetime

from . import environment

AREAS = ["bar", "inside-tables", "patio"]

# Base share by party size (solo, pair, three or more): bar, inside tables, patio.
_BASE = {
    1: {"bar": 0.50, "inside-tables": 0.38, "patio": 0.12},
    2: {"bar": 0.28, "inside-tables": 0.50, "patio": 0.22},
    3: {"bar": 0.07, "inside-tables": 0.60, "patio": 0.33},
}
_MONTH_PATIO = {12: 0.08, 1: 0.08, 2: 0.08, 3: 0.35, 4: 0.35, 11: 0.35, 5: 0.8, 10: 0.8, 6: 1.3, 7: 1.3, 8: 1.3, 9: 1.3}
_BAD_WEATHER = ("storm", "rain", "drizzl", "snow", "flurr", "slush")
FLOOR = 0.1  # a full table area still draws a few guests, who stand


def patio_appeal(now: datetime) -> float:
    """How much the patio draws right now, about 1.0 on a decent day: the season, the weather and the hour."""
    appeal = _MONTH_PATIO[now.month]
    if any(w in environment.weather(now) for w in _BAD_WEATHER):
        appeal *= 0.3
    if 15 <= now.hour < 19:
        appeal *= 1.2
    elif now.hour >= 21:
        appeal *= 0.7
    return appeal


def area_weights(party: int, bar_lean: float, knows_bartender: bool, game_fan: bool, now: datetime,
                 free: dict[str, int], cap: dict[str, int]) -> dict[str, float]:
    """Relative odds of each area for a party of this size, given how full each one is."""
    w = dict(_BASE[max(1, min(3, party))])
    w["bar"] *= bar_lean * (1.4 if knows_bartender else 1.0)
    if game_fan and environment.live(environment.game_on(now), now):
        w["bar"] *= 2
    if party >= 2 and environment.trivia_on(now):
        w["inside-tables"] *= 1.8
    w["patio"] *= patio_appeal(now)
    for a in AREAS:
        room = free[a] / cap[a] if cap[a] else 0.0
        w[a] *= room ** 0.5 if a == "bar" else max(FLOOR, room ** 0.5)
    return w


def pick_area(rng: random.Random, weights: dict[str, float]) -> str:
    areas = [a for a in AREAS if weights[a] > 0]
    return rng.choices(areas, [weights[a] for a in areas])[0] if areas else "inside-tables"

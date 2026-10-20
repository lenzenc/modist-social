"""The room around the people: weather, the game on the TV, trivia night, and how loud it is.

Everything is deterministic from the date, so a restart replays the same day and tests need no clock.
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

GAME_MINUTES = 180
OPPONENTS = {
    "Vikings": ["Packers", "Bears", "Lions", "Cowboys"],
    "Twins": ["Guardians", "Tigers", "White Sox", "Royals"],
    "Timberwolves": ["Nuggets", "Lakers", "Thunder", "Suns"],
    "Wild": ["Blackhawks", "Blues", "Jets", "Avalanche"],
}
_POINTS = {"Vikings": (7, 3), "Twins": (1, 2), "Timberwolves": (2, 3), "Wild": (1,)}
_SEASONS = {  # month -> weather pool
    **dict.fromkeys((12, 1, 2), ["snowing steadily", "bitterly cold and clear", "gray with flurries", "brutally cold, wind chill below zero"]),
    **dict.fromkeys((3, 4), ["slushy and gray", "cold and drizzling", "bright but still chilly", "windy with patches of old snow"]),
    **dict.fromkeys((5, 6), ["mild and green", "warm with a threat of storms", "perfect patio weather", "muggy and overcast"]),
    **dict.fromkeys((7, 8), ["hot and humid", "warm, with mosquitoes out", "sunny and breezy", "thunderstorms rolling through"]),
    **dict.fromkeys((9, 10), ["crisp and clear", "gray and drizzly", "cool with leaves coming down", "windy and cold"]),
    11: ["gray and raw", "first snow of the season", "cold and bare", "cold with a sharp wind"],
}


@dataclass
class Game:
    team: str
    opp: str
    start: datetime
    plays: list[tuple[datetime, bool, int]]  # (when, our team scored, points)


def _seed(now: datetime, tag: str) -> random.Random:
    return random.Random(f"{now.strftime('%Y-%m-%d')}|{tag}")


def game_on(now: datetime) -> Game | None:
    """The game on the bar TV today, if any."""
    day = _seed(now, "game")
    m, wd = now.month, now.weekday()
    if m in (9, 10, 11, 12, 1) and wd == 6 and day.random() < 0.85:
        team, hour = "Vikings", 12
    else:
        pool = [t for t, months in (("Twins", (4, 5, 6, 7, 8, 9)), ("Timberwolves", (10, 11, 12, 1, 2, 3, 4)),
                                    ("Wild", (10, 11, 12, 1, 2, 3, 4))) if m in months]
        if not pool or day.random() > 0.45:
            return None
        team, hour = day.choice(pool), 19
    start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    plays_rng = _seed(now, "plays")
    offsets = sorted(plays_rng.uniform(5, GAME_MINUTES - 5) for _ in range(plays_rng.randint(8, 14)))
    pts = _POINTS[team]
    plays = [(start + timedelta(minutes=o), plays_rng.random() < 0.5, plays_rng.choice(pts)) for o in offsets]
    return Game(team, day.choice(OPPONENTS[team]), start, plays)


def score(g: Game, now: datetime) -> tuple[int, int]:
    us = sum(p for when, ours, p in g.plays if ours and when <= now)
    them = sum(p for when, ours, p in g.plays if not ours and when <= now)
    return us, them


def live(g: Game | None, now: datetime) -> bool:
    return g is not None and g.start <= now <= g.start + timedelta(minutes=GAME_MINUTES)


def new_plays(g: Game, prev: datetime, now: datetime) -> list[tuple[bool, int, int, int]]:
    """Scoring plays in (prev, now]: (ours, points, our score, their score)."""
    out = []
    for when, ours, pts in g.plays:
        if prev < when <= now:
            us, them = score(g, when)
            out.append((ours, pts, us, them))
    return out


def weather(now: datetime) -> str:
    return _seed(now, "weather").choice(_SEASONS[now.month])


def trivia_on(now: datetime) -> bool:
    return now.weekday() == 2 and 19 <= now.hour < 21


def noise(guests: int) -> str:
    return "quiet" if guests < 6 else "comfortably busy" if guests < 14 else "loud" if guests < 22 else "loud and packed"


def is_loud(guests: int) -> bool:
    return guests >= 14


def fan_of(team: str, persona: dict) -> bool:
    blob = " ".join([str(persona.get("job", "")), str(persona.get("quirk", "")),
                     " ".join(persona.get("interests", [])), " ".join(persona.get("traits", []))]).lower()
    return team.lower() in blob or (team == "Timberwolves" and "wolves" in blob)


def room_line(now: datetime, guests: int) -> str:
    """One line of what the room is like, for every guest's scene."""
    parts = [f"Outside it is {weather(now)}.", f"The taproom is {noise(guests)}."]
    g = game_on(now)
    if live(g, now):
        us, them = score(g, now)
        parts.append(f"The {g.team} game is on the bar TV ({g.team} {us}, {g.opp} {them}).")
    elif g and now < g.start:
        parts.append(f"The {g.team} play the {g.opp} at {g.start.strftime('%-I%p').lower()}; it'll be on the bar TV.")
    if trivia_on(now):
        parts.append("Trivia is going at the inside tables.")
    return " ".join(parts)

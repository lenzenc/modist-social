"""Brand-new people walking into the taproom.

Code rolls the skeleton (name, numbers, schedule, habits) so uniqueness and balance are guaranteed; the model, or a
template when there is no model, fills in the human parts. Pure functions, like god.py and human.py.
"""
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from app.sim import human, menu, sales
from app.sim.state import display_name, short_name

SEED = Path(__file__).parent.parent / "seed"
WEEKDAY_WEIGHT = [1, 1, 1.5, 2, 3, 3, 2]  # Mon..Sun: when newcomers tend to come
FRIENDS_REASONS = ("unwind", "catch_up", "solo", "game", "date")
STYLES = tuple(human.STYLE_TEXT)
BEERS = tuple(human.BEER_TEXT)
MAX_FIELD = 160


@lru_cache(maxsize=1)
def names() -> dict:
    return yaml.safe_load((SEED / "names.yaml").read_text())


@lru_cache(maxsize=1)
def pools() -> dict:
    return yaml.safe_load((SEED / "newcomer_pools.yaml").read_text())


# ---------------------------------------------------------------- the skeleton


def pick_name(rng: random.Random, taken_shorts: set[str], taken_displays: set[str]) -> tuple[str, str] | None:
    """(full name, pronouns) with a first name and a display name nobody else has, or None when the pool is spent."""
    shorts = {s.lower() for s in taken_shorts}
    displays = {d.lower() for d in taken_displays}
    firsts = [f for f in names()["first"] if f["n"].lower() not in shorts]
    if not firsts:
        return None
    for _ in range(50):
        f = rng.choice(firsts)
        last = rng.choice(names()["last"])
        if f"{f['n']} {last}".lower() not in displays:
            return f"{f['n']} {last}", f["p"]
    return None


def _clamp(n: int, lo: int = 1, hi: int = 5) -> int:
    return max(lo, min(hi, n))


def _talk(e: int, rng: random.Random) -> float:
    """Talkativeness that agrees with extraversion, the same bands the seeded people follow."""
    base = {1: 0.22, 2: 0.3, 3: 0.5, 4: 0.72, 5: 0.86}[e] + rng.uniform(-0.04, 0.04)
    lo, hi = (0.1, 0.34) if e <= 2 else (0.36, 0.64) if e == 3 else (0.66, 0.95)
    return round(max(lo, min(hi, base)), 2)


def skeleton(rng: random.Random, now: datetime) -> dict:
    """Everything about a newcomer that is numeric, mechanical or a habit; the model never sees it as a choice."""
    ranges = [(21, 29), (30, 39), (40, 54), (55, 72)]
    lo, hi = rng.choices(ranges, [3, 3, 2.5, 1.5])[0]
    big5 = {k: _clamp(round(rng.gauss(3, 1))) for k in "ocean"}
    sociable = big5["e"] >= 4
    style_w = {"listener": 3 if big5["e"] <= 2 else 1, "storyteller": 3 if sociable else 1,
               "joker": 3 if sociable else 1, "debater": 2 if big5["a"] <= 2 else 1, "asker": 2}
    reasons = rng.sample(FRIENDS_REASONS, rng.choice([2, 3]))
    days: list[int] = []
    pool = list(range(7))
    for _ in range(rng.choice([1, 2, 2, 3])):
        d = rng.choices(pool, [WEEKDAY_WEIGHT[i] for i in pool])[0]
        pool.remove(d)
        days.append(d)
    start = rng.choice([15, 16, 17, 18, 19])
    return {
        "age": rng.randint(lo, hi),
        "big5": big5,
        "talk": _talk(big5["e"], rng),
        "style": rng.choices(list(style_w), list(style_w.values()))[0],
        "beer": rng.choices(BEERS, [3, 5, 2])[0],
        "reasons": {r: rng.randint(1, 4) for r in reasons},
        "freq": rng.choices([0.3, 0.6, 1.0, 1.5, 2.5], [30, 30, 20, 13, 7])[0],
        "days": sorted(days),
        "window": [start, start + rng.choice([2, 3, 4])],
        "stay": rng.choice([45, 60, 75, 90, 120, 150]),
        "pay": rng.choices(["card", "tab"], [6, 4])[0],
        "tipper": rng.choices(list(sales.TIP_WEIGHTS), [3, 6, 2])[0],
        "walkin": True,
        "joined": now.isoformat(),
    }


# ---------------------------------------------------------------- the human part


def brief(name: str, pronouns: str, skel: dict, now: datetime, city: str, jobs: list[str]) -> str:
    """The skeleton in words, for the model to build a person around."""
    first = name.split()[0]
    reasons = ", ".join(human.REASON_TEXT[r] for r in sorted(skel["reasons"], key=skel["reasons"].get, reverse=True))
    traits = human.trait_words({"big5": skel["big5"]}) or "ordinary in temperament"
    taken = "; ".join(sorted(set(jobs))[:60])
    return (
        f"Create a person who is walking into a craft brewery taproom in {city} for the first time, "
        f"on {now.strftime('%A')} around {now.strftime('%-I %p')}.\n"
        f"Name: {name} ({pronouns}), age {skel['age']}.\n"
        f"Temperament: {traits}. Talks with a {skel['style']} style. Beer knowledge: {skel['beer']}.\n"
        f"Typical reasons they go out: {reasons}.\n"
        f"Their job must be different from the jobs already common here: {taken}.\n"
        f"Write {first}'s job, three personality traits, politics, three interests, one quirk, how they talk, "
        "their usual drink (from the board when you can), where life stands right now (including what brought "
        "them here for the first time), two or three firmly held opinions, up to two topics they steer away from, "
        "and one or two speech habits."
    )


def fill_template(rng: random.Random, skel: dict) -> dict:
    """A complete persona from the pools, for mock mode or when the model call fails."""
    p = pools()
    return {
        **skel,
        "job": rng.choice(p["jobs"]),
        "traits": rng.sample(p["traits"], 3),
        "politics": rng.choice(p["politics"]),
        "drink": rng.choice(menu.names()),
        "interests": rng.sample(p["interests"], 3),
        "quirk": rng.choice(p["quirks"]),
        "voice": rng.choice(p["voices"]),
        "life": rng.choice(p["lives"]),
        "takes": rng.sample(p["takes"], rng.choice([2, 3])),
        "avoid": rng.sample(p["avoid"], rng.choice([0, 1, 2])),
        "tics": rng.sample(p["tics"], rng.choice([1, 2])),
    }


def _text(v, limit: int = MAX_FIELD) -> str:
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def _items(v, lo: int, hi: int) -> list[str]:
    items = [_text(x, 80) for x in v if isinstance(x, str)] if isinstance(v, list) else []
    items = [x for x in items if x]
    return items[:hi] if len(items) >= lo else []


def validate(raw: dict | None, skel: dict, rng: random.Random) -> dict:
    """The skeleton plus the model's part, coerced to the shape the rest of the code needs. A field the model got
    wrong or left out comes from the template, so the result is always a complete persona."""
    persona = fill_template(rng, skel)
    if not isinstance(raw, dict):
        return persona
    for key in ("job", "politics", "quirk", "voice", "life"):
        if value := _text(raw.get(key)):
            persona[key] = value
    for key, lo, hi in (("traits", 2, 4), ("interests", 2, 4), ("takes", 1, 3), ("tics", 1, 2)):
        if values := _items(raw.get(key), lo, hi):
            persona[key] = values
    if isinstance(raw.get("avoid"), list):
        persona["avoid"] = _items(raw["avoid"], 0, 2)
    if drink := menu.match(_text(raw.get("drink"))):
        persona["drink"] = drink
    return persona


def person_row(name: str, pronouns: str) -> dict:
    """The names a Person needs, derived once."""
    return {"name": name, "pronouns": pronouns, "short": short_name(name), "display": display_name(name)}

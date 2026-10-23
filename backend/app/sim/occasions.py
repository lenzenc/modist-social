"""The room's calendar: the rhythm of the week, holidays, live music, private parties, new beer releases, birthdays,
a regular's last night before moving away, and the odd incident that becomes part of the room's history.

Pure functions, seeded from the date like environment.py, so a restart replays the same day and tests need no clock.
The director decides what happens to people; the model only voices it through scene hints.
"""
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import yaml

from app.seed.loader import HERE
from app.sim import environment

LOG_KEEP = 120
HISTORY_KEEP = 60
LORE_DAYS = 45  # how long the room remembers a night
LORE_MIN_VISITS = 3  # newer faces haven't been around for the stories
FAREWELL_ODDS = 1 / 24  # per sim day, with none already planned
FAREWELL_LEAD = (5, 8)  # days between the announcement and the last night
MIN_VISITS_TO_LEAVE = 5
INCIDENT_ODDS = 0.1
MOVED_VISIT_SCALE = 0.05  # someone who moved away comes back about this often, compared with when they lived here
VARIETY_BANDS = (50, 25)  # share of days with something distinct, for green and amber

DAY_PULSE = {0: 0.8, 1: 0.7, 2: 0.9, 3: 1.0, 4: 1.25, 5: 1.35, 6: 0.95}
DAY_LINE = {
    0: "It's a slow Monday.", 1: "It's a slow Tuesday.", 2: "It's a midweek Wednesday.", 3: "It's Thursday, the weekend starting early.",
    4: "It's Friday night.", 5: "It's Saturday, the busiest day of the week.", 6: "It's a lazy Sunday.",
}
CITIES = ["Denver", "Portland", "Austin", "Chicago", "Seattle", "Raleigh", "Boise", "Madison", "Asheville", "Phoenix"]
BANDS = [("The Loons", "local indie folk"), ("Dead Reckoning", "bluegrass"), ("Salt & Pepper Kings", "a soul-and-blues trio"),
         ("The Gentle Giants", "classic-rock covers"), ("Lake Effect", "an acoustic duo"), ("Hot Dish", "a polka-punk band")]
PARTIES = ["a 40th birthday", "a retirement party", "an office happy hour", "a rehearsal dinner", "a bridal shower", "a reunion of old teammates"]


@dataclass(frozen=True)
class Holiday:
    key: str
    title: str
    crowd: float
    mood: float
    line: str
    spark: str
    post: str = ""


@dataclass(frozen=True)
class Band:
    name: str
    genre: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Party:
    what: str
    area: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Incident:
    kind: str
    start: datetime
    minutes: int
    detail: str = ""

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)


# kind -> (weight, minutes it lasts, title in the room's history, words people use when they bring it up, memory)
INCIDENTS = {
    "power_out": (4, 30, "the night the power went out", ["power", "lights", "candle", "dark", "flashlight"],
                  "The power went out at the taproom and we sat around in the dark with phone flashlights."),
    "keg_kicked": (5, 0, "the night {detail} ran out", ["keg", "kicked", "ran out"],
                   "The {detail} keg kicked right in the middle of the night and the whole bar groaned."),
    "fire_alarm": (3, 15, "the night of the fire alarm", ["alarm", "fire", "sidewalk", "evacuat"],
                   "The fire alarm went off and everyone stood out on the sidewalk until the all clear."),
    "proposal": (2, 0, "the night someone got engaged at the bar", ["engaged", "proposal", "proposed", "ring"],
                 "Someone got down on one knee at the bar and the whole room cheered."),
    "snowed_in": (4, 0, "the night we got snowed in", ["snowed in", "blizzard", "snowstorm", "plow"],
                  "A snowstorm trapped the taproom and nobody wanted to be the first to leave."),
}


# ---------------------------------------------------------------- seeds and dates


def _rng(d: date, tag: str) -> random.Random:
    return random.Random(f"{d.isoformat()}|occasion|{tag}")


def _nth(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last(year: int, month: int, weekday: int) -> date:
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return end - timedelta(days=(end.weekday() - weekday) % 7)


@lru_cache(maxsize=8)
def holidays(year: int) -> dict[date, Holiday]:
    thanks = _nth(year, 11, 3, 4)
    table = [
        (date(year, 2, 14), Holiday("valentines", "Valentine's Day", 1.0, 0.05, "It's Valentine's Day: couples at the tables and a few defiant singles at the bar.", "Valentine's Day plans, or the lack of them")),
        (_nth(year, 2, 6, 2), Holiday("superbowl", "Super Bowl Sunday", 1.5, 0.1, "It's Super Bowl Sunday and the whole taproom is wearing someone's colors.", "the big game, the commercials and the snacks", "🏈 Super Bowl Sunday: every seat faces the TV.")),
        (date(year, 3, 17), Holiday("stpatricks", "St. Patrick's Day", 1.5, 0.15, "It's St. Patrick's Day and there is green on half the room.", "St. Patrick's Day and whether anyone is actually Irish", "☘️ St. Patrick's Day at Modist Social.")),
        (date(year, 5, 5), Holiday("cinco", "Cinco de Mayo", 1.2, 0.1, "It's Cinco de Mayo and the food truck has a line.", "Cinco de Mayo and the good taco places")),
        (_last(year, 5, 0), Holiday("memorial", "Memorial Day", 1.2, 0.05, "It's Memorial Day, the unofficial start of summer.", "Memorial Day plans and the first cookout of the year")),
        (date(year, 7, 4), Holiday("july4", "the Fourth of July", 1.1, 0.1, "It's the Fourth of July and fireworks are coming after dark.", "fireworks, the lake and the Fourth of July", "🎆 The Fourth of July: fireworks after dark.")),
        (_nth(year, 9, 0, 1), Holiday("labor", "Labor Day", 1.2, 0.05, "It's Labor Day, the last long weekend of summer.", "the end of summer and the long weekend")),
        *[(_nth(year, 9, 5, n) + timedelta(days=7 * k), Holiday("oktoberfest", "Oktoberfest weekend", 1.2, 0.1, "It's Oktoberfest weekend and the lagers are getting extra attention.", "Oktoberfest and which lager is the best one", "🥨 Oktoberfest weekend: steins up."))
          for n, k in ((3, 0), (3, 1), (3, 2))],
        (date(year, 10, 31), Holiday("halloween", "Halloween", 1.25, 0.1, "It's Halloween: a few costumes in the room and a candy bowl on the bar.", "Halloween costumes, candy and the worst houses on the block", "🎃 Halloween: costumes welcome, candy on the bar.")),
        (thanks - timedelta(days=5), Holiday("friendsgiving", "Friendsgiving weekend", 1.1, 0.1, "It's Friendsgiving weekend and everyone has a dish to brag about.", "Friendsgiving and who is bringing what")),
        (thanks - timedelta(days=1), Holiday("thanksgiving_eve", "the night before Thanksgiving", 1.6, 0.15, "It's the night before Thanksgiving, the biggest bar night of the year, with old friends home from out of town.", "Thanksgiving plans and the relatives who are coming", "🦃 The night before Thanksgiving: the whole town is home.")),
        (thanks, Holiday("thanksgiving", "Thanksgiving", 0.4, 0.0, "It's Thanksgiving and the room is mostly people with somewhere to be, or nowhere.", "Thanksgiving dinner and escaping the relatives")),
        (date(year, 12, 24), Holiday("xmas_eve", "Christmas Eve", 0.8, 0.1, "It's Christmas Eve and the taproom is quiet and a little sentimental.", "Christmas Eve plans and family traditions")),
        (date(year, 12, 31), Holiday("nye", "New Year's Eve", 1.7, 0.2, "It's New Year's Eve and the room is counting down to midnight.", "resolutions, the year behind you and midnight plans", "🎉 New Year's Eve: the countdown is on.")),
    ]
    return dict(table)


def holiday(d: date) -> Holiday | None:
    return holidays(d.year).get(d)


def crowd(now: datetime) -> float:
    """How busy the day is, as a multiplier on arrivals: the weekday's rhythm times whatever holiday it is."""
    h = holiday(now.date())
    return DAY_PULSE[now.weekday()] * (h.crowd if h else 1.0)


def mood_shift(now: datetime) -> float:
    h = holiday(now.date())
    return h.mood if h else 0.0


# ---------------------------------------------------------------- music, parties, releases


def band_for(d: date) -> Band | None:
    if d.weekday() not in (4, 5):
        return None
    r = _rng(d, "band")
    if r.random() >= 0.45:
        return None
    name, genre = r.choice(BANDS)
    start = datetime.combine(d, time(r.choice([19, 20])))
    return Band(name, genre, start, start + timedelta(hours=r.choice([2, 2.5])))


def band_on(now: datetime) -> Band | None:
    b = band_for(now.date())
    return b if b and b.start <= now < b.end else None


def party_for(d: date) -> Party | None:
    if d.weekday() not in (3, 4, 5):
        return None
    r = _rng(d, "party")
    if r.random() >= 0.25:
        return None
    start = datetime.combine(d, time(r.choice([17, 18, 19])))
    area = "inside-tables" if d.month in (11, 12, 1, 2, 3) else r.choice(["patio", "inside-tables"])
    return Party(r.choice(PARTIES), area, start, start + timedelta(hours=3))


def party_on(now: datetime) -> Party | None:
    p = party_for(now.date())
    return p if p and p.start <= now < p.end else None


def music_off(now: datetime) -> bool:
    """A band is playing or the power is out, so the jukebox stays quiet."""
    return band_on(now) is not None or outage(now)


@lru_cache(maxsize=1)
def release_pool() -> list[dict]:
    return yaml.safe_load((HERE / "releases.yaml").read_text())


def release_due(d: date) -> bool:
    """Every other Thursday."""
    return d.weekday() == 3 and (d.toordinal() // 7) % 2 == 0


def next_release(released: list[dict]) -> dict | None:
    have = {r["name"] for r in released}
    return next((r for r in release_pool() if r["name"] not in have), None)


def release_entry(name: str) -> dict | None:
    return next((r for r in release_pool() if r["name"] == name), None)


def release_tonight(released: list[dict], now: datetime) -> dict | None:
    day = now.strftime("%Y-%m-%d")
    name = next((r["name"] for r in released if r["day"] == day), "")
    return release_entry(name) if name else None


# ---------------------------------------------------------------- people


def birthday(pid: str, persona: dict) -> tuple[int, int]:
    """(month, day) of a person's birthday: the persona's `birthday: MM-DD` if it sets one, else a stable pick from their id."""
    if raw := persona.get("birthday"):
        m, d = str(raw).split("-")
        return int(m), int(d)
    r = random.Random(f"birthday|{pid}")
    return r.randint(1, 12), r.randint(1, 28)


def is_birthday(pid: str, persona: dict, d: date) -> bool:
    return birthday(pid, persona) == (d.month, d.day)


def roll_farewell(candidates: list[str], day: date, rng: random.Random) -> dict | None:
    """Rarely, one regular announces they are moving away. The plan is where, and which night is their last."""
    if not candidates or rng.random() >= FAREWELL_ODDS:
        return None
    night = day + timedelta(days=rng.randint(*FAREWELL_LEAD))
    return {"pid": rng.choice(candidates), "city": rng.choice(CITIES), "announced": day.isoformat(), "night": night.isoformat()}


def farewell_phase(plan: dict | None, day: date) -> str:
    """'' when nothing is planned, then 'announced' until the last night, 'tonight', and 'over' after it."""
    if not plan:
        return ""
    night = date.fromisoformat(plan["night"])
    return "announced" if day < night else "tonight" if day == night else "over"


# ---------------------------------------------------------------- incidents


def incident_for(d: date) -> Incident | None:
    r = _rng(d, "incident")
    if r.random() >= INCIDENT_ODDS:
        return None
    kinds = [k for k in INCIDENTS if k != "snowed_in" or "snow" in environment.weather(datetime.combine(d, time(12)))]
    kind = r.choices(kinds, [INCIDENTS[k][0] for k in kinds])[0]
    from app.sim import menu  # local import: menu is cheap but keeps this module light for tests

    detail = r.choice(menu.names()) if kind == "keg_kicked" else ""
    start = datetime.combine(d, time(17)) + timedelta(minutes=r.randint(0, 179))
    return Incident(kind, start, INCIDENTS[kind][1], detail)


def incident_active(now: datetime) -> Incident | None:
    inc = incident_for(now.date())
    return inc if inc and inc.minutes and inc.start <= now < inc.end else None


def outage(now: datetime) -> bool:
    inc = incident_active(now)
    return bool(inc and inc.kind == "power_out")


def history_row(day: str, kind: str, title: str, who: list[str], keys: list[str]) -> dict:
    return {"day": day, "kind": kind, "title": title, "who": who, "keys": keys}


def incident_row(inc: Incident, day: str, who: list[str]) -> dict:
    _, _, title, keys, _ = INCIDENTS[inc.kind]
    return history_row(day, inc.kind, title.format(detail=inc.detail), who, keys + ([inc.detail.lower()] if inc.detail else []))


def incident_memory(inc: Incident) -> str:
    return INCIDENTS[inc.kind][4].format(detail=inc.detail)


def incident_post(inc: Incident) -> str:
    return {
        "power_out": "💡 The power goes out. Candles and phone flashlights come out.",
        "keg_kicked": f"🛢️ The {inc.detail} keg kicks. The bartenders are changing it over.",
        "fire_alarm": "🚨 The fire alarm goes off and everyone files out to the sidewalk.",
        "snowed_in": "❄️ The snow is coming down sideways. Nobody is driving anywhere soon.",
    }.get(inc.kind, "")


def incident_end_post(inc: Incident) -> str:
    return {"power_out": "💡 The lights come back on and the room cheers.", "fire_alarm": "🚨 All clear. Everyone files back in."}.get(inc.kind, "")


def incident_line(now: datetime) -> str:
    inc = incident_active(now)
    return {"power_out": "The power is out; the taproom is lit by candles and phone flashlights and the jukebox is dead.",
            "fire_alarm": "The fire alarm went off and everyone is outside on the sidewalk waiting for the all clear."}.get(inc.kind, "") if inc else ""


# ---------------------------------------------------------------- what goes into a scene


def room_bits(now: datetime, released: list[dict]) -> list[str]:
    """The calendar's part of the room line: the day's rhythm and whatever is on tonight."""
    bits = [DAY_LINE[now.weekday()]]
    if h := holiday(now.date()):
        bits.append(h.line)
    if b := band_on(now):
        bits.append(f"{b.name} ({b.genre}) is playing a set; the room is loud with live music.")
    if p := party_on(now):
        bits.append(f"{p.what.capitalize()} has the {p.area.replace('-', ' ')} booked until {p.end.strftime('%-I%p').lower()}.")
    if r := release_tonight(released, now):
        bits.append(f"Tonight is the release of {r['name']} ({r['style']}), new on the board.")
    if line := incident_line(now):
        bits.append(line)
    return bits


def label(now: datetime, released: list[dict]) -> str:
    """A short name for what's special tonight, for the header; empty on an ordinary night."""
    if inc := incident_active(now):
        return {"power_out": "Power outage", "fire_alarm": "Fire alarm"}.get(inc.kind, "")
    if b := band_on(now):
        return f"Live music: {b.name}"
    if r := release_tonight(released, now):
        return f"Release night: {r['name']}"
    if h := holiday(now.date()):
        return h.title[0].upper() + h.title[1:]
    if p := party_on(now):
        return "Private party"
    return ""


def spark(now: datetime, released: list[dict], history: list[dict], leaver: str, rng: random.Random) -> str:
    """A topic the calendar hands people when the talk flags: tonight's holiday, a new beer, someone leaving, a night to remember."""
    options = []
    if h := holiday(now.date()):
        options.append(h.spark)
    if r := release_tonight(released, now):
        options.append(f"the new {r['name']}, {r['blurb']}")
    if leaver:
        options.append(f"{leaver} moving away")
    day = now.strftime("%Y-%m-%d")
    for row in history[-3:]:
        if row["kind"] in INCIDENTS and row["day"] != day and (now.date() - date.fromisoformat(row["day"])).days <= LORE_DAYS:
            options.append(f"remembering {row['title']}")
    return rng.choice(options) if options else ""


def lore_line(history: list[dict], now: datetime, visits: int, rng: random.Random) -> str:
    """What the regulars still bring up, now and then. Newer faces weren't there for it."""
    if visits < LORE_MIN_VISITS or rng.random() >= 0.3:
        return ""
    today = now.date()
    recent = [r for r in history if 0 < (today - date.fromisoformat(r["day"])).days <= LORE_DAYS and r["kind"] != "birthday"]
    if not recent:
        return ""
    row = rng.choice(recent[-4:])
    ago = (today - date.fromisoformat(row["day"])).days
    when = "last week" if ago < 10 else f"{ago // 7} weeks ago"
    return f"Regulars still bring up {row['title']} ({when}). Mention it only if it fits."


def birthday_note(honoree: str, me: bool) -> str:
    return "It's your birthday today, and you're feeling it a little." if me else f"It's {honoree}'s birthday today."


def farewell_note(plan: dict, leaver: str, me: bool, phase: str) -> str:
    when = "tonight is your last night before the move" if phase == "tonight" else "your move is only days away"
    if me:
        return f"You're moving to {plan['city']} and {when}. It's bittersweet."
    return (f"{leaver} is moving to {plan['city']} and tonight is their last night in town." if phase == "tonight"
            else f"{leaver} is moving to {plan['city']} soon.")


def back_note(city: str, leaver: str, me: bool) -> str:
    return (f"You moved to {city} a while ago and are back in town for a visit." if me
            else f"{leaver} moved to {city} and is back in town for a visit.")


# ---------------------------------------------------------------- the scorecard


def static_kinds(now: datetime, released: list[dict]) -> set[str]:
    """What the calendar alone put on this day."""
    d = now.date()
    out = set()
    if holiday(d):
        out.add("holiday")
    if band_for(d):
        out.add("band")
    if party_for(d):
        out.add("party")
    if release_tonight(released, now):
        out.add("release")
    return out


def report(log: list[dict], history: list[dict], lines: list[tuple[date, str, str]], upto: date | None = None) -> dict:
    """How much the days differ, and whether the room remembers its own nights. A calendar of identical days is the failure."""
    n = len(log)
    distinct = sum(1 for r in log if r["kinds"])
    rate = None if n < 3 else round(100 * distinct / n)
    band = "none" if rate is None else "green" if rate >= VARIETY_BANDS[0] else "amber" if rate >= VARIETY_BANDS[1] else "red"
    counts: dict[str, int] = {}
    for r in log:
        for k in r["kinds"]:
            counts[k] = counts.get(k, 0) + 1
    seen = 0
    for row in history:
        d = date.fromisoformat(row["day"])
        if upto is not None and d > upto:
            continue
        keys = [k.lower() for k in row["keys"]]
        if any(day > d and any(k in text.lower() for k in keys) for day, _, text in lines):
            seen += 1
    return {"rate": rate, "band": band, "days": n, "counts": counts, "history": len(history), "recalled": seen}

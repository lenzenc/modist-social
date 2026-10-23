"""Bartenders' inner lives: fatigue over a shift, a rough night now and then, mistakes, favourites, a pet peeve, and
friction with the coworker.

Pure functions over a Shift, a persona dict and a RelState, in the style of drunk.py and dynamics.py. Everything is
deterministic given an rng; the model only voices what the code decides, through the hints in the scene. A bartender's
mood lives on their PersonState (so human.nudge_mood and human.blend_mood work on it); the Shift holds the rest.
"""
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.sim import drunk, human
from app.sim.beats import pos

LOG_KEEP = 300
ROUGH_ODDS = 0.15  # chance a shift starts as a rough night
ROUGH_MOOD = -0.35
ROUGH_FATIGUE = 1.5  # a rough night wears them out this much faster
FATIGUE_PER_HOUR = 0.07  # on an ordinary shift, before the crowd
CROWD_FATIGUE = 0.004  # more per hour, for each guest in the room
QUEUE_FATIGUE = 0.05  # more per hour, for each guest waiting on a bartender
QUEUE_LONG = 3  # a line this long drags the mood down
REST_PER_HOUR = 0.03  # a quiet room lets them catch their breath
TIRED, WORN = 0.4, 0.7  # fatigue at which it starts to show, and at which it really does
MISTAKE_BASE = 0.01
MISTAKE_MAX = 0.25
FAVORITE = (50, 45)  # (familiarity, affinity) for a favourite regular
IRRITANT = (30, -10)  # (familiarity, affinity at most) for a guest who gets on their nerves
IMPATIENT_MIN = 2.0  # minutes in line before an impatient guest bothers a bartender
CAMPER_MIN = 90.0  # minutes on a stool nursing a drink or two
FRICTION_BASE = 0.12
FRICTION_MAX = 0.4
POUR_OZ, PINT_OZ = 4, 16  # a taster is four ounces, against the pint a guest gets
POURS = (2, 4)  # tasters in a shift when the persona doesn't say
FIRST_POUR_MIN = 45  # nobody pours one straight off clock-in
POUR_GAP_MIN = (50, 110)
BT_LOOSE, BT_BUZZED, BT_STOP = 0.08, 0.18, 0.25  # buzz at which it shows, at which it's a real buzz, and past which they stop pouring
TEXTURED_BAND = (50, 25)  # share of shifts with anything happening, for green and amber

PEEVES = {
    "bad_tipper": "guests who tip nothing",
    "drunk": "guests who are visibly drunk",
    "impatient": "guests who hover and sigh while you're busy",
    "indecisive": "guests who can't pick and make you recite the whole board",
    "camper": "guests who nurse one beer at the bar for hours",
}
MISTAKES = {
    "wrong_pour": ["🍺 {p} pours a {wrong} instead of the {right}, catches it, and pours the right one."],
    "spill": ["{p} knocks a pint over behind the bar and grabs a rag.",
              "{p} fumbles a glass and sloshes beer down {pos} apron."],
}
STATE_ROUGH = "You're having a rough night ({why}). It shows a little, though you're professional about it."
STATE_WORN = "You've been on your feet for hours and you're worn out: shorter, flatter, a bit slow."
STATE_TIRED = "You're starting to feel the shift in your feet."
PEEVE_HINT = "This guest is one of your pet peeves ({peeve}). Don't be rude, but let a little of it show."
FAVORITE_HINT = "{name} is one of your favorite regulars: warmer and chattier than usual."
IRRITANT_HINT = "{name} gets on your nerves a bit: stay polite but clipped."
GRIPE_HINT = "You're annoyed that {name} left you to handle the rush alone. Bring it up with them, in your own way."
GRIPE_ANSWER_HINT = "{name} is annoyed that you were off chatting while the line built. Take it on the chin: own it or deflect."
LOOK_TEXT = ["{a} shoots {b} a look as the line builds.", "{a} glances over at {b}, who is deep in a chat, and sighs."]


@dataclass
class Shift:
    started: datetime
    fatigue: float = 0.0
    rough: str = ""  # why the night is rough, or ""
    served: int = 0
    wrong: int = 0
    spills: int = 0
    peeves: int = 0
    gripes: int = 0
    tips_good: int = 0
    tips_none: int = 0
    low: float = 0.0  # the lowest and highest the mood got
    high: float = 0.0
    gripe: str = ""  # the coworker (id) they are sore at; voiced in the next staff chat
    grudge: str = ""  # that coworker's name, kept for the end-of-shift memory
    owed: str = ""  # the coworker (name) who has just aired a gripe at them and is owed an answer
    made_up: bool = False  # they have answered a gripe; the director settles the score
    pour_goal: int = 0  # tasters they mean to have this shift
    pours: int = 0
    next_pour_at: datetime | None = None
    poured: list[str] = field(default_factory=list)
    peak_buzz: float = 0.0


def start_shift(persona: dict, rng: random.Random, now: datetime) -> Shift:
    s = Shift(started=now)
    lo, hi = (persona.get("pours") or POURS)[:2]
    s.pour_goal = rng.randint(lo, hi) + (1 if human.trait(persona, "c") <= 2 and rng.random() < 0.5 else 0)
    s.next_pour_at = now + timedelta(minutes=FIRST_POUR_MIN + rng.uniform(0, 30))
    reasons = [r for r in (persona.get("rough") or []) if r]
    if reasons and rng.random() < ROUGH_ODDS:
        s.rough = rng.choice(reasons)
    return s


def opening_mood(persona: dict, rng: random.Random, shift: Shift) -> float:
    m = human.opening_mood(persona, rng)
    return max(-1.0, m + ROUGH_MOOD) if shift.rough else m


def note_mood(s: Shift, mood: float) -> None:
    s.low, s.high = min(s.low, mood), max(s.high, mood)


def tire(s: Shift, persona: dict, dt_min: float, guests: int, queue: int) -> None:
    """Fatigue builds with time on shift, a full room and a line; a quiet room lets it ease."""
    if guests <= 2 and queue == 0:
        s.fatigue = max(0.0, s.fatigue - REST_PER_HOUR * dt_min / 60)
        return
    rate = FATIGUE_PER_HOUR + CROWD_FATIGUE * min(guests, 25) + QUEUE_FATIGUE * queue
    if human.trait(persona, "c") <= 2:
        rate *= 1.3
    if human.trait(persona, "n") >= 4:
        rate *= 1.2
    if s.rough:
        rate *= ROUGH_FATIGUE
    s.fatigue = min(1.0, s.fatigue + rate * dt_min / 60)


def line_mood(queue: int, dt_min: float) -> float:
    """How much a long line weighs on the mood over dt_min."""
    return -0.1 * dt_min / 60 * (queue - QUEUE_LONG + 1) if queue >= QUEUE_LONG else 0.0


def worn(s: Shift) -> bool:
    return s.fatigue >= WORN


# ---------------------------------------------------------------- tasters


def pour_strength(abv: float | None) -> float:
    """How hard a four-ounce taster hits, in the units human.add_drink takes (a pint of ordinary beer is 1.0)."""
    return drunk.strength(abv) * POUR_OZ / PINT_OZ


def wants_pour(s: Shift, buzz: float, now: datetime, busy: bool, queue: int) -> bool:
    """Due, under their goal, still only mildly buzzed, and in a lull: a bartender doesn't taste with a line waiting."""
    return bool(s.next_pour_at and now >= s.next_pour_at and s.pours < s.pour_goal and buzz < BT_STOP and not busy and queue == 0)


def pick_pour(persona: dict, released_tonight: list[str], names: list[str], rng: random.Random) -> tuple[str, str]:
    """(beer, why): a beer new tonight first, then a favourite named in the persona, else a quality check on anything."""
    if new := [n for n in released_tonight if n in names]:
        return rng.choice(new), "new"
    text = str(persona.get("drink", "")).lower()
    if fav := [n for n in names if n.lower() in text]:
        return rng.choice(fav), "favorite"
    return rng.choice(names), "check"


def pour_text(rng: random.Random, b, name: str, why: str) -> str:
    if why == "new":
        return rng.choice([f"🍺 {b.short} tastes a splash of the new {name} to check it.", f"🍺 {b.short} pours a 4oz taster of the new {name}."])
    if why == "favorite":
        return rng.choice([f"🍺 {b.short} pours {pos(b)}self a 4oz taster of {name}.", f"🍺 {b.short} sneaks a small {name} between orders."])
    return rng.choice([f"🍺 {b.short} pours a 4oz taster of {name} as a quality check.", f"🍺 {b.short} tries a little {name} to see how it's pouring."])


def buzz_hint(buzz: float) -> str:
    if buzz >= BT_BUZZED:
        return ("You're a little buzzed from a few tasters over the shift: chattier, more candid, a bit more teasing, "
                "still fully on top of the job. Never sloppy.")
    if buzz >= BT_LOOSE:
        return "You've had a taster or two: a touch looser and quicker to laugh."
    return ""


def buzz_word(buzz: float) -> str:
    return "a little buzzed" if buzz >= BT_BUZZED else "a taster or two in" if buzz >= BT_LOOSE else ""


# ---------------------------------------------------------------- mistakes


def mistake_chance(s: Shift, persona: dict, guests: int, buzz: float = 0.0) -> float:
    c = MISTAKE_BASE + 0.04 * buzz + 0.05 * s.fatigue + (0.03 if s.rough else 0.0) + 0.01 * max(0, 3 - human.trait(persona, "c"))
    c += 0.02 if guests > 10 else 0.0
    return min(MISTAKE_MAX, c)


def roll_mistake(rng: random.Random) -> str:
    return rng.choices(["wrong_pour", "spill"], [3, 2])[0]


def mistake_text(rng: random.Random, kind: str, b, wrong: str = "", right: str = "") -> str:
    return rng.choice(MISTAKES[kind]).format(p=b.short, pos=pos(b), wrong=wrong, right=right)


# ---------------------------------------------------------------- how they feel about guests


def favorite(rel) -> bool:
    return rel.familiarity >= FAVORITE[0] and rel.affinity >= FAVORITE[1]


def irritant(rel) -> bool:
    return rel.familiarity >= IRRITANT[0] and rel.affinity <= IRRITANT[1]


def opinion(rel, short: str) -> str:
    if favorite(rel):
        return FAVORITE_HINT.format(name=short)
    if irritant(rel):
        return IRRITANT_HINT.format(name=short)
    return ""


def peeve_hit(key: str, guest, waited_min: float = 0.0, stayed_min: float = 0.0, intent_kind: str = "") -> bool:
    """Does this guest, right now, trip the bartender's pet peeve? Each peeve is something the code can see."""
    if key == "bad_tipper":
        return guest.persona.get("tipper") == "low"
    if key == "drunk":
        return drunk.tier(guest.buzz) in ("drunk", "wasted")
    if key == "impatient":
        return waited_min >= IMPATIENT_MIN
    if key == "indecisive":
        return intent_kind == "rec"
    if key == "camper":
        return guest.seated and guest.drinks <= 2 and stayed_min >= CAMPER_MIN
    return False


def peeve_hint(key: str) -> str:
    return PEEVE_HINT.format(peeve=PEEVES.get(key, "a certain kind of guest"))


def state_hint(s: Shift, mood: float, buzz: float = 0.0) -> str:
    parts = []
    if s.rough:
        parts.append(STATE_ROUGH.format(why=s.rough))
    if s.fatigue >= WORN:
        parts.append(STATE_WORN)
    elif s.fatigue >= TIRED:
        parts.append(STATE_TIRED)
    if (w := human.mood_word(mood)) and not s.rough:
        parts.append(f"You're {w}.")
    if h := buzz_hint(buzz):
        parts.append(h)
    return " ".join(parts)


def tired_word(s: Shift) -> str:
    return "worn out" if s.fatigue >= WORN else "tired" if s.fatigue >= TIRED else "fresh"


def mood_scale(s: Shift, mood: float, buzz: float = 0.0) -> float:
    """How readily a bartender chats and lingers: lower when tired or in a bad mood, a touch higher when cheerful."""
    return max(0.3, 1.0 - 0.5 * s.fatigue + 0.2 * mood + 0.6 * buzz)


# ---------------------------------------------------------------- friction with the coworker


def friction_chance(worker: Shift, affinity: int, queue: int) -> float:
    """A bartender working a line while the other chats: how likely it is to become a grievance."""
    if queue < 1:
        return 0.0
    c = FRICTION_BASE + 0.2 * worker.fatigue + (0.1 if worker.rough else 0.0) + max(0, -affinity) / 200 - max(0, affinity) / 400
    return max(0.02, min(FRICTION_MAX, c))


def look(rng: random.Random, a: str, b: str) -> str:
    return rng.choice(LOOK_TEXT).format(a=a, b=b)


# ---------------------------------------------------------------- the end of a shift


def textured(s: Shift) -> bool:
    return bool(s.wrong or s.spills or s.rough or s.peeves or s.gripes or s.fatigue >= WORN or s.low <= -0.45 or s.high >= 0.5
                or s.peak_buzz >= BT_BUZZED)


def end_of_shift(s: Shift, pid: str, day: str) -> tuple[str, int, dict]:
    """(memory text, importance, log row) for a shift that is over."""
    bits = []
    if s.rough:
        bits.append(f"a rough night ({s.rough})")
    if s.wrong:
        bits.append(f"{s.wrong} wrong pour{'s' if s.wrong != 1 else ''}")
    if s.spills:
        bits.append(f"{s.spills} spill{'s' if s.spills != 1 else ''}")
    if s.fatigue >= WORN:
        bits.append("feet killing you")
    if s.gripes and s.grudge:
        bits.append(f"{s.grudge} left you with the rush")
    if s.peeves:
        bits.append("guests who got under your skin")
    if s.pours:
        bits.append(f"{s.pours} taster{'s' if s.pours != 1 else ''} ({', '.join(dict.fromkeys(s.poured))})")
    if s.peak_buzz >= BT_BUZZED:
        bits.append("a little buzzed by close")
    text = f"End of shift: {', '.join(bits)}." if bits else f"An ordinary shift: {s.served} drinks poured, nothing much to report."
    row = {"day": day, "pid": pid, "served": s.served, "wrong": s.wrong, "spills": s.spills, "rough": bool(s.rough),
           "peeves": s.peeves, "gripes": s.gripes, "worn": s.fatigue >= WORN, "textured": textured(s),
           "pours": s.pours, "peak": round(s.peak_buzz, 2)}
    return text, 4 if bits else 2, row


def report(log: list[dict]) -> dict:
    """Share of shifts with anything in them. Every shift being the same is the failure: the room's constant presence has no texture."""
    n = len(log)
    hit = sum(1 for r in log if r["textured"])
    rate = None if n < 3 else round(100 * hit / n)
    band = "none" if rate is None else "green" if rate >= TEXTURED_BAND[0] else "amber" if rate >= TEXTURED_BAND[1] else "red"
    return {"rate": rate, "band": band, "shifts": n, "wrong_pours": sum(r["wrong"] for r in log),
            "spills": sum(r["spills"] for r in log), "rough": sum(1 for r in log if r["rough"]),
            "gripes": sum(r["gripes"] for r in log), "peeves": sum(r["peeves"] for r in log),
            "pours_avg": round(sum(r.get("pours", 0) for r in log) / n, 1) if n else 0.0,
            "buzzed": sum(1 for r in log if r.get("peak", 0) >= BT_BUZZED)}

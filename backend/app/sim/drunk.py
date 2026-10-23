"""Drinking and what comes of it: how drunk someone is, how the bartender treats them, and the mess they leave behind.

Pure functions over a PersonState, in the style of human.py and life.py. Everything here is deterministic given an rng;
the model only voices it, through the hints in speech_hint and bartender_note.
"""
import random
from datetime import datetime

from app.sim.beats import pos

TIPSY, DRUNK, WASTED = 0.25, 0.5, 0.75  # buzz at which each tier starts
CUT_DRINKS = 7  # a bartender cuts off anyone this many in, however they seem
STRONG_ABV = 6.0  # a drink at this strength adds buzz at the ordinary rate
STRENGTH = (0.6, 2.0)
WATER_MIN = (30, 45)  # minutes a guest spends on water after switching; buzz wears off faster meanwhile
WATER_DECAY = 1.5
SLOW_WAIT = 1.6  # a guest the bartender is slowing down waits this much longer between rounds
CUT_LEAVE_MIN = (15, 40)  # minutes a cut-off guest stays before heading home
SLOP_PER_HOUR = {"drunk": 0.35, "wasted": 0.9}
RIDE_TIPSY = 0.2  # chance a merely tipsy guest calls a ride anyway
WATER_ODDS = {"tipsy": 0.0, "drunk": 0.3, "wasted": 0.6}
WATER_PERSONA = ("designated driver", "orders water", "drives home")  # persona text that makes water likelier
MEMORY_IMPORTANCE = 7
LOG_KEEP = 300

SLOPS = {
    "dropped_glass": ["💥 {p} drops {pos} {drink}: glass everywhere, and a cheer from the bar.",
                      "💥 {p} fumbles {pos} {drink} and it shatters on the floor."],
    "spill": ["{p} sloshes {pos} {drink} across the table and mops at it with a napkin.",
              "{p} gestures too hard and sends {pos} {drink} down the front of {pos} shirt."],
}


def tier(buzz: float) -> str:
    return "wasted" if buzz >= WASTED else "drunk" if buzz >= DRUNK else "tipsy" if buzz >= TIPSY else "sober"


def strength(abv: float | None) -> float:
    """How hard a drink hits, against an ordinary 6% beer. THC drinks and the odd unlisted one count as ordinary."""
    if abv is None:
        return 1.0
    if abv <= 0:
        return 0.0
    return max(STRENGTH[0], min(STRENGTH[1], abv / STRONG_ABV))


def service(p) -> str:
    """How the bartender treats this guest: pour | slow | cut."""
    t = tier(p.buzz)
    if p.cut_off or p.drinks >= CUT_DRINKS or t == "wasted":
        return "cut"
    return "slow" if t == "drunk" else "pour"


def wants_water(p, rng: random.Random) -> bool:
    """A guest at the point of switching themselves to water (the odds are higher for the designated driver)."""
    odds = WATER_ODDS.get(tier(p.buzz), 0.0)
    blob = " ".join(str(v) for v in (p.persona.get("quirk"), p.persona.get("life"), *(p.persona.get("traits") or []))).lower()
    if odds and any(k in blob for k in WATER_PERSONA):
        odds = min(1.0, odds + 0.3)
    return rng.random() < odds


def decay_mult(p, now: datetime) -> float:
    return WATER_DECAY if p.on_water_until and now < p.on_water_until else 1.0


# ---------------------------------------------------------------- what the model hears


def speech_hint(buzz: float) -> str:
    t = tier(buzz)
    if t == "tipsy":
        return "You've had a few: you're looser, chattier and more candid than usual."
    if t == "drunk":
        return ("You're properly drunk: louder than you realise, repeating yourself, a word or two slurred "
                "(\"shhure\", \"honeshtly\"), and quick to get sentimental. Still readable.")
    if t == "wasted":
        return ("You're very drunk: slurring, too loud, losing the thread mid-sentence, announcing your feelings and "
                "saying more than you should. Keep it short and a bit of a mess.")
    return ""


def bartender_note(guest, policy: str) -> str:
    if policy == "cut":
        return (f"{guest.short} has had {guest.drinks} and is clearly drunk. Cut them off, firmly but kindly: no more beer, "
                "a free water instead, and suggest a ride home. Don't pour another alcoholic drink.")
    if policy == "slow":
        return (f"{guest.short} is getting drunk ({guest.drinks} so far). Slow them down: ask if they'd like a water with this, "
                "and keep an eye on them.")
    return ""


def guest_note(guest, policy: str, water: bool) -> str:
    """Order-time hint for the guest. Cut-off guests are told rather than asked."""
    if policy == "cut":
        return "The bartender may well cut you off; you're a bit out of it. Take it with whatever grace you have, and accept the water."
    if water:
        return "You're feeling it and think you should slow down: ask for a water instead (put Water in drink)."
    if policy == "slow":
        return "You're feeling it, but you may want one more."
    return ""


def overshare_hint(names: list[str]) -> str:
    to = " and ".join(names) if names else "the room"
    return f"You've had too much and the filter is gone: blurt out something personal you'd normally keep to yourself, in front of {to}."


# ---------------------------------------------------------------- sloppy moments


def slop_chance(t: str, dt_min: float) -> float:
    per_hour = SLOP_PER_HOUR.get(t, 0.0)
    return 1 - (1 - min(per_hour / 60, 0.99)) ** max(dt_min, 0.0)


def roll_slop(rng: random.Random, p, in_chat: bool) -> str:
    """dropped_glass | spill | overshare, or "" when nothing fits (no drink in hand and nobody to talk to)."""
    pool = {}
    if p.drink:
        pool.update(dropped_glass=3, spill=2)
    if in_chat:
        pool["overshare"] = 3
    return rng.choices(list(pool), list(pool.values()))[0] if pool else ""


def slop_text(rng: random.Random, kind: str, p) -> str:
    return rng.choice(SLOPS[kind]).format(p=p.short, pos=pos(p), drink=(p.drink or "drink").split(" - ")[0])


# ---------------------------------------------------------------- getting home


def ride_home(p, mates: list, rng: random.Random):
    """(how, driver id or None) for someone heading out, or None when they walk or drive themselves.

    `mates` are the members of their party still in the room. A sober friend drives; otherwise a rideshare.
    """
    t = tier(p.buzz)
    if t == "sober" or (t == "tipsy" and rng.random() >= RIDE_TIPSY):
        return None
    for q in mates:
        if q.id != p.id and q.present and tier(q.buzz) == "sober":
            return "driver", q.id
    return "rideshare", None


# ---------------------------------------------------------------- the morning after


def record(p, day: str, ride: str) -> dict | None:
    """What a visit comes to, if anything: kept for the next day's memory and for the scorecard."""
    peak = tier(p.peak_buzz)
    if peak not in ("drunk", "wasted"):
        return None
    return {"day": day, "pid": p.id, "drinks": p.drinks, "peak": peak, "slops": list(p.slops), "cut_off": p.cut_off,
            "water": p.on_water_until is not None, "ride": ride, "with": sorted(p.overshared_with), "written": False}


def regret_text(h: dict) -> str:
    bits = [f"{h['drinks']} drink{'s' if h['drinks'] != 1 else ''}"]
    if h["cut_off"]:
        bits.append("got cut off")
    bits += h["slops"]
    if h["ride"] == "rideshare":
        bits.append("had to call a rideshare")
    elif h["ride"] == "driver":
        bits.append("needed a friend to drive you home")
    mood = "properly embarrassed" if h["peak"] == "wasted" else "a bit sheepish"
    return f"You overdid it at the taproom last night ({', '.join(bits)}). You're {mood} about it and a little hungover."


def regret_followups(h: dict, names: dict[str, str]) -> list[tuple[str, list[str]]]:
    """(text, about) pairs: people to say sorry to, or thank."""
    out = []
    if h["with"]:
        who = [names[i] for i in h["with"] if i in names]
        if who:
            out.append((f"Check in with {' and '.join(who)}: you said more than you meant to last night.", list(h["with"])))
    return out


def hangover_goal(goal: int) -> int:
    return max(1, goal - 1)


def consequences(log: list[dict]) -> dict:
    """Does being drunk change anything? Share of drunk visits where something happened (a cut-off, a mess, water, a ride).

    All of them is natural; if drunk guests keep drinking and nothing happens, the room isn't taking it seriously.
    """
    n = len(log)
    hit = sum(1 for h in log if h["cut_off"] or h["slops"] or h["water"] or h["ride"])
    rate = None if n < 3 else round(100 * hit / n)
    band = "none" if rate is None else "green" if rate >= 70 else "amber" if rate >= 40 else "red"
    return {"rate": rate, "band": band, "visits": n, "cut_offs": sum(h["cut_off"] for h in log),
            "messes": sum(len(h["slops"]) for h in log), "rides": sum(1 for h in log if h["ride"])}

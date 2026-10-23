"""Inner life for the people in the taproom: traits, mood, buzz, social battery, needs, and how they shape a turn.

Pure functions over a persona dict and a PersonState, in the style of god.py, so every rule is easy to test.
"""
import random
from datetime import datetime, timedelta

from app.sim import drunk

MOODS = {"good": 0.6, "fine": 0.1, "meh": -0.2, "annoyed": -0.5, "down": -0.7}
MOOD_TAGS = tuple(MOODS)
NEEDS = {
    "restroom": "use the restroom",
    "call": "take a phone call",
    "air": "step outside for some air",
    "food": "grab something from the food truck",
}
REASON_TEXT = {
    "unwind": "here to unwind after the day",
    "catch_up": "hoping to catch up with friends",
    "solo": "here for some time to yourself",
    "game": "here to watch the game",
    "date": "here with something like a date in mind",
    "work": "working",
}
ACTIVITIES = [
    "{} scrolls through their phone.",
    "{} people-watches over their pint.",
    "{} reads something on their phone.",
    "{} studies the chalkboard like it owes them money.",
]
STYLE_TEXT = {
    "listener": "You listen more than you talk: short replies and good follow-up questions.",
    "storyteller": "You tell stories, with details and tangents.",
    "joker": "You joke and tease a lot, and not every joke lands.",
    "debater": "You like to argue a point, and you push back when you disagree.",
    "asker": "You ask people about themselves and their lives.",
}
BEER_TEXT = {
    "newbie": "You're new to craft beer: you ask questions and order by what sounds good.",
    "casual": "You like beer but you're no expert.",
    "nerd": "You know beer deeply (styles, hops, process) and you have opinions about it.",
}
# Trait -> words, only at the ends of the scale; the middle is unremarkable and left out.
_WORDS = {
    "e": {1: "quiet and reserved", 2: "a bit reserved", 4: "outgoing", 5: "very outgoing and loud"},
    "a": {1: "blunt and quick to argue", 2: "a little prickly", 4: "warm and accommodating", 5: "very agreeable, hates conflict"},
    "n": {1: "unflappable", 4: "easily rattled", 5: "anxious and takes things hard"},
    "o": {1: "set in their ways", 2: "prefers the familiar", 4: "curious about new things", 5: "restless and endlessly curious"},
    "c": {1: "scattered and impulsive", 2: "a bit disorganized", 4: "organized and punctual", 5: "very disciplined"},
}
LOW_BATTERY = 0.3
RECOVER_PER_HOUR = 0.5
BUZZ_DECAY_PER_HOUR = 0.1


def trait(persona: dict, key: str) -> int:
    """A Big Five score 1-5; 3 when the persona has none."""
    try:
        return max(1, min(5, int((persona.get("big5") or {}).get(key, 3))))
    except (TypeError, ValueError):
        return 3


def trait_words(persona: dict) -> str:
    return ", ".join(w for k in "eanoc" if (w := _WORDS[k].get(trait(persona, k))))


# ---------------------------------------------------------------- the start of a visit


def pick_reason(persona: dict, rng: random.Random) -> str:
    reasons = {k: v for k, v in (persona.get("reasons") or {}).items() if k in REASON_TEXT and v}
    if not reasons:
        return "unwind"
    return rng.choices(list(reasons), list(reasons.values()))[0]


def opening_mood(persona: dict, rng: random.Random) -> float:
    """Neurotic people start further from neutral."""
    spread = 0.2 + 0.08 * trait(persona, "n")
    return max(-0.8, min(0.8, rng.gauss(0.05, spread)))


def pick_need(rng: random.Random, stay_min: float, now: datetime, food_truck: bool) -> tuple[str, datetime | None]:
    if stay_min < 40 or rng.random() > 0.4:
        return "", None
    pool = [k for k in NEEDS if k != "food" or food_truck]
    return rng.choice(pool), now + timedelta(minutes=rng.uniform(0.3, 0.8) * stay_min)


def goal_shift(persona: dict, goal: int, rng: random.Random) -> int:
    """Conscientious people stick to their plan; impulsive ones have another."""
    c = trait(persona, "c")
    if c <= 2 and rng.random() < 0.3:
        return goal + 1
    if c >= 4 and rng.random() < 0.2:
        return max(1, goal - 1)
    return goal


def stay_scale(persona: dict) -> float:
    s = 1.0
    if trait(persona, "e") <= 2:
        s *= 0.85  # introverts run out of steam sooner
    c = trait(persona, "c")
    return s * (0.92 if c >= 4 else 1.08 if c <= 2 else 1.0)


# ---------------------------------------------------------------- state over time


def body(persona: dict) -> float:
    return 0.9 + int(persona.get("age", 30)) / 300


def add_drink(buzz: float, persona: dict, strength: float = 1.0) -> float:
    """`strength` is how hard the drink hits against an ordinary beer: see drunk.strength."""
    return min(1.0, buzz + 0.18 * body(persona) * strength)


def tick(p, dt_min: float, decay: float = 1.0) -> None:
    """Passive change while time passes: buzz wears off (faster on water), mood settles, and a free person recovers."""
    p.buzz = max(0.0, p.buzz - BUZZ_DECAY_PER_HOUR * decay * dt_min / 60)
    p.peak_buzz = max(p.peak_buzz, p.buzz)
    p.mood += (0.0 - p.mood) * min(1.0, dt_min / 180)
    if p.thread_id is None:
        p.battery = min(1.0, p.battery + RECOVER_PER_HOUR * dt_min / 60)


def spoke(p) -> None:
    """Talking costs energy, and more for the reserved."""
    e = trait(p.persona, "e")
    p.battery = max(0.0, p.battery - 0.03 * (1.5 if e <= 2 else 1.0 if e == 3 else 0.7))


def nudge_mood(p, amount: float) -> None:
    p.mood = max(-1.0, min(1.0, p.mood + amount * (0.7 + 0.15 * trait(p.persona, "n"))))


def blend_mood(p, tag: str) -> None:
    """Fold the mood the person reported for their last line into the running mood."""
    if tag in MOODS:
        w = 0.25 + 0.05 * trait(p.persona, "n")
        p.mood = max(-1.0, min(1.0, p.mood * (1 - w) + MOODS[tag] * w))


def mood_word(mood: float) -> str:
    return "in a good mood" if mood >= 0.4 else "a bit down" if mood <= -0.45 else "a little irritable" if mood <= -0.25 else ""


# ---------------------------------------------------------------- what it does to behaviour


def drive(p, now: datetime) -> float:
    """How readily this person joins or starts a conversation right now, 1.0 being the ordinary rate."""
    d = 0.4 + 0.2 * trait(p.persona, "e")
    if p.reason == "solo":
        d *= 0.5
    if p.busy_until and now < p.busy_until:
        d *= 0.4
    d *= 0.4 + 0.6 * p.battery
    d *= 1.0 + 0.4 * p.buzz
    d *= 1.0 + 0.3 * p.mood
    return max(0.05, d)


def affinity_weight(aff: int) -> float:
    return max(0.1, min(2.0, 1.0 + aff / 100))


def avoids(aff: int) -> bool:
    return aff <= -30


def speaker_weight(p) -> float:
    return (0.6 + 0.4 * p.battery) * (1.0 + 0.6 * p.buzz)


def pace(p) -> float:
    """Multiplier on the pause between this person's lines: the buzzed talk faster, the drained slower."""
    return (1.0 - 0.25 * p.buzz) * (1.0 + 0.4 * (1.0 - p.battery))


def escalation(persona: dict) -> float:
    """Agreeable people take longer to wind up in an argument."""
    return 1.0 + (3 - trait(persona, "a")) * 0.15


def event_interest(persona: dict) -> float:
    """Open people are readier to talk about the big news."""
    return 1.0 + (trait(persona, "o") - 3) * 0.08


def excuse_due(p, now: datetime, turns: int, rng: random.Random) -> str:
    """Why this person should bow out of the chat they're in (empty if they shouldn't)."""
    if p.need and p.need_at and now >= p.need_at:
        return f"You need to {NEEDS[p.need]}. Say so naturally and excuse yourself."
    if turns >= 3 and not p.wants_leave:
        if p.battery < 0.2 and rng.random() < 0.5:
            return "You're socially spent. Bow out politely (you need a breather) and excuse yourself."
        if p.mood <= -0.6 and rng.random() < 0.2:
            return "You're in a mood and this chat isn't helping. Make an excuse and step away."
    return ""


def away_for(reason: str, rng: random.Random) -> timedelta:
    return timedelta(minutes=rng.uniform(4, 10) if reason.startswith("You need") else rng.uniform(10, 25))


# ---------------------------------------------------------------- how a turn sounds


def length_mode(p, rng: random.Random, loud: bool = False) -> str:
    """react (a few words) | normal | story (a longer turn)."""
    w = {"react": 0.25, "normal": 0.6, "story": 0.15}
    style = p.persona.get("style", "")
    if style == "joker":
        w["react"] += 0.15
    elif style == "listener":
        w["react"] += 0.2
        w["story"] -= 0.1
    elif style == "storyteller":
        w["story"] += 0.25
        w["react"] -= 0.1
    elif style == "debater":
        w["story"] += 0.1
    if p.buzz > 0.4:
        w["story"] += 0.1
    if p.battery < LOW_BATTERY:
        w["react"] += 0.3
        w["story"] = 0.02
    if p.mood <= -0.3:
        w["react"] += 0.15
    if loud:
        w["react"] += 0.1
    w = {k: max(0.02, v) for k, v in w.items()}
    return rng.choices(list(w), list(w.values()))[0]


MODE_HINT = {
    "react": "Keep this one very short: a few words, a reaction or a quip (under about 8 words).",
    "normal": "",
    "story": "You've got something to say: take a little longer, 2-3 sentences (under about 55 words).",
}


def moves(rng: random.Random, buzz: float) -> str:
    """A rare, human slip in this turn."""
    r = rng.random()
    if r < 0.02:
        return "You half-misheard the last thing said; answer what you thought you heard."
    if r < 0.05:
        return "Your attention drifts for a second (your phone, the TV, the room); give a distracted, partial answer."
    if r < 0.08:
        return "The last thing said didn't land with you. Don't laugh to be polite."
    if r < 0.10:
        return "Trail off mid-thought and let it hang."
    if buzz > 0.7 and r < 0.2:
        return "You're a few in: you drift off topic or repeat a story you already told."
    return ""


def right_now(p, now: datetime, room: str = "") -> str:
    """One line of what this guest is feeling and wanting, for the volatile scene."""
    parts = ["your first time at this taproom" if p.first_visit else "", REASON_TEXT.get(p.reason, "")]
    if p.drinks:
        n = f"drink number {p.drinks}"
        parts.append(n + {"tipsy": ", feeling it a little", "drunk": ", properly drunk", "wasted": ", very drunk"}.get(drunk.tier(p.buzz), ""))
    if p.battery < 0.45:
        parts.append("starting to tire of talking" if p.battery >= LOW_BATTERY else "socially drained")
    if m := mood_word(p.mood):
        parts.append(m)
    if p.need and p.need_at and timedelta(0) <= p.need_at - now <= timedelta(minutes=12):
        parts.append(f"you'll need to {NEEDS[p.need]} soon")
    parts = [x for x in parts if x]
    return ("Right now: " + " · ".join(parts) + ".") if parts else ""

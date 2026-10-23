"""Evolving relationships: named bonds that form and change, and what each one does to behaviour.

Pure functions over a RelState and two people, in the style of life.py and human.py. Familiarity and affinity say how
well two people know each other; the bond says what they are to each other (friends, rivals, a crush, a couple, a
falling-out). Moves come from thresholds on those numbers plus an optional `moment` the conversation summary reports
(fight, flirt, apology, ...), so the whole thing costs no extra model call.
"""
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

BONDS = ("stranger", "acquaintance", "friends", "close_friends", "rivals", "crush", "couple", "falling_out", "ex", "mentor")
MOMENTS = ("none", "fight", "flirt", "apology", "confided", "advice", "teasing")
LABEL = {
    "acquaintance": "acquaintances", "friends": "friends", "close_friends": "close friends", "rivals": "rivals",
    "crush": "a crush", "couple": "a couple", "falling_out": "fallen out", "ex": "exes", "mentor": "mentor",
}
ICON = {"friends": "🤝", "close_friends": "💛", "rivals": "⚔️", "crush": "💘", "couple": "❤️", "falling_out": "💔", "ex": "🥀", "mentor": "🎓"}

FALLOUT_DAYS = (5, 14)  # how long a falling-out lasts before it heals or sets hard
CRUSH_DAYS = 21  # a crush that goes nowhere fades after this long
EX_DAYS = 30  # exes are civil again after this long
EX_AVOID_DAYS = 7  # and keep their distance for the first week
MIN_AGE = 21  # romance is for adults
CRUSH_GAP = 15  # most years apart for a crush
MENTOR_GAP = 15  # least years apart for a mentor
CRUSH_CHANCE = 0.25  # per flirt, before the attached scale
ATTACHED_SCALE = 0.2
RECONCILE_CHANCE = 0.15  # per sim day once a falling-out is old enough
ROMANCE_PER_DAY = 1  # most crushes and couples the room forms in a sim day

_ATTACHED = re.compile(r"\b(wife|husband|married|spouse|fianc\w*|girlfriend|boyfriend|my partner|his partner|her partner)\b", re.I)
_UNATTACHED = re.compile(r"\b(widow\w*|divorc\w*|late husband|late wife|husband's death|wife's death|ex-wife|ex-husband)\b", re.I)
_KINDS = (
    (("close friend", "old friend", "best friend"), "close_friends"),
    (("rival", "adversar", "frenem", "wary"), "rivals"),
    (("ex-partner",), "ex"),
    (("mentor",), "mentor"),
)


@dataclass
class Change:
    """A move from one bond to another."""
    new: str
    why: str
    until: datetime | None = None  # when a falling-out stops being fresh
    by: str = ""  # who has the crush, or who is the mentor


# ---------------------------------------------------------------- starting points


def from_seed(kind: str, familiarity: int, affinity: int) -> str:
    """The bond a relationship starts with: its seeded kind if that says so, else its numbers."""
    k = (kind or "").lower()
    if familiarity <= 0:
        return "stranger"
    for words, bond in _KINDS:
        if any(w in k for w in words):
            return bond
    if familiarity >= 75 and affinity >= 55:
        return "close_friends"
    if familiarity >= 45 and affinity >= 30:
        return "friends"
    if familiarity >= 15:
        return "acquaintance"
    return "stranger"


def attached(persona: dict) -> bool:
    """True if the persona's own prose says they have a partner."""
    text = " ".join(str(persona.get(k, "")) for k in ("life", "quirk", "job", "traits", "interests"))
    return bool(_ATTACHED.search(text)) and not _UNATTACHED.search(text)


def _age(p) -> int:
    try:
        return int(p.persona.get("age", 30))
    except (TypeError, ValueError):
        return 30


def _patrons(p, q) -> bool:
    return not p.is_bartender and not q.is_bartender


# ---------------------------------------------------------------- moves


def step(rel, p, q, moment: str, by: str, aff_delta: int, now: datetime, rng: random.Random) -> Change | None:
    """The move, if any, that one finished conversation makes between p and q. `by` is who did the moment."""
    cur = rel.bond or "stranger"
    if cur != "stranger" and rel.bond_since and now - rel.bond_since < timedelta(days=1):
        return None  # one change per pair per sim day
    fam, aff = rel.familiarity, rel.affinity
    moment = moment if moment in MOMENTS else "none"

    if cur in ("friends", "close_friends", "couple") and _patrons(p, q) and ((moment == "fight" and aff_delta <= -4) or aff < 0):
        return Change("falling_out", "a fight" if moment == "fight" else "things went sour",
                      until=now + timedelta(days=rng.uniform(*FALLOUT_DAYS)))
    if cur == "falling_out":
        return Change(rel.prior or "friends", "made up") if moment == "apology" else None

    if not _patrons(p, q):
        return _grow(rel, cur, now)  # staff and regulars get friendlier but never fall out or pair off

    if cur in ("acquaintance", "friends") and fam >= 30 and aff <= -25:
        return Change("rivals", "they rub each other the wrong way")
    if cur == "rivals":
        return Change("acquaintance", "buried the hatchet") if aff >= 15 else None

    if (moment == "flirt" and by in (p.id, q.id) and cur in ("acquaintance", "friends", "close_friends")
            and min(_age(p), _age(q)) >= MIN_AGE and abs(_age(p) - _age(q)) <= CRUSH_GAP and aff >= 0):
        suitor = p if by == p.id else q
        if rng.random() < CRUSH_CHANCE * (ATTACHED_SCALE if attached(suitor.persona) else 1.0):
            return Change("crush", "a spark", by=by)
    if cur == "crush":
        if (moment == "flirt" and by != rel.crush_by) or (fam >= 55 and aff >= 50 and aff_delta > 0 and moment in ("flirt", "confided")):
            return Change("couple", "it turned out to be mutual")
        return None
    if cur == "couple":
        return None

    if moment == "advice" and cur in ("acquaintance", "friends") and fam >= 40 and aff >= 20 and abs(_age(p) - _age(q)) >= MENTOR_GAP:
        return Change("mentor", "gave advice that stuck", by=(p if _age(p) > _age(q) else q).id)
    if moment == "confided" and cur == "acquaintance" and fam >= 35 and aff_delta > 0:
        return Change("friends", "opened up to each other")
    return _grow(rel, cur, now)


def _grow(rel, cur: str, now: datetime) -> Change | None:
    if cur == "acquaintance" and rel.familiarity >= 45 and rel.affinity >= 30:
        return Change("friends", "got to know each other")
    if cur == "friends" and rel.familiarity >= 75 and rel.affinity >= 55 and (rel.met_at is None or now - rel.met_at >= timedelta(days=7)):
        return Change("close_friends", "grown close")
    return None


def decay(rel) -> str:
    """Where a falling-out ends up when nobody makes the first move."""
    if rel.prior == "couple":
        return "ex"
    return "rivals" if rel.affinity < -25 else "acquaintance"


def offscreen(rel, now: datetime, rng: random.Random) -> Change | None:
    """What a sim day does to a bond with nobody watching. `rng` is seeded by (pair, day)."""
    if not rel.bond_since:
        return None
    age = now - rel.bond_since
    if rel.bond == "falling_out":
        if rel.bond_until and now >= rel.bond_until:
            return Change(decay(rel), "it never got patched up")
        if age >= timedelta(days=3) and rng.random() < RECONCILE_CHANCE:
            return Change(rel.prior or "friends", "made up")
    elif rel.bond == "crush" and age >= timedelta(days=CRUSH_DAYS):
        return Change(rel.prior or "acquaintance", "the feeling faded")
    elif rel.bond == "ex" and age >= timedelta(days=EX_DAYS):
        return Change("acquaintance", "moved on")
    return None


def date_night(rel, rng: random.Random) -> bool:
    """Do these two come in together on a day they would otherwise skip?"""
    return rel.bond == "couple" and rng.random() < 0.12


# ---------------------------------------------------------------- what it does to behaviour


def avoids(rel, now: datetime) -> bool:
    if rel.bond == "falling_out":
        return True
    if rel.bond == "ex" and rel.bond_since and now - rel.bond_since < timedelta(days=EX_AVOID_DAYS):
        return True
    if rel.bond == "rivals":
        return False  # rivals seek each other out to needle each other
    return rel.affinity <= -30


JOIN = {"couple": 1.6, "crush": 1.4, "close_friends": 1.3, "rivals": 1.3, "friends": 1.1, "ex": 0.5}


def join_weight(rel) -> float:
    return JOIN.get(rel.bond, 1.0)


FOLLOW = {"couple": 0.7, "close_friends": 0.5, "crush": 0.4, "rivals": 0.15, "ex": 0.05, "falling_out": 0.0}


def follow_chance(rel, reason: str, good_news: bool = False) -> float:
    """The chance that someone who just walked in is followed by this person."""
    base = FOLLOW.get(rel.bond, 0.5 if reason == "catch_up" else 0.3)
    return min(0.95, base * (1.3 if good_news else 1.0))


def sits_close(rel) -> bool:
    return rel.bond in ("couple", "crush")


def scene_hint(rel, me: str, other: str, am_attached: bool, now: datetime, rng: random.Random) -> str:
    """One sentence for the volatile scene about how `me` feels towards `other`. Empty when the bond is nothing special."""
    b = rel.bond
    if b == "crush":
        if rel.crush_by != me:
            return ""  # they don't know
        guilt = " You're with someone, which makes it feel wrong." if am_attached else ""
        return f"You have a quiet crush on {other}: you try a bit too hard, and you haven't said anything.{guilt}"
    if b == "couple":
        return f"You and {other} are together: easy, affectionate, a little private."
    if b == "falling_out":
        when = f" since {rel.bond_since:%A}" if rel.bond_since else ""
        hint = f"You and {other} have fallen out{when} and you're still sore: be short with them unless they make the first move."
        return hint + (" You might try to clear the air." if rng.random() < 0.2 else "")
    if b == "rivals":
        return f"You and {other} are rivals: you needle each other, and it's half fun and half real."
    if b == "ex":
        return f"{other} is your ex: keep it civil."
    if b == "mentor":
        if not rel.mentor_id:
            return f"You and {other} have a mentor-and-protege history: there is respect and a little pride and criticism in it."
        return f"{other} looks up to you." if rel.mentor_id == me else f"You look up to {other} and value their advice."
    if b == "close_friends":
        return f"{other} is one of your closest friends: you can say anything."
    return ""


def label(rel) -> str | None:
    """How a bond reads in a prompt's relationship line; None to fall back on the plain familiarity wording."""
    b = rel.bond
    since = f" on {rel.bond_since:%A}" if rel.bond_since else ""
    if b == "falling_out":
        return f"you had a falling-out{since} and are still sore"
    if b == "couple":
        return "together" + (f" since {rel.bond_since:%b %-d}" if rel.bond_since else "")
    if b == "crush":
        return "you've been getting close"
    if b in ("rivals", "ex", "mentor"):
        return rel.kind if rel.kind not in ("stranger", "acquaintance", "regular") else LABEL[b]
    return None


# ---------------------------------------------------------------- the scorecard


def drama(changes: int, patron_days: int, days: int) -> dict:
    """Are bonds moving at a believable pace? Too few and the room never changes; too many and it is a soap opera."""
    if patron_days < 20:
        return {"rate": None, "band": "none"}
    rate = changes / patron_days
    if changes == 0:
        band = "red" if days >= 7 else "amber"
    elif rate > 0.15:
        band = "red"
    elif rate > 0.1 or rate < 0.005:
        band = "amber"
    else:
        band = "green"
    return {"rate": round(rate, 3), "band": band}

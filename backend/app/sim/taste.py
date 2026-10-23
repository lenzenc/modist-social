"""What people like to drink, how that drifts, and what they can afford to spend.

Pure functions over a TasteRec, in the style of drunk.py and life.py. Everything here is deterministic given an rng;
the model only voices it, through guest_note and bartender_note. Code decides the drink, the recommendation, the
skipped round and the round bought for friends.
"""
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.sim import menu

LIKE_USUAL = 0.8  # affinity a person starts with for their persona's usual drink
LIKE_STYLE = 0.25  # ...and for drinks in the same menu section
LIKE_STEP = {"loved": 0.35, "fine": 0.08, "meh": -0.3}
VERDICT_ODDS = {"loved": 0.25, "fine": 0.5, "meh": 0.25}
DRIFT = 0.04  # how far a daily nudge pulls an affinity toward zero (the top two are exempt)
TIRED_STREAK = 4  # the same drink this many visits running and they start to tire of it
TIRED_DAYS = (5, 12)
HISTORY_KEEP = 20
OWES_CAP = 3
LOG_KEEP = 300

BEER_ADVENTURE = {"newbie": 0.0, "casual": 0.1, "nerd": 0.25}
# Odds a patron stays with what they have, against switching. A newbie sticks to one safe thing; a nerd roams.
STICK = 0.55
NEW_BASE = 0.12
ASK_REC_BASE = 0.08
TAKE_REC_BASE = 0.35

# Money, in cents per visit.
BUDGET_CAP = {"tight": 1600, "ok": 3200, "flush": 6400}
BUDGET_WORDS = {
    "tight": ("rent", "behind on", "bill", "lease", "loan", "saving", "broke", "student", "debt", "mortgage"),
    "flush": ("owns", "closing a big", "big listing", "year"),
}
MONEY_SHRINK = {"lost_the_job": 0.4, "car_trouble": 0.6, "unexpected_bill": 0.65, "landlord_trouble": 0.8}
WINDFALL = 1.8
ROUND_BASE = 0.1
ROUND_BUDGET = {"tight": 0.0, "ok": 0.5, "flush": 1.3}
MIN_FRIENDS = 1
MAX_FRIENDS = 3


@dataclass
class TasteRec:
    like: dict[str, float] = field(default_factory=dict)  # drink -> affinity, -1..1
    streak: list = field(default_factory=lambda: ["", 0])  # [drink, visits in a row it was the first drink]
    tired: dict[str, str] = field(default_factory=dict)  # drink -> ISO day they are tired of it until
    tried: list[str] = field(default_factory=list)
    owes: dict[str, int] = field(default_factory=dict)  # pid -> rounds I owe them (negative: they owe me)
    history: list[str] = field(default_factory=list)  # last drinks, newest last

    def dump(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, raw: dict) -> "TasteRec":
        known = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        return cls(**known)


@dataclass
class Intent:
    """What a guest means to do about a drink this round. `kind` is same | usual | switch | new | rec (ask the bartender)."""
    kind: str
    drink: str = ""
    why: str = ""


def section(drink: str) -> int:
    return menu.section_of(drink)


def usual(persona: dict) -> str:
    return menu.match(str(persona.get("drink", ""))) or ""


def adventurous(persona: dict) -> float:
    """0..1: how much they want to try something they haven't had."""
    o = int((persona.get("big5") or {}).get("o", 3))
    return max(0.0, min(1.0, (o - 1) / 4 * 0.6 + BEER_ADVENTURE.get(persona.get("beer", "casual"), 0.1) + 0.15))


def seed(persona: dict, rng: random.Random) -> TasteRec:
    rec = TasteRec()
    fav = usual(persona)
    if fav:
        rec.like[fav] = LIKE_USUAL
        rec.tried.append(fav)
        for d in menu.names():
            if d != fav and section(d) == section(fav):
                rec.like[d] = LIKE_STYLE * rng.uniform(0.5, 1.0)
    else:
        for d in rng.sample(menu.names(), 3):
            rec.like[d] = rng.uniform(0.3, 0.6)
    return rec


def top(rec: TasteRec, n: int = 3) -> list[str]:
    return [d for d, v in sorted(rec.like.items(), key=lambda kv: -kv[1]) if v > 0][:n]


def tired_of(rec: TasteRec, day: str) -> list[str]:
    return [d for d, until in rec.tired.items() if until > day]


# ---------------------------------------------------------------- choosing a drink


def intend(rec: TasteRec, persona: dict, last: str, rng: random.Random, day: str, *, specials: list[str] | None = None,
           tight: bool = False, serve_water: bool = False) -> Intent:
    """What this guest is going to order: the same again, their usual, a switch, something new, or the bartender's call."""
    tired = set(tired_of(rec, day))
    fav = usual(persona)
    adv = adventurous(persona)
    specials = [s for s in (specials or []) if s not in tired]
    pool = {d: v for d, v in rec.like.items() if d not in tired and v > 0}
    if last and last not in tired and rng.random() < STICK * (1 - adv) + 0.15 * max(rec.like.get(last, 0), 0):
        return Intent("same", last, "you're happy with it")
    if not last and fav and fav not in tired and rng.random() < 0.6 * (1 - adv) + 0.3:
        return Intent("usual", fav, "your usual")
    if tight and specials and rng.random() < 0.6:
        return Intent("switch", rng.choice(specials), "it's on special and money's tight")
    if rng.random() < ASK_REC_BASE + 0.25 * adv:
        return Intent("rec", "", "you're curious what the bartender would pour")
    if rng.random() < NEW_BASE + 0.5 * adv:
        fresh = [d for d in menu.names() if d not in rec.tried and d not in tired]
        if fresh:
            return Intent("new", rng.choice(fresh), "you want to try something you haven't had")
    if pool:
        names = list(pool)
        pick = rng.choices(names, [pool[d] + 0.05 for d in names])[0]
        return Intent("switch" if pick != last else "same", pick, "something you like")
    return Intent("new", rng.choice([d for d in menu.names() if d not in tired] or menu.names()), "you're not sure what you feel like")


def recommend(bartender: dict, rec: TasteRec, rng: random.Random, day: str, specials: list[str] | None = None) -> str:
    """What the bartender suggests: something in a style the guest likes that they haven't tried, else a special or their own pick."""
    tired = set(tired_of(rec, day))
    liked = {section(d) for d in top(rec, 4)}
    fresh = [d for d in menu.names() if d not in rec.tried and d not in tired]
    close = [d for d in fresh if section(d) in liked]
    if close:
        return rng.choice(close)
    own = menu.match(str(bartender.get("drink", "")))
    if own and own not in tired and rng.random() < 0.5:
        return own
    if specials and (cheap := [s for s in specials if s not in tired]):
        return rng.choice(cheap)
    return rng.choice(fresh or [d for d in menu.names() if d not in tired] or menu.names())


def takes_rec(persona: dict, familiarity: int, rng: random.Random) -> bool:
    """Whether the guest goes along with a suggestion: openness, and how far they trust this bartender."""
    return rng.random() < min(0.95, TAKE_REC_BASE + 0.4 * adventurous(persona) + 0.3 * familiarity / 100)


# ---------------------------------------------------------------- how a drink lands


def verdict(rec: TasteRec, persona: dict, drink: str, rng: random.Random) -> str:
    """loved | fine | meh. Drinks in a style they already like land better."""
    w = dict(VERDICT_ODDS)
    liked = {section(d) for d in top(rec, 4)}
    if section(drink) in liked:
        w["loved"] += 0.25
        w["meh"] -= 0.15
    if rec.like.get(drink, 0) > 0.5:
        w["loved"] += 0.2
        w["meh"] -= 0.1
    w["meh"] = max(w["meh"], 0.05)
    return rng.choices(list(w), list(w.values()))[0]


def after_drink(rec: TasteRec, drink: str, v: str) -> None:
    """Take a drink into account: affinity moves, the history grows, and a rut can start to wear."""
    rec.like[drink] = max(-1.0, min(1.0, rec.like.get(drink, 0.0) + LIKE_STEP[v]))
    if drink not in rec.tried:
        rec.tried.append(drink)
    rec.history = (rec.history + [drink])[-HISTORY_KEEP:]


def first_of_visit(rec: TasteRec, drink: str, day: str, rng: random.Random) -> bool:
    """Count visits in a row that opened with the same drink. At TIRED_STREAK they tire of it for a while; returns True then."""
    if rec.streak[0] == drink:
        rec.streak[1] += 1
    else:
        rec.streak = [drink, 1]
    if rec.streak[1] >= TIRED_STREAK:
        y, m, d = map(int, day.split("-"))
        until = datetime(y, m, d).toordinal() + rng.randint(*TIRED_DAYS)
        rec.tired[drink] = datetime.fromordinal(until).strftime("%Y-%m-%d")
        rec.streak = [drink, 0]
        rec.like[drink] = rec.like.get(drink, 0) - 0.2
        return True
    return False


def daily(rec: TasteRec, day: str) -> None:
    """Once a sim day: affinities drift toward zero except the two they love most, and tired-of entries lapse."""
    keep = set(top(rec, 2))
    for d, v in list(rec.like.items()):
        if d in keep:
            continue
        v = v - DRIFT if v > 0 else v + DRIFT
        if abs(v) < DRIFT:
            del rec.like[d]
        else:
            rec.like[d] = round(v, 3)
    rec.tired = {d: until for d, until in rec.tired.items() if until > day}


# ---------------------------------------------------------------- money


def budget(persona: dict) -> str:
    """tight | ok | flush. A persona can say so; otherwise it comes from what their life and job suggest."""
    if (b := persona.get("budget")) in BUDGET_CAP:
        return b
    blob = f"{persona.get('life', '')} {persona.get('job', '')}".lower()
    if any(k in blob for k in BUDGET_WORDS["tight"]):
        return "tight"
    if persona.get("tipper") == "generous" and any(k in blob for k in BUDGET_WORDS["flush"]):
        return "flush"
    return "tight" if persona.get("tipper") == "low" else "ok"


def visit_cap(persona: dict, events: list, now: datetime, weight) -> int:
    """Cents they are willing to spend this visit. Money trouble shrinks it, a windfall grows it, both fading with the event.

    `events` are life events and `weight(e, now)` is how fresh each one still is.
    """
    cap = float(BUDGET_CAP[budget(persona)])
    for e in events:
        w = weight(e, now)
        if w <= 0:
            continue
        if e.kind in MONEY_SHRINK:
            cap *= 1 - (1 - MONEY_SHRINK[e.kind]) * w
        elif e.kind == "windfall":
            cap *= 1 + (WINDFALL - 1) * w
    return int(cap)


def can_afford(spent: int, cap: int, price: int) -> bool:
    return spent + price <= cap


def buys_round(persona: dict, mood: float, buzz: float, owed: int, flush_now: bool, rng: random.Random, friends: int) -> bool:
    """Whether someone at the bar treats their friends. A flush budget, good mood, a drink or two in and being owed all help."""
    if friends < MIN_FRIENDS:
        return False
    odds = ROUND_BASE * (ROUND_BUDGET[budget(persona)] + (1.0 if flush_now else 0.0))
    odds *= 1 + max(mood, 0) + min(buzz, 0.5) + 0.3 * max(owed, 0)
    return rng.random() < min(0.6, odds)


# ---------------------------------------------------------------- what the model hears


def guest_note(i: Intent) -> str:
    """The guest's order-time hint: the drink they have decided on, as the board's exact name."""
    if i.kind == "rec":
        return "You don't know what you feel like: ask the bartender what they'd pour you, and leave drink empty for now."
    if i.kind in ("same", "usual"):
        verb = "get the same again" if i.kind == "same" else "get your usual"
        return f"You've decided to {verb}: {i.drink} ({i.why}). Put its exact board name in drink."
    verb = "switch to" if i.kind == "switch" else "try"
    return f"You've decided to {verb} {i.drink} ({i.why}). Put its exact board name in drink."


def rec_reply(suggest: str, take: bool, fallback: str) -> str:
    """The guest's answer to the bartender's suggestion, decided in code."""
    if take:
        return f"The bartender suggested {suggest}: you like the sound of it. Say so and put {suggest} in drink."
    return f"The bartender suggested {suggest}, but it's not for you today: say no thanks kindly and order {fallback} instead (put it in drink)."


def bartender_note(guest_short: str, suggest: str, regular_drink: str) -> str:
    if suggest:
        return (f"{guest_short} wants a suggestion. Recommend {suggest} by its exact board name, in a line, and say why it suits them.")
    if regular_drink:
        return f"{guest_short} has been drinking {regular_drink} lately; you may mention it."
    return ""


def treat_note(names: list[str]) -> str:
    return f"You're buying a round for {', '.join(names)}: tell the bartender it's on you."


def tired_text(drink: str) -> str:
    return f"You've been on {drink} a lot lately and you're a little tired of it."


# ---------------------------------------------------------------- the scorecard


def habits(log: list[dict], sales: list[tuple[str, str]]) -> dict:
    """Do people order like people? `sales` is (person, drink) for recent sales, oldest first.

    Variety is distinct drinks per person; repeats are consecutive identical orders. Both bands are loose, because
    "always the same" and "never the same" are each wrong.
    """
    by: dict[str, list[str]] = {}
    for pid, drink in sales:
        by.setdefault(pid, []).append(drink)
    multi = {p: ds for p, ds in by.items() if len(ds) >= 4}
    variety = round(sum(len(set(ds)) / len(ds) for ds in multi.values()) / len(multi), 2) if multi else None
    pairs = [(a, b) for ds in multi.values() for a, b in zip(ds, ds[1:])]
    repeat = round(sum(a == b for a, b in pairs) / len(pairs), 2) if pairs else None
    band = "none" if repeat is None else "green" if 0.25 <= repeat <= 0.7 else "amber" if 0.1 <= repeat <= 0.85 else "red"
    count = lambda kind: sum(1 for x in log if x.get("kind") == kind)
    recs = count("rec_taken") + count("rec_declined")
    return {"variety": variety, "repeat": repeat, "band": band, "guests": len(multi),
            "recs": recs, "taken": count("rec_taken"), "loved": count("rec_loved"),
            "tried_new": count("new"), "tired": count("tired"), "skips": count("skip"), "rounds": count("round")}

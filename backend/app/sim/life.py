"""Off-screen life: things that happen to patrons between visits, and what they do to the next one.

Pure functions over the catalog in seed/life_events.yaml, in the style of human.py. Effects fade linearly from full
strength when an event starts to nothing when it ends, so a cold hurts on the first night and barely at all by the last.
"""
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import yaml

from app.seed.loader import HERE
from app.sim.realism import norm

DAILY_CHANCE = 0.12  # per patron per sim day, before the neuroticism scale
MAX_ACTIVE = 2
STRONG = 0.3  # freshness at which an event can still decide why someone came, or how they pay
SHOWN = 2  # most events that go into one scene
FRESH = 0.5  # freshness above which news is still raw enough to come up early
IMPORTANCE = {"work": 6, "family": 7, "health": 7, "money": 6, "good": 7, "interest": 5}


@dataclass
class LifeEventRec:
    kind: str
    text: str
    started_at: datetime
    ends_at: datetime
    cat: str = ""
    keys: list[str] = field(default_factory=list)
    next_kind: str = ""  # the follow-on this event leads to, if it starts an arc
    due_at: datetime | None = None  # when that follow-on happens
    resolved: bool = False  # the follow-on has happened
    id: int | None = None


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict]:
    rows = yaml.safe_load((HERE / "life_events.yaml").read_text())
    return {r["kind"]: r for r in rows}


# ---------------------------------------------------------------- rolling


def active(events: list[LifeEventRec], now: datetime) -> list[LifeEventRec]:
    return [e for e in events if not e.resolved and e.started_at <= now < e.ends_at]


def _fits(entry: dict, persona: dict) -> bool:
    when = entry.get("when") or {}
    age = int(persona.get("age", 30))
    return when.get("age_min", 0) <= age <= when.get("age_max", 200)


def fill(template: str, persona: dict, occurred: date, rng: random.Random) -> str:
    interests = persona.get("interests") or ["something new"]
    return (template.replace("{day}", f"on {occurred:%A}").replace("{since}", f"{occurred:%A}")
            .replace("{job}", str(persona.get("job", "work"))).replace("{interest}", str(rng.choice(interests))))


def make(entry: dict, persona: dict, occurred: date, rng: random.Random) -> LifeEventRec:
    """Turn a catalog entry into an event that began on `occurred`, with its follow-on already decided."""
    started = datetime.combine(occurred, time(6))
    rec = LifeEventRec(
        kind=entry["kind"], text=fill(entry["text"], persona, occurred, rng), cat=entry["cat"],
        started_at=started, ends_at=started + timedelta(days=entry["days"]), keys=list(entry.get("keys", [])),
    )
    if nexts := entry.get("then"):
        pick = rng.choices(nexts, [n["weight"] for n in nexts])[0]
        lo, hi = pick["after"]
        rec.next_kind, rec.due_at = pick["kind"], started + timedelta(days=rng.uniform(lo, hi))
    return rec


def roll_day(pid: str, persona: dict, events: list[LifeEventRec], day: date) -> list[LifeEventRec]:
    """New events for one person on one sim day. Seeded by (person, day), so a day always rolls the same."""
    rng = random.Random(f"{pid}:{day}")
    now = datetime.combine(day, time(9))
    live = active(events, now)
    scale = 0.8 + 0.1 * (int((persona.get("big5") or {}).get("n", 3)) - 1)
    if len(live) >= MAX_ACTIVE or rng.random() >= DAILY_CHANCE * scale:
        return []
    taken = {e.kind for e in live}
    pool = [e for e in catalog().values() if e["weight"] > 0 and e["kind"] not in taken and _fits(e, persona)]
    if not pool:
        return []
    entry = rng.choices(pool, [e["weight"] for e in pool])[0]
    return [make(entry, persona, day - timedelta(days=rng.choice([0, 0, 1])), rng)]


def due_followups(events: list[LifeEventRec], persona: dict, now: datetime, rng: random.Random) -> list[LifeEventRec]:
    """Arcs whose time has come: end the parent, and return the events that follow."""
    out = []
    for e in events:
        if e.resolved or not e.next_kind or e.due_at is None or now < e.due_at:
            continue
        e.resolved, e.ends_at = True, min(e.ends_at, now)
        if entry := catalog().get(e.next_kind):
            out.append(make(entry, persona, now.date(), rng))
    return out


# ---------------------------------------------------------------- effects


def freshness(e: LifeEventRec, now: datetime) -> float:
    """1.0 when the event starts, fading to 0.0 at its end."""
    span = (e.ends_at - e.started_at).total_seconds()
    if e.resolved or span <= 0 or not (e.started_at <= now < e.ends_at):
        return 0.0
    return max(0.0, min(1.0, (e.ends_at - now).total_seconds() / span))


def _weighted(events: list[LifeEventRec], now: datetime):
    for e in events:
        if (w := freshness(e, now)) > 0:
            yield catalog().get(e.kind, {}), w, e


def mood_shift(events: list[LifeEventRec], now: datetime) -> float:
    return max(-0.8, min(0.8, sum(c.get("mood", 0.0) * w for c, w, _ in _weighted(events, now))))


def _mult(events: list[LifeEventRec], now: datetime, key: str, lo: float, hi: float) -> float:
    m = 1.0
    for c, w, _ in _weighted(events, now):
        m *= 1.0 + (c.get(key, 1.0) - 1.0) * w
    return max(lo, min(hi, m))


def visit_mult(events: list[LifeEventRec], now: datetime) -> float:
    return _mult(events, now, "visit", 0.15, 2.0)


def stay_mult(events: list[LifeEventRec], now: datetime) -> float:
    return _mult(events, now, "stay", 0.5, 1.6)


def drink_delta(events: list[LifeEventRec], now: datetime) -> int:
    return round(sum(c.get("drinks", 0) * w for c, w, _ in _weighted(events, now)))


def reason_override(events: list[LifeEventRec], now: datetime) -> str:
    strong = sorted(((w, c["reason"]) for c, w, _ in _weighted(events, now) if c.get("reason") and w >= STRONG), reverse=True)
    return strong[0][1] if strong else ""


def pay_override(events: list[LifeEventRec], now: datetime) -> str:
    return next((c["pay"] for c, w, _ in _weighted(events, now) if c.get("pay") and w >= STRONG), "")


# ---------------------------------------------------------------- in the scene and the scorecard


def freshest(events: list[LifeEventRec], now: datetime, n: int = SHOWN) -> list[LifeEventRec]:
    return [e for _, e in sorted(((freshness(e, now), e) for e in events if freshness(e, now) > 0), key=lambda x: -x[0])[:n]]


def on_mind(events: list[LifeEventRec], now: datetime) -> str:
    """One line for the volatile scene: what has been happening to this person away from here."""
    shown = freshest(events, now)
    raw = [e for e in shown if freshness(e, now) >= FRESH]
    older = [e for e in shown if e not in raw]
    parts = []
    if raw:
        parts.append("On your mind, and fresh: " + "; ".join(e.text for e in raw)
                     + ". It is weighing on you, so it is natural to mention it in your first line or two if you haven't"
                       " already, unless the talk has moved somewhere else.")
    if older:
        parts.append("On your mind lately: " + "; ".join(e.text for e in older)
                     + ". Bring it up only if it fits, the way you would with a friend; don't open with it every time.")
    return " ".join(parts)


_PRONOUNS = frozenset("he she his her hers him himself herself".split())


def usable(text: str, person) -> bool:
    """A polished event reads as a subjectless clause: one line, no pronouns, and not about the person by name."""
    if not text or "\n" in text or len(text) > 160:
        return False
    words = set(norm(text).split())
    return not (words & _PRONOUNS) and not any(n.lower() in words for n in {person.short, *person.display.split()})


def memory_text(e: LifeEventRec) -> str:
    return f"Something that happened to you: {e.text}."


def mentioned(text: str, events: list[LifeEventRec]) -> bool:
    """True if a line of talk touches any of these events, judged by the event's own keywords."""
    padded = f" {norm(text)} "
    return any(f" {norm(k)} " in padded for e in events for k in e.keys)


def continuity(lines: list[tuple[date, str, str]], events: dict[str, list[LifeEventRec]], names: dict[str, str] | None = None) -> dict:
    """Do people actually bring their off-screen lives into the room?

    `lines` are (day, speaker, text). A visit is a person-day with an event on their mind and at least 3 lines; the
    rate is the share of visits where the event came up. Around a third to four fifths is natural: lower and the
    events are invisible, higher and everyone is monologuing about their week.
    """
    names = names or {}
    by_day: dict[tuple[date, str], list[str]] = {}
    for day, sid, text in lines:
        by_day.setdefault((day, sid), []).append(text)

    def on(e: LifeEventRec, day: date) -> bool:
        return e.started_at.date() <= day <= (e.ends_at - timedelta(seconds=1)).date()

    visits = hits = 0
    for (day, sid), texts in by_day.items():
        mine = [e for e in events.get(sid, []) if on(e, day)]
        if mine and len(texts) >= 3:
            visits += 1
            hits += any(mentioned(t, mine) for t in texts)
    listed = []
    for sid, evs in events.items():
        for e in evs:
            said = [t for (day, s), ts in by_day.items() if s == sid and on(e, day) for t in ts]
            listed.append({"person": names.get(sid, sid), "text": e.text, "started": e.started_at.date().isoformat(),
                           "seen": bool(said), "came_up": mentioned(" ".join(said), [e])})
    listed.sort(key=lambda x: x["started"], reverse=True)
    rate = None if visits < 5 else round(100 * hits / visits)
    band = "none" if rate is None else "green" if 30 <= rate <= 80 else "amber" if 15 <= rate <= 90 else "red"
    return {"rate": rate, "band": band, "visits": visits, "mentioned": hits, "events": listed[:20]}

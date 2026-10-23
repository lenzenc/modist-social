"""Group dynamics inside conversations: who is on the outside, who holds the floor and talks over others, jokes that land
unevenly, a mood that spreads round the table, deliberate changes of subject, and pairs that split off.

Pure functions over a PersonState, a RelState and a ThreadState's lines, in the style of beats.py and drunk.py. Everything
is deterministic given an rng; the model only voices what the code decides, through hints in the scene.
"""
import random
from collections import Counter, defaultdict

from app.sim import human, realism

LOG_KEEP = 600
OUTSIDER_GAP = 40  # how far below the rest's bond with each other someone's ties to the table must sit
OUTSIDER_EXCUSE = 0.08  # per turn, once the chat is a few lines in
INTERRUPT_GAP = 0.25  # how much more dominant than the speaker someone must be to talk over them
INTERRUPT_CHANCE = 0.08  # per turn, before the dominance gap scales it
JOKE_BASE = 0.04
STEER_CHANCE = {"avoid": 0.5, "touchy": 0.5, "gossip": 0.4, "stale": 0.12}
STEER_STALE_TURNS = 6
SPLINTER_CHANCE = 0.04  # per turn
SPLINTER_MIN_TURNS = 4
SPLINTER_MIN_GUESTS = 4
SPLINTER_TIE = 70  # the pair's bond must be at least this strong
HOG_SHARE = 0.5  # one person's share of the last lines before the table notices
HOG_LINES = 8
HOG_MIN = 6
FLOOR = {"green": (35, 60), "amber": (28, 70)}  # the top speaker's share of a chat, in percent
FLOOR_MIN_LINES = 6
FLOOR_MIN_CHATS = 5

CLOSE = {"couple": 40, "crush": 25, "close_friends": 30, "friends": 15, "mentor": 15}  # bond -> extra pull

OUTSIDER_HINT = ("The others know each other better than you do and you're a bit on the outside. Keep it short, "
                 "find a way in, or let yourself drift.")
OUTSIDER_EXCUSE_TEXT = "You feel like the odd one out at this table. Make a polite excuse and step away."
INTERRUPTED_HINT = "{name} talks over you before you finish: cut your line off mid-thought and end it with a dash (—)."
INTERRUPTING_HINT = "You can't hold it in. Cut in on {name} and talk over them."
JOKE_HINT = "Make a joke or tease someone here; it's fine if not everyone gets it."
HOG_HINT = "{name} has been doing most of the talking. Get a word in, or let them run."
SPLIT_HINT = "You two just broke off from the bigger table conversation to talk on your own."
LANDED_HINT = "{name}'s joke landed with you; react."
FLAT_HINT = "{name}'s joke didn't land with you. Don't laugh to be polite."
STUNG_HINT = "{name}'s joke stung a little. You may let it show."
STEER_HINT = "Change the subject on purpose to {topic}; make it obvious you're moving on."
VIBE_HINT = "The mood at the table is {word}."


# ---------------------------------------------------------------- who is close to whom


def tie(rel) -> float:
    """How tightly two people are bound: how well they know each other, whether they like each other, and what they are."""
    return rel.familiarity + max(-20, rel.affinity) + CLOSE.get(rel.bond, 0)


def outsider(ids: list[str], rel) -> str | None:
    """The one whose ties to the table sit well below everyone else's bond with each other. `rel(a, b)` gives a RelState."""
    if len(ids) < 3:
        return None
    mean = {i: sum(tie(rel(i, j)) for j in ids if j != i) / (len(ids) - 1) for i in ids}
    low = min(ids, key=lambda i: (mean[i], i))
    rest = [i for i in ids if i != low]
    pairs = [tie(rel(a, b)) for k, a in enumerate(rest) for b in rest[k + 1:]]
    return low if sum(pairs) / len(pairs) - mean[low] >= OUTSIDER_GAP else None


def outsider_leaves(rng: random.Random, turns: int) -> bool:
    return turns >= 4 and rng.random() < OUTSIDER_EXCUSE


# ---------------------------------------------------------------- the floor


def dominance(p) -> float:
    """How readily this person takes and keeps the floor. 1.0 is ordinary."""
    d = 1.0 + 0.15 * (human.trait(p.persona, "e") - 3) - 0.1 * (human.trait(p.persona, "a") - 3)
    d += {"storyteller": 0.2, "debater": 0.3, "joker": 0.1, "listener": -0.3}.get(p.persona.get("style", ""), 0.0)
    d += 0.3 * p.buzz
    return max(0.4, min(2.2, d))


def floor_keep(p) -> float:
    """The weight left to someone who just spoke: the dominant keep talking more often than the rest."""
    return min(0.6, 0.12 + 0.4 * max(0.0, dominance(p) - 1.0))


def hogging(speakers: list[str]) -> str:
    """Whoever has had most of the last lines in a chat, or empty. `speakers` are the speech lines' speaker ids in order."""
    recent = speakers[-HOG_LINES:]
    if len(recent) < HOG_MIN:
        return ""
    who, n = Counter(recent).most_common(1)[0]
    return who if n / len(recent) > HOG_SHARE else ""


def interrupter(rng: random.Random, victim, others: list):
    """Someone who talks over the speaker: a clearly more dominant member, now and then."""
    dv = dominance(victim)
    gaps = [(o, dominance(o) - dv) for o in others]
    gaps = [(o, g) for o, g in gaps if g >= INTERRUPT_GAP]
    if not gaps:
        return None
    o, gap = max(gaps, key=lambda x: (x[1], x[0].id))
    return o if rng.random() < INTERRUPT_CHANCE * (1 + 2 * gap) else None


def trail_off(text: str) -> str:
    """A line cut off mid-thought."""
    return text.rstrip(" .!?,;:—-") + "—"


# ---------------------------------------------------------------- jokes


def joke_due(rng: random.Random, p) -> bool:
    chance = JOKE_BASE + (0.08 if p.persona.get("style") == "joker" else 0.0) + 0.05 * p.buzz + 0.01 * (human.trait(p.persona, "e") - 3)
    return rng.random() < max(0.0, chance)


def reception(rng: random.Random, teller, listener, rel) -> str:
    """How a joke goes down with one listener: landed | flat | stung."""
    lean = rel.affinity / 100 + 0.1 * (human.trait(listener.persona, "a") - 3) + 0.5 * listener.mood + 0.3 * listener.buzz
    if rng.random() < max(0.1, min(0.9, 0.5 + 0.5 * lean)):
        return "landed"
    sour = rel.affinity < 0 or listener.mood < -0.3
    return "stung" if sour and rng.random() < 0.4 else "flat"


def verdict(results: dict[str, str]) -> str:
    """How a joke went with the table as a whole: landed | mixed | flat."""
    got = list(results.values())
    return "landed" if all(r == "landed" for r in got) else "flat" if not any(r == "landed" for r in got) else "mixed"


def _list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def reaction(teller: str, results: dict[str, str], names: dict[str, str]) -> str:
    """One action line for how a joke went round the table."""
    by: dict[str, list[str]] = defaultdict(list)
    for pid, r in results.items():
        by[r].append(names.get(pid, pid))
    parts = []
    if by["landed"]:
        parts.append(f"{_list(by['landed'])} {'cracks' if len(by['landed']) == 1 else 'crack'} up")
    if by["flat"]:
        parts.append(f"{_list(by['flat'])} {'just sips' if len(by['flat']) == 1 else 'just sip'} {'their' if len(by['flat']) > 1 else 'a'} drink")
    if by["stung"]:
        parts.append(f"{_list(by['stung'])} {'forces' if len(by['stung']) == 1 else 'force'} a thin smile")
    return f"{teller} lands a joke. " + "; ".join(parts) + "."


def joke_mood(res: str) -> float:
    return {"landed": 0.05, "flat": 0.0, "stung": -0.1}[res]


def teller_mood(v: str) -> float:
    return {"landed": 0.08, "mixed": 0.0, "flat": -0.06}[v]


# ---------------------------------------------------------------- the table's mood


def vibe(guests: list) -> float:
    """The table's mood: everyone's, weighted toward the talkers."""
    if not guests:
        return 0.0
    w = [0.5 + g.talk for g in guests]
    return sum(g.mood * x for g, x in zip(guests, w)) / sum(w)


def catch(p, table: float) -> None:
    """Moods are catching: drift a little toward the table's, the agreeable more than the blunt."""
    human.nudge_mood(p, (table - p.mood) * (0.05 + 0.02 * human.trait(p.persona, "a")))


def vibe_word(table: float, tension: float = 0.0) -> str:
    return "tense" if tension >= 1 else "lively" if table >= 0.25 else "flat" if table <= -0.2 else "easy"


# ---------------------------------------------------------------- changing the subject


def _keys(phrase: str) -> set[str]:
    return {w for w in realism.norm(phrase).split() if len(w) >= 5 and w not in realism.STOP}


def touches(avoid: list[str], text: str) -> bool:
    words = set(realism.norm(text).split())
    return any(_keys(a) & words for a in avoid)


def steer_due(rng: random.Random, p, recent: list[str], touchy: list[str], gossiped: bool, since: int) -> tuple[str, str] | None:
    """(why, a topic from their own interests) when this person means to change the subject, else None."""
    interests = [i for i in (p.persona.get("interests") or []) if isinstance(i, str) and i]
    if not interests or not recent:
        return None
    text = " ".join(recent)
    low = text.lower()
    why = ""
    if touches(p.persona.get("avoid") or [], text):
        why = "avoid"
    elif any(n.lower() in low for n in touchy):
        why = "touchy"
    elif gossiped:
        why = "gossip"
    elif since >= STEER_STALE_TURNS and (p.persona.get("style") in ("asker", "debater") or human.trait(p.persona, "o") >= 4):
        why = "stale"
    if not why or rng.random() >= STEER_CHANCE[why]:
        return None
    fresh = [i for i in interests if not (_keys(i) & set(realism.norm(text).split()))]
    return why, rng.choice(fresh or interests)


# ---------------------------------------------------------------- splitting off


def splinter(rng: random.Random, guests: list, rel) -> tuple[str, str] | None:
    """A pair at a big table who break off on their own: the closest two, if they share something the rest don't."""
    if len(guests) < SPLINTER_MIN_GUESTS or rng.random() >= SPLINTER_CHANCE:
        return None
    best, top = None, SPLINTER_TIE - 1
    for i, a in enumerate(guests):
        for b in guests[i + 1:]:
            r = rel(a.id, b.id)
            t = tie(r)
            if t > top and (r.bond in CLOSE and r.bond != "friends" or _shared(a, b, guests)):
                best, top = (a.id, b.id), t
    return best


def _shared(a, b, guests: list) -> bool:
    mine = {i.lower() for i in (a.persona.get("interests") or [])} & {i.lower() for i in (b.persona.get("interests") or [])}
    rest = {i.lower() for g in guests if g is not a and g is not b for i in (g.persona.get("interests") or [])}
    return bool(mine - rest)


# ---------------------------------------------------------------- the scorecard


def floor(lines: list[tuple[int | None, str, str]], threads: dict[int, dict]) -> dict:
    """How evenly a chat's lines are spread: the top speaker's average share in chats of three or more. A monologue and a
    perfectly even rota are both off."""
    by: dict[int, list[str]] = defaultdict(list)
    for tid, sid, _ in lines:
        if tid is not None and threads.get(tid, {}).get("kind") == "chat":
            by[tid].append(sid)
    shares = [100 * Counter(s).most_common(1)[0][1] / len(s) for s in by.values()
              if len(s) >= FLOOR_MIN_LINES and len(set(s)) >= 3]
    if len(shares) < FLOOR_MIN_CHATS:
        return {"share": None, "band": "none", "chats": len(shares)}
    share = round(sum(shares) / len(shares))
    lo, hi = FLOOR["green"]
    alo, ahi = FLOOR["amber"]
    return {"share": share, "chats": len(shares), "band": "green" if lo <= share <= hi else "amber" if alo <= share <= ahi else "red"}


def report(log: list[dict], lines: list[tuple[int | None, str, str]], threads: dict[int, dict], patron_days: int) -> dict:
    kinds = Counter(e["kind"] for e in log)
    jokes = Counter(e.get("result") for e in log if e["kind"] == "joke")
    per = (lambda n: round(n / patron_days, 2)) if patron_days else (lambda n: None)
    return {
        "splits": kinds["split"], "interrupts": kinds["interrupt"], "steers": kinds["steer"], "outsiders": kinds["outsider"],
        "jokes": {"landed": jokes["landed"], "mixed": jokes["mixed"], "flat": jokes["flat"]},
        "per_patron_day": {k: per(kinds[k]) for k in ("split", "interrupt", "steer", "outsider", "joke")},
        "floor": floor(lines, threads),
    }

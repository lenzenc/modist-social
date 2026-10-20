"""God Mode: a free-form world event that colours the room's conversations.

An event is scored on two axes, each 1-5: reach (how many people care) and divisiveness (how much they split into
sides). Heat, derived from both and fading over sim time, drives tone, how far the event spills into other chats,
how long chats about it last, and whether opposing sides escalate.
"""
import hashlib
import random
import re
from datetime import datetime

from app.sim.human import trait

MAX_TEXT = 280
LEVELS = (1, 2, 3, 4, 5)
CHANCE = {1: 0.15, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.9}  # reach -> chance a new chat is about the event
HALF_LIFE = {1: 2, 2: 4, 3: 8, 4: 24, 5: 72}  # reach -> sim hours for the buzz to halve
GONE = 0.08  # below this on-topic chance the buzz has died down

STANCE_KEYS = ("feels", "pushback", "mixed", "shrug")
# Weights by divisiveness: what share of the room is with the mood, against it, torn, or indifferent.
_WEIGHTS = {
    1: (62, 4, 14, 20),
    2: (52, 12, 16, 20),
    3: (40, 22, 18, 20),
    4: (36, 34, 15, 15),
    5: (40, 42, 10, 8),
}
_CONTRARIAN = ("devil's advocate", "contrarian", "cynical", "skeptic", "libertarian")
_STOP = {
    "that", "this", "with", "from", "have", "were", "local", "today", "their", "about", "after", "news", "just",
    "been", "into", "will", "over", "than", "them", "what", "when", "also", "some", "more",
}

# First match wins: (pattern, reach, divisiveness).
_RULES = [
    (r"\b(war|invasion|invade[sd]?|airstrikes?|nukes?|nuclear)\b", 5, 5),
    (r"\b(trans|transgender|abortion|gun control|immigration|deportations?|impeach\w*|riots?|supreme court)\b", 4, 5),
    (r"\b(election|elected|shooting|police|ballot|referendum|protest\w*)\b", 4, 4),
    (r"\b(crash\w*|recession|depression|collapse[sd]?|layoffs?|bank run|inflation)\b", 5, 2),
    (r"\b(championship|champions?|title|finals?|super bowl|world series|stanley cup|playoffs?)\b", 5, 2),
    (r"\b(said|says|tweeted|remarks?|comments?|gaffe|quoted)\b", 1, 2),
    (r"\b(tax\w*|mayor|council|senator|governor|bill|law|strike)\b", 3, 3),
    (r"\b(game|match|scored?|won|win|beat|lost|season|trade[sd]?)\b", 1, 1),
]


def clean(text: str) -> str:
    return " ".join(text.split())[:MAX_TEXT]


def clamp(n, lo: int = 1, hi: int = 5) -> int:
    try:
        return max(lo, min(hi, int(round(float(n)))))
    except (TypeError, ValueError):
        return 3


# ---------------------------------------------------------------- classification


def _cares(words: set[str], persona: dict) -> bool:
    blob = " ".join([str(persona.get("job", "")), " ".join(persona.get("interests", [])),
                     " ".join(persona.get("traits", []))]).lower()
    return any(w in blob for w in words)


def heuristic_stances(text: str, reach: int, div: int, people) -> dict[str, str]:
    """A stable stance per person, shaped by divisiveness; low-reach events only matter to those with a stake."""
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}
    out = {}
    for p in people:
        w = dict(zip(STANCE_KEYS, _WEIGHTS[div]))
        if any(c in str(p["persona"].get("politics", "")).lower() for c in _CONTRARIAN):
            w["pushback"] += 30
        w["pushback"] = max(0, w["pushback"] + 10 * (3 - trait(p["persona"], "a")))  # blunt people push back more
        if reach <= 2:
            w["shrug"] = 2 if _cares(words, p["persona"]) else w["shrug"] + (300 if reach == 1 else 100)
        seed = int(hashlib.sha256(f"{text}|{p['id']}".encode()).hexdigest()[:12], 16)
        out[p["id"]] = random.Random(seed).choices(list(w), weights=list(w.values()))[0]
    return out


def heuristic(text: str, people) -> dict:
    """A free estimate from keywords, for mock mode or when the model call fails."""
    reach, div = 2, 2
    for pattern, r, d in _RULES:
        if re.search(pattern, text.lower()):
            reach, div = r, d
            break
    sides = ["on one side of it", "on the other side"] if div >= 3 else ["with the crowd on it", "going against the crowd"]
    return {
        "reach": reach, "divisiveness": div, "sides": sides, "source": "heuristic",
        "reason": f"Keyword estimate (no model call): reach {reach}, divisiveness {div}.",
        "stances": heuristic_stances(text, reach, div, people),
    }


def roster(people) -> str:
    return "\n".join(
        f"{p['id']} | {p['short']} | {p['persona'].get('job', '')} | politics: {p['persona'].get('politics', '')} | "
        f"interests: {', '.join(p['persona'].get('interests', []))} | traits: {', '.join(p['persona'].get('traits', []))}"
        for p in people
    )


async def assess(llm, text: str, people) -> dict:
    """Score the event. One model call; falls back to the keyword estimate if there is none or it fails."""
    people = list(people)
    classify = getattr(llm, "classify", None)
    data = await classify(text, roster(people)) if classify else None
    sides = data.get("sides") if data else None
    if not data or not isinstance(sides, list) or len(sides) < 2:
        return heuristic(text, people)
    known = {p["id"] for p in people}
    stances = {}
    for row in data.get("people", []):
        if row.get("id") in known and row.get("stance") in STANCE_KEYS:
            stances[row["id"]] = row["stance"]
    # Anyone the model skipped gets the hash fallback at read time (stance()).
    return {
        "reach": clamp(data.get("reach")), "divisiveness": clamp(data.get("divisiveness")),
        "sides": [str(sides[0])[:80], str(sides[1])[:80]], "source": "llm",
        "reason": str(data.get("reason", ""))[:200], "stances": stances,
    }


def build(text: str, a: dict, now: datetime, reach: int | None = None, div: int | None = None, people=()) -> dict:
    """The stored God Mode state: an assessment, with the user's sliders applied on top."""
    r = clamp(reach if reach is not None else a["reach"])
    d = clamp(div if div is not None else a["divisiveness"])
    stances = a.get("stances", {})
    if a.get("source") == "heuristic" and (r, d) != (a["reach"], a["divisiveness"]):
        stances = heuristic_stances(text, r, d, list(people))
    return {
        "text": text, "reach": r, "divisiveness": d, "sides": a["sides"], "reason": a.get("reason", ""),
        "stances": stances, "half_life_h": HALF_LIFE[r], "set_at": now.isoformat(),
    }


def normalize(raw: dict | None, now: datetime) -> dict | None:
    """Load saved state, including the older {"text", "buzz"} shape."""
    if not raw:
        return None
    if "reach" in raw:
        return raw
    buzz = raw.get("buzz", 0.65)
    reach = 2 if buzz < 0.5 else 4 if buzz < 0.8 else 5
    return {
        "text": raw["text"], "reach": reach, "divisiveness": 2, "sides": ["with the crowd on it", "going against the crowd"],
        "reason": "", "stances": {}, "half_life_h": HALF_LIFE[reach], "set_at": now.isoformat(),
    }


def public(a: dict) -> dict:
    return {k: a[k] for k in ("reach", "divisiveness", "sides", "reason")}


# ---------------------------------------------------------------- how impact plays out


def fade(god: dict, now: datetime | None) -> float:
    """1.0 when set, halving every half-life of sim time."""
    if now is None:
        return 1.0
    hours = max(0.0, (now - datetime.fromisoformat(god["set_at"])).total_seconds() / 3600)
    return 0.5 ** (hours / god.get("half_life_h", HALF_LIFE[god["reach"]]))


def chance(god: dict, now: datetime | None = None) -> float:
    """The chance a new chat is about the event."""
    return CHANCE[god["reach"]] * fade(god, now)


def heat(god: dict, now: datetime | None = None) -> float:
    return (god["reach"] + 2 * god["divisiveness"]) / 15 * fade(god, now)


def bleed(god: dict, now: datetime | None = None) -> float:
    """The chance a flagging off-topic chat gets pulled onto the event."""
    return max(0.0, heat(god, now) - 0.3) * 0.9


def stretch(god: dict, now: datetime | None = None) -> int:
    """Extra turns a chat about the event lasts."""
    h = heat(god, now)
    return round(8 * h * h)


def alive(god: dict, now: datetime | None = None) -> bool:
    return chance(god, now) >= GONE


def stance(god: dict, person_id: str, persona: dict) -> str:
    """A stable stance for this person on this event: same event, same person, same answer."""
    known = god.get("stances", {}).get(person_id)
    if known in STANCE_KEYS:
        return known
    return heuristic_stances(god["text"], god["reach"], god["divisiveness"], [{"id": person_id, "persona": persona}])[person_id]


def stance_text(key: str, sides: list[str]) -> str:
    return {
        "feels": f"You're with most people on this ({sides[0]}), and it shows. React in your own voice.",
        "pushback": f"You see it differently from most people ({sides[1]}). Say so (politely or not, in character) when it comes up.",
        "mixed": "You have mixed feelings about it. You can see both sides and tend to argue the nuance.",
        "shrug": "You really don't care much about this. If it comes up, shrug it off and steer the talk to something else.",
    }[key]


def tone(god: dict, now: datetime | None = None) -> str:
    h, d = heat(god, now), god["divisiveness"]
    if h < 0.3:
        return "It is light chatter: mention it and move on, nothing heavy."
    if d <= 2:
        if h < 0.5:
            return "It is a fair topic of conversation, shared by most people."
        return ("Everyone is buzzing about it and the mood is shared and loud; "
                "the few who feel differently get friendly ribbing.")
    if h < 0.5:
        return "People have real opinions about this and will say so."
    if h < 0.8:
        return "Feelings run high: people press their point instead of dropping it."
    return ("It is all anyone cares about tonight, and people argue hard, interrupt and dig in. "
            "Stay in character, but keep it to arguing the issue: nothing that attacks anyone for who they are.")


def scene(god: dict, person_id: str, persona: dict, on_topic: bool, is_bartender: bool = False,
          now: datetime | None = None) -> str:
    """The volatile prompt section for a turn while God Mode is on."""
    key = stance(god, person_id, persona)
    out = f"\nBig news today (true in this world): {god['text']}\nHow you feel about it: {stance_text(key, god['sides'])}"
    if on_topic:
        out += f"\n{tone(god, now)}"
    else:
        out += "\nOnly bring it up if someone else does; this conversation is mostly about other things."
    if is_bartender and heat(god, now) >= 0.5:
        out += "\nYou're working: stay neutral about it and keep the peace; don't take a side."
    return out


def steer(event: str) -> str:
    return f"the big news: {event} (react to it as you would, and let others react differently)"


def opposed(a: str, b: str) -> bool:
    return {a, b} == {"feels", "pushback"}

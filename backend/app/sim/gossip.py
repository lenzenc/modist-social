"""Gossip with a paper trail: who told whom, how sure they were, how much it changed on the way, and who found out.

Pure functions over MemoryRec, in the style of bonds.py and drunk.py. Everything here is deterministic given an rng;
the model only voices it, through the labels in label() and the `heard_from` / `sure` it reports back in the summary.
Accuracy (how true a rumor is) is hidden: it is never put in a prompt, only used to decide what happens when a
rumor reaches the person it is about.
"""
import random
import re
from dataclasses import dataclass

from app.sim import drunk

SURE = {"certain": 90, "fairly": 65, "doubtful": 35}  # how sure the listener says they are
CRED_START = 60  # a person's credibility as a source, 0..100
TRUE_AT, GARBLED_AT = 70, 40  # accuracy at which a rumor counts as true / garbled (below GARBLED_AT: false)
CORRECT_GAP = 30  # a listener who holds a copy this much more accurate pushes back on a retelling
WRONG_BASE = 0.15  # chance a brand-new claim is mostly wrong; each drunk tier adds to it
LOG_KEEP = 300
_WORD = re.compile(r"[a-z]{3,}")


def words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def overlap(a: str, b: str) -> float:
    """How much two sentences share, 0..1 (Jaccard on words)."""
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


def tier_n(buzz: float) -> int:
    return ("sober", "tipsy", "drunk", "wasted").index(drunk.tier(buzz))


def clamp(n: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, round(n)))


# ---------------------------------------------------------------- reading a rumor

def is_rumor(rec) -> bool:
    """A memory about someone else that came from somebody (or that somebody else has since passed on)."""
    return rec.kind == "event" and bool(rec.about) and (bool(rec.source_id) or rec.origin_id is not None)


def sureness(confidence: int) -> str:
    return "pretty sure" if confidence >= 80 else "fairly sure" if confidence >= 50 else "not sure"


def label(rec, names: dict[str, str], present: set[str]) -> str:
    """The provenance phrase shown beside a remembered rumor, e.g. "heard from Dana, not sure"."""
    bits = []
    if rec.source_id and rec.source_id in names:
        bits.append(f"heard from {names[rec.source_id]}")
    if rec.source_id or rec.origin_id is not None:
        bits.append(sureness(rec.confidence))
    here = [names[i] for i in rec.about if i in present and i in names]
    if here:
        bits.append(f"{' and '.join(here)} is right here")
    return ", ".join(bits)


def hazy(rec) -> bool:
    return is_rumor(rec) and rec.confidence < 50


HAZY_HINT = "Some of what you've heard about other people is secondhand and you're hazy on the details: hedge, or fill gaps loosely."


# ---------------------------------------------------------------- passing it on

def find_parent(teller_mems: list, told_ids: list[int], subject_ids: set[str], text: str):
    """The teller's memory a retold rumor most likely came from, or None when the teller is making a fresh claim.

    It has to share a subject. Memories the teller actually had in mind this thread win, then the closest wording.
    """
    best, best_score = None, 0.0
    for m in teller_mems:
        if m.kind != "event" or m.id is None or not (set(m.about) & subject_ids):
            continue
        score = (2.0 if m.id in told_ids else 0.0) + overlap(text, m.text)
        if score > best_score:
            best, best_score = m, score
    return best


def retell(parent, text: str, sure: str, teller_buzz: float, cred: int, rng: random.Random) -> dict:
    """The provenance fields for a listener's copy of a rumor: it loses accuracy with every retelling."""
    drift = (1 - overlap(text, parent.text)) * 20 + rng.uniform(0, 6) + 5 * tier_n(teller_buzz) + 2 * parent.hops
    conf = SURE.get(sure, SURE["fairly"]) * (0.5 + cred / 200) * (0.6 + 0.4 * parent.confidence / 100)
    return {"hops": parent.hops + 1, "origin_id": parent.origin_id or parent.id,
            "confidence": clamp(conf, 5), "accuracy": clamp(parent.accuracy - drift)}


def fresh_claim(teller_buzz: float, cred: int, rng: random.Random) -> int:
    """Accuracy of a rumor nobody traces further back than the teller. Drunk and unreliable tellers get more wrong."""
    wrong = WRONG_BASE + 0.07 * tier_n(teller_buzz) + max(0, CRED_START - cred) / 200
    if rng.random() < wrong:
        return rng.randint(10, 40)
    return rng.randint(80, 100)


def verdict(accuracy: int) -> str:
    return "true" if accuracy >= TRUE_AT else "garbled" if accuracy >= GARBLED_AT else "false"


def correction(listener_mems: list, origin_id: int | None, incoming_accuracy: int):
    """The listener's own, better copy of this rumor, if they hold one the teller has now contradicted."""
    if origin_id is None:
        return None
    for m in listener_mems:
        if m.origin_id == origin_id and m.confidence >= 60 and m.accuracy - incoming_accuracy >= CORRECT_GAP:
            return m
    return None


# ---------------------------------------------------------------- credibility

def get_cred(creds: dict, pid: str) -> int:
    return int(creds.get(pid, CRED_START))


def bump_cred(creds: dict, pid: str, delta: int) -> None:
    creds[pid] = clamp(get_cred(creds, pid) + delta)


# ---------------------------------------------------------------- the subject finds out

@dataclass
class Plan:
    """What happens when a rumor reaches the person it is about."""
    kind: str  # true | garbled | false
    aff: int  # subject's affinity change toward the teller
    origin_aff: int  # smaller change toward whoever started it, when that is someone else
    cred: int  # the teller's credibility change
    teller_mood: float
    subject_mood: float
    fight: bool  # run it through the bond rules as a fight, started by the subject


def confrontation(kind: str, rng: random.Random) -> Plan:
    if kind == "false":
        return Plan(kind, -rng.randint(5, 8), -rng.randint(2, 3), -15, -0.15, -0.15, True)
    if kind == "garbled":
        return Plan(kind, -rng.randint(2, 4), -1, -5, -0.05, -0.1, False)
    return Plan(kind, -rng.randint(2, 3), 0, 5, 0.0, -0.05, False)


def texts(kind: str, teller: str, subject: str, claim: str) -> dict[str, str]:
    """First-person memories for the three parties of a confrontation: the subject, the teller, anyone who heard it."""
    if kind == "false":
        return {
            "subject": f"{teller} has been telling people something untrue about me: \"{claim}\". I'm angry.",
            "teller": f"{subject} caught me repeating \"{claim}\" and it wasn't true. Embarrassing.",
            "listener": f"Turns out what {teller} said about {subject} (\"{claim}\") wasn't true.",
        }
    if kind == "garbled":
        return {
            "subject": f"{teller} has been passing around a mangled version of something about me: \"{claim}\".",
            "teller": f"{subject} heard me repeating \"{claim}\" and corrected the details. Awkward.",
            "listener": f"{subject} says {teller} got it wrong about \"{claim}\".",
        }
    return {
        "subject": f"{teller} has been spreading something true about me: \"{claim}\". I wish they hadn't.",
        "teller": f"{subject} heard me say \"{claim}\". It was true, but they weren't thrilled.",
        "listener": f"{subject} confirmed what {teller} said: \"{claim}\".",
    }


# ---------------------------------------------------------------- scorecard

def spread(rows: list[dict], log: list[dict]) -> dict:
    """How the grapevine is behaving. `rows` are memory rows with source_id/origin_id/hops/accuracy; `log` is the events.

    The rate is the share of rumor chains with a consequence: the subject heard it, or someone was corrected.
    Rumors that never reach anyone they are about aren't gossip, they're small talk; if none of them ever
    land, the room has no social cost for talking.
    """
    told = [r for r in rows if r.get("source_id")]
    chains = {r["origin_id"] for r in told if r.get("origin_id") is not None}
    hit = {e["origin"] for e in log if e.get("origin") in chains}
    n = len(chains)
    rate = None if n < 3 else round(100 * len(hit) / n)
    band = "none" if rate is None else "green" if rate >= 30 else "amber" if rate >= 10 else "red"
    return {
        "rate": rate, "band": band, "rumors": len(told), "chains": n,
        "avg_hops": round(sum(r["hops"] for r in told) / len(told), 1) if told else 0,
        "max_hops": max((r["hops"] for r in told), default=0),
        "distortion": round(sum(100 - r["accuracy"] for r in told) / len(told)) if told else 0,
        "caught_out": sum(1 for e in log if e.get("verdict") == "false"),
        "subject_heard": sum(1 for e in log if e.get("kind") == "confront"),
        "corrected": sum(1 for e in log if e.get("kind") == "correct"),
    }

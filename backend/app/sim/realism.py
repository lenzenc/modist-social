"""Realism scorecard and repetition detector. Pure text statistics, no model calls.

`score` grades a window of finished speech; `Realism` keeps a rolling window of recent speech so the prompts can be told
which phrases and openers are worn out.
"""
import math
import re
from collections import Counter, deque
from itertools import combinations

GREEN, AMBER = 70, 45
VOICE_FULL = 0.2  # average feature distance between speakers at which voices count as fully distinct
MIN_LINES = 12  # fewer speech lines than this and a metric is not scored
MIN_VOICE_LINES = 8  # a speaker needs this many lines to take part in the voice comparison
MIN_SHARED_PHRASE = 3  # times a phrase must recur before it counts as worn out
TIDY_MIN_LINES = 4  # a chat needs this many speech lines before its ending is judged

STOP = frozenset(
    "a an the and or but so of to in on at for with it its is are was were be been am i you he she they we me my your "
    "that this there then than as if do does did not no yes just".split()
)
INTERJECTIONS = frozenset("honestly ha haha oh well okay ok wait yeah hm hmm ope man look listen right so anyway".split())
FAREWELLS = (
    "cheers", "good talking", "take care", "catch you", "enjoy your", "nice chatting", "nice talking", "see you",
    "have a good", "good night", "goodnight", "good to see", "talk later", "later,", "have a great", "get going",
)
TOPIC_WORDS = {
    "beer": "beer ipa hops hop yeast brew brewing pint tap lager stout ale saison sour malt barrel pour".split(),
    "civic": "vote council zoning bike lane lanes potholes parking taxes mayor city election ballot".split(),
    "town": "weather rain snow forecast event restaurant food truck downtown festival market parade traffic".split(),
    "gossip": "heard rumor rumour apparently told secret gossip supposedly drama".split(),
    "sports": "game score twins vikings wild timberwolves playoffs coach season fantasy team lost won".split(),
    "life": "work boss job kid kids wife husband dog cat mom dad sister brother week landlord rent move moving".split(),
    "culture": "movie show music band album book song concert netflix podcast".split(),
    "story": "remember once time story years ago back when".split(),
}
TOPICS = (*TOPIC_WORDS, "event", "other")


# ---------------------------------------------------------------- text helpers


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", text.lower().replace("’", "'"))).strip()


def opener(text: str) -> str:
    return " ".join(norm(text).split()[:3])


def ngrams(text: str, n: int = 4) -> set[str]:
    words = norm(text).split()
    grams = (words[i:i + n] for i in range(len(words) - n + 1))
    return {" ".join(g) for g in grams if not all(w in STOP for w in g)}


def topic_of(text: str, on_event: bool = False) -> str:
    if on_event:
        return "event"
    words = Counter(norm(text).split())
    best, hits = "other", 0
    for name, keys in TOPIC_WORDS.items():
        n = sum(words[k] for k in keys)
        if n > hits:
            best, hits = name, n
    return best


def tidy_ending(texts: list[str]) -> bool:
    """True if a chat's last two lines read like a neat goodbye."""
    return any(f in t.lower() for t in texts[-2:] for f in FAREWELLS)


def _features(texts: list[str]) -> list[float]:
    n = len(texts)
    words = [len(t.split()) for t in texts]
    first = [(norm(t).split() or [""])[0] for t in texts]
    return [
        min(1.0, sum(words) / n / 40),
        sum(t.rstrip().endswith("?") for t in texts) / n,
        sum(t.rstrip().endswith("!") for t in texts) / n,
        sum(f in INTERJECTIONS for f in first) / n,
        sum(w <= 5 for w in words) / n,
        sum(w > 25 for w in words) / n,
        sum(("—" in t or "..." in t or "…" in t) for t in texts) / n,
    ]


def _dist(a: list[float], b: list[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def band(v: float | None) -> str:
    return "none" if v is None else "green" if v >= GREEN else "amber" if v >= AMBER else "red"


def _entropy(c: Counter) -> float:
    total = sum(c.values())
    if total == 0:
        return 0.0
    return -sum(v / total * math.log(v / total) for v in c.values() if v) / math.log(len(TOPICS))


# ---------------------------------------------------------------- the scorecard


def score(lines: list[tuple[int | None, str, str]], threads: dict[int, dict], prior_topics: list[Counter] | None = None,
          names: dict[str, str] | None = None) -> dict:
    """Grade a window of speech.

    `lines` are (thread_id, speaker_id, text) in order. `threads` maps thread_id to {"kind", "on_event"}.
    `prior_topics` are topic counts for the days before, used to spot the same topics night after night.
    """
    names = names or {}
    by_thread: dict[int, list[tuple[str, str]]] = {}
    for tid, sid, text in lines:
        if tid is not None:
            by_thread.setdefault(tid, []).append((sid, text))
    chats = {t: ls for t, ls in by_thread.items() if threads.get(t, {}).get("kind") == "chat"}
    orders = {t: ls for t, ls in by_thread.items() if threads.get(t, {}).get("kind") == "order"}

    metrics: dict[str, float | None] = dict.fromkeys(("openers", "phrases", "sameness", "topics", "endings"))
    detail: dict = {}

    # Fresh openers: how many chats begin with an opener the room keeps using.
    opens = Counter(opener(ls[0][1]) for ls in chats.values() if opener(ls[0][1]))
    repeated = {o for o, n in opens.items() if n >= MIN_SHARED_PHRASE}
    if len(chats) >= 5:
        metrics["openers"] = 100 * (1 - sum(opens[o] for o in repeated) / len(chats))
    greet = Counter(opener(ls[0][1]) for ls in orders.values() if ls)
    detail["openers"] = [{"text": o, "count": n} for o, n in opens.most_common(8) if n >= 2]
    detail["greetings"] = [{"text": o, "count": n} for o, n in greet.most_common(5) if n >= 2]

    # Phrase repetition and cross-person sameness.
    per_line = [(sid, ngrams(text)) for _, sid, text in lines]
    counts: Counter = Counter()
    speakers: dict[str, set[str]] = {}
    for sid, grams in per_line:
        counts.update(grams)
        for g in grams:
            speakers.setdefault(g, set()).add(sid)
    worn = {g for g, n in counts.items() if n >= MIN_SHARED_PHRASE}
    shared = {g for g in worn if len(speakers[g]) >= MIN_SHARED_PHRASE}
    detail["phrases"] = [
        {"text": g, "count": counts[g], "speakers": len(speakers[g])}
        for g in sorted(worn, key=lambda g: (-counts[g], g))[:12]
    ]
    voice = None
    by_speaker: dict[str, list[str]] = {}
    for _, sid, text in lines:
        by_speaker.setdefault(sid, []).append(text)
    feats = {s: _features(ts) for s, ts in by_speaker.items() if len(ts) >= MIN_VOICE_LINES}
    if len(feats) >= 3:
        pairs = [_dist(feats[a], feats[b]) for a, b in combinations(feats, 2)]
        voice = min(100.0, sum(pairs) / len(pairs) / VOICE_FULL * 100)
    detail["voice"] = None if voice is None else round(voice)
    if len(lines) >= MIN_LINES:
        metrics["phrases"] = 100 * (1 - sum(1 for _, g in per_line if g & worn) / len(lines))
        line_part = 100 * (1 - sum(1 for _, g in per_line if g & shared) / len(lines))
        metrics["sameness"] = line_part if voice is None else (line_part + voice) / 2

    # Topic variety, and how much of it repeats the previous days.
    today = Counter(topic_of(" ".join(t for _, t in ls), threads[tid].get("on_event", False)) for tid, ls in chats.items())
    detail["topic_mix"] = {k: today[k] for k in TOPICS if today[k]}
    if sum(today.values()) >= 5:
        variety = 100 * _entropy(today)
        before = sum(prior_topics or [], Counter())
        if sum(before.values()) >= 5:
            overlap = sum(min(today[k] / sum(today.values()), before[k] / sum(before.values())) for k in TOPICS)
            detail["topic_overlap"] = round(overlap, 2)
            variety = (variety + 100 * (1 - overlap)) / 2
        metrics["topics"] = variety

    # Neat endings: chats that close on a tidy goodbye.
    judged = [[t for _, t in ls] for ls in chats.values() if len(ls) >= TIDY_MIN_LINES]
    if len(judged) >= 5:
        tidy = sum(tidy_ending(ls) for ls in judged) / len(judged)
        detail["tidy_share"] = round(tidy, 2)
        metrics["endings"] = 100 * (1 - tidy)

    got = [v for v in metrics.values() if v is not None]
    overall = sum(got) / len(got) if got else None

    # Per person: who repeats themselves, and whose voice blends into the room's.
    mean_vec = [sum(col) / len(feats) for col in zip(*feats.values())] if feats else []
    people = []
    for sid, texts in by_speaker.items():
        if len(texts) < MIN_VOICE_LINES:
            continue
        own = Counter(g for t in texts for g in ngrams(t))
        top = own.most_common(1)
        opens_own = Counter(opener(t) for t in texts)
        people.append({
            "id": sid, "name": names.get(sid, sid), "lines": len(texts),
            "phrase": top[0][0] if top and top[0][1] >= 2 else "", "phrase_count": top[0][1] if top and top[0][1] >= 2 else 0,
            "opener_repeat": round(sum(n for n in opens_own.values() if n >= 2) / len(texts), 2),
            "blend": round(1 - min(1.0, _dist(feats[sid], mean_vec) / VOICE_FULL), 2) if sid in feats else None,
        })
    people.sort(key=lambda r: (-r["phrase_count"], -r["opener_repeat"], r["name"]))

    out = {k: None if v is None else round(v) for k, v in metrics.items()}
    return {
        "overall": None if overall is None else round(overall),
        "metrics": out, "bands": {k: band(v) for k, v in out.items()} | {"overall": band(overall)},
        "lines": len(lines), "chats": len(chats), "detail": detail, "people": people[:25],
    }


# ---------------------------------------------------------------- live tracker


class Realism:
    """Rolling window of recent speech, used to tell the next speaker what is worn out."""

    PER_SPEAKER = 150
    ROOM = 600

    def __init__(self) -> None:
        self.per: dict[str, deque[set[str]]] = {}
        self.room: deque[tuple[str, set[str], str, bool]] = deque(maxlen=self.ROOM)
        self.endings: deque[bool] = deque(maxlen=20)
        self._cache: tuple[Counter, dict[str, set[str]], Counter] | None = None

    def add(self, speaker: str, text: str, first: bool = False) -> None:
        grams = ngrams(text)
        self.per.setdefault(speaker, deque(maxlen=self.PER_SPEAKER)).append(grams)
        self.room.append((speaker, grams, opener(text), first))
        self._cache = None

    def warm(self, rows: list[tuple[str, str, bool]]) -> None:
        """Seed from stored speech, oldest first: (speaker, text, first line of its chat)."""
        for sid, text, first in rows:
            self.add(sid, text, first)

    def add_ending(self, tidy: bool) -> None:
        self.endings.append(tidy)

    def tidy_share(self) -> float:
        return sum(self.endings) / len(self.endings) if len(self.endings) >= 5 else 0.0

    def _room_counts(self):
        if self._cache is None:
            counts: Counter = Counter()
            speakers: dict[str, set[str]] = {}
            opens: Counter = Counter()
            for sid, grams, op, first in self.room:
                counts.update(grams)
                for g in grams:
                    speakers.setdefault(g, set()).add(sid)
                if first and op:
                    opens[op] += 1
            self._cache = (counts, speakers, opens)
        return self._cache

    def avoid_for(self, pid: str, first_line: bool = False, limit: int = 5) -> list[str]:
        """Phrases this speaker should not reach for again: their own tics, then the room's, then stale openers."""
        own = Counter(g for grams in self.per.get(pid, ()) for g in grams)
        out = _drop_nested([g for g, n in sorted(own.items(), key=lambda x: (-x[1], x[0])) if n >= 2])[:2]
        counts, speakers, opens = self._room_counts()
        shared = [g for g in counts if len(speakers[g]) >= MIN_SHARED_PHRASE]
        out += sorted(shared, key=lambda g: (-counts[g], g))
        if first_line:
            out += [o for o, n in opens.most_common(limit) if n >= MIN_SHARED_PHRASE]
        return _drop_nested(out)[:limit]


def _drop_nested(phrases: list[str]) -> list[str]:
    """Overlapping 4-grams from one longer phrase tell the model the same thing, so keep the first of each cluster."""
    kept: list[str] = []
    for p in phrases:
        words = set(p.split())
        if not any(len(words & set(k.split())) >= 3 for k in kept):
            kept.append(p)
    return kept

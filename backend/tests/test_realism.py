import random

from app.sim import realism
from app.sim.realism import Realism, band, ngrams, norm, opener, score, tidy_ending, topic_of


def test_text_helpers():
    assert norm("Ha!  That's  fine, honestly.") == "ha that's fine honestly"
    assert opener("Honestly, I think it's fine.") == "honestly i think"
    assert "tell me about it" in ngrams("Ha, tell me about it, really")
    assert ngrams("and it is so") == set()  # all stopwords
    assert ngrams("two words") == set()


def test_topic_and_endings():
    assert topic_of("this IPA has great hops and yeast") == "beer"
    assert topic_of("the council vote on bike lanes and zoning") == "civic"
    assert topic_of("anything at all", on_event=True) == "event"
    assert topic_of("mm") == "other"
    assert tidy_ending(["so anyway", "Good talking to you, take care!"])
    assert not tidy_ending(["so anyway", "wait is that my phone"])


def _threads(n, kind="chat"):
    return {i: {"kind": kind} for i in range(n)}


def _chat_lines(n, line):
    return [(i, f"p{i % 6}", line(i, j)) for i in range(n) for j in range(3)]


def test_repetitive_room_scores_low_and_varied_room_high():
    same = _chat_lines(12, lambda i, j: "Tell me about it, my boss has been on a tear all week.")
    out = score(same, _threads(12))
    assert out["metrics"]["openers"] == 0
    assert out["metrics"]["phrases"] == 0
    assert out["metrics"]["sameness"] < 30
    assert out["bands"]["phrases"] == "red"

    words = "amber copper pine harbor velvet quartz meadow lantern orchid summit river pebble falcon maple".split()

    def varied(i, j):
        r = random.Random(i * 10 + j)
        return " ".join(r.sample(words, 8))

    out = score(_chat_lines(12, varied), _threads(12))
    assert out["metrics"]["openers"] > 80
    assert out["metrics"]["phrases"] == 100
    assert out["detail"]["phrases"] == []


def test_neat_endings_lower_the_score():
    lines = [(i, "p1", t) for i in range(6) for t in ("one two three", "four five six", "seven eight nine", "Cheers, take care!")]
    out = score(lines, _threads(6))
    assert out["detail"]["tidy_share"] == 1.0
    assert out["metrics"]["endings"] == 0


def test_not_enough_data_is_not_scored():
    out = score([(0, "p1", "hello there friend")], _threads(1))
    assert out["overall"] is None
    assert out["metrics"]["phrases"] is None
    assert band(None) == "none" and band(80) == "green" and band(50) == "amber" and band(10) == "red"


def test_avoid_prefers_own_tics_then_room_phrases_and_caps():
    r = Realism()
    for _ in range(3):
        r.add("p0", "honestly the hops are a bit much for me", first=True)
    for sid in ("p1", "p2", "p3"):
        r.add(sid, "tell me about it my boss is awful")
    got = r.avoid_for("p0")
    assert got[0] in ngrams("honestly the hops are a bit much for me")  # their own tic comes first
    assert any("tell me about it" in g or "me about it my" in g for g in got)
    assert len(got) <= 5
    assert "honestly the hops" in r.avoid_for("p9", first_line=True)  # a stale opener, for someone with no history
    assert r.avoid_for("p9") != [] and Realism().avoid_for("p0") == []


def test_tidy_share_needs_a_sample():
    r = Realism()
    for _ in range(4):
        r.add_ending(True)
    assert r.tidy_share() == 0.0
    r.add_ending(True)
    assert r.tidy_share() == 1.0


def _worn_scene(monkeypatch, feedback=True):
    from app.agents.agent import build_turn
    from app.config import settings

    from tests.test_sim import _chat, _scene_director

    d = _scene_director()
    d.persona_text["p0"] = ""
    for sid in ("p1", "p2", "p3"):
        d.realism.add(sid, "tell me about it my boss is awful", first=True)
    monkeypatch.setattr(settings, "realism_feedback", feedback)
    return d, build_turn, _chat


def test_build_turn_adds_the_avoid_hint(monkeypatch):
    d, build_turn, _chat = _worn_scene(monkeypatch)
    req = build_turn(d, _chat(False), d.people["p0"], False)
    assert "Don't reuse these worn-out phrases or openers:" in req.context
    assert req.avoid and any("tell me about it" in a or "me about it" in a for a in req.avoid)


def test_avoid_hint_can_be_turned_off(monkeypatch):
    d, build_turn, _chat = _worn_scene(monkeypatch, feedback=False)
    req = build_turn(d, _chat(False), d.people["p0"], False)
    assert "worn-out" not in req.context and req.avoid == []


def test_wind_down_can_fizzle_when_endings_are_too_neat(monkeypatch):
    d, build_turn, _chat = _worn_scene(monkeypatch)
    for _ in range(6):
        d.realism.add_ending(True)
    seen = {build_turn(d, _chat(False, tid=i), d.people["p0"], True).context.count("running out of steam") for i in range(30)}
    assert seen == {0, 1}  # about half fizzle, half wrap up
    d.realism.endings.clear()
    assert all("running out of steam" not in build_turn(d, _chat(False, tid=i), d.people["p0"], True).context for i in range(10))

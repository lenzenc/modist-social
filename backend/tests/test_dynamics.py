import random

from app.agents.agent import build_turn
from app.llm.mock import MockLLM
from app.llm.types import TurnRequest, Utterance
from app.sim import dynamics
from app.sim.social import pair_key
from app.sim.state import PersonState, RelState, ThreadState
from tests.test_beats import _turn_director
from tests.test_drunk import _p, _run
from tests.test_sim import NOW, _chat


def _g(pid, **kw):
    persona = kw.pop("persona", {})
    return _p(id=pid, short=pid.upper(), persona={"talk": 0.5, **persona}, **kw)


def _rels(**pairs):
    """A rel(a, b) lookup from {"a-b": RelState}; any other pair is strangers."""
    table = {pair_key(*k.split("-")): v for k, v in pairs.items()}
    return lambda a, b: table.get(pair_key(a, b)) or RelState()


CLOSE = RelState(familiarity=80, affinity=60, bond="close_friends")
COUPLE = RelState(familiarity=90, affinity=80, bond="couple")


# ---------------------------------------------------------------- pure rules


def test_the_odd_one_out_is_found_next_to_a_couple_and_never_in_a_pair():
    rel = _rels(**{"a-b": COUPLE, "a-c": RelState(familiarity=5), "b-c": RelState(familiarity=5)})
    assert dynamics.outsider(["a", "b", "c"], rel) == "c"
    assert dynamics.outsider(["a", "b"], rel) is None
    even = _rels(**{"a-b": CLOSE, "a-c": CLOSE, "b-c": CLOSE})
    assert dynamics.outsider(["a", "b", "c"], even) is None


def test_dominance_orders_personas_and_buzz_adds_to_it():
    loud = _g("a", persona={"big5": {"e": 5, "a": 1}, "style": "debater"})
    quiet = _g("b", persona={"big5": {"e": 1, "a": 5}, "style": "listener"})
    assert dynamics.dominance(loud) > 1.0 > dynamics.dominance(quiet) >= 0.4
    assert dynamics.dominance(_g("c", buzz=0.8)) > dynamics.dominance(_g("c"))
    assert dynamics.floor_keep(loud) > dynamics.floor_keep(quiet) == 0.12


def test_only_a_clearly_more_dominant_member_talks_over_the_speaker(monkeypatch):
    monkeypatch.setattr(dynamics, "INTERRUPT_CHANCE", 1.0)
    loud = _g("a", persona={"big5": {"e": 5, "a": 1}, "style": "debater"})
    quiet = _g("b", persona={"big5": {"e": 1, "a": 5}, "style": "listener"})
    rng = random.Random(1)
    assert dynamics.interrupter(rng, quiet, [loud]) is loud
    assert dynamics.interrupter(rng, loud, [quiet]) is None
    assert dynamics.interrupter(rng, _g("x"), [_g("y")]) is None


def test_a_cut_off_line_ends_in_a_dash():
    assert dynamics.trail_off("Well, the thing is.") == "Well, the thing is—"
    assert dynamics.trail_off("So—") == "So—"


def test_hogging_needs_enough_lines_and_more_than_half():
    assert dynamics.hogging(["a"] * 5) == ""
    assert dynamics.hogging(["a", "a", "a", "a", "a", "b", "c", "a"]) == "a"
    assert dynamics.hogging(["a", "b", "c", "a", "b", "c", "a", "b"]) == ""


def test_jokes_land_with_friends_more_than_with_the_sour():
    teller = _g("a")
    fan = _g("b", mood=0.3)
    sour = _g("c", mood=-0.6)
    rng = random.Random(2)
    friend = RelState(affinity=70)
    foe = RelState(affinity=-50)
    n = lambda l, r: sum(dynamics.reception(rng, teller, l, r) == "landed" for _ in range(500))
    assert n(fan, friend) > 300 > 200 > n(sour, foe)
    assert {dynamics.reception(rng, teller, sour, foe) for _ in range(300)} == {"landed", "flat", "stung"}
    assert dynamics.verdict({"a": "landed", "b": "landed"}) == "landed"
    assert dynamics.verdict({"a": "landed", "b": "flat"}) == "mixed"
    assert dynamics.verdict({"a": "stung", "b": "flat"}) == "flat"


def test_the_reaction_line_names_everyone():
    text = dynamics.reaction("Sam", {"a": "landed", "b": "flat", "c": "stung"}, {"a": "Ann", "b": "Bo", "c": "Cy"})
    assert text.startswith("Sam lands a joke.") and "Ann cracks up" in text and "Bo just sips" in text and "Cy forces" in text


def test_moods_drift_toward_the_table_and_stay_in_range():
    happy, sad = _g("a", mood=0.8), _g("b", mood=-0.8)
    table = dynamics.vibe([happy, sad])
    for _ in range(200):
        dynamics.catch(happy, table)
        dynamics.catch(sad, table)
    assert abs(happy.mood - sad.mood) < 0.2 and -1 <= sad.mood <= happy.mood <= 1
    assert dynamics.vibe([]) == 0.0


def test_the_vibe_word():
    assert [dynamics.vibe_word(v) for v in (0.5, 0.0, -0.4)] == ["lively", "easy", "flat"]
    assert dynamics.vibe_word(0.5, 1.2) == "tense"


def test_steering_follows_what_they_avoid_and_picks_their_own_interest(monkeypatch):
    monkeypatch.setitem(dynamics.STEER_CHANCE, "avoid", 1.0)
    p = _g("a", persona={"avoid": ["his divorce"], "interests": ["birdwatching", "bikes"]})
    why, topic = dynamics.steer_due(random.Random(3), p, ["Did you hear about the divorce?"], [], False, 0)
    assert why == "avoid" and topic in ("birdwatching", "bikes")
    assert dynamics.steer_due(random.Random(3), p, ["Nice weather."], [], False, 0) is None
    assert dynamics.steer_due(random.Random(3), _g("b", persona={"avoid": ["divorce"]}), ["the divorce"], [], False, 0) is None


def test_steering_when_a_falling_out_is_mentioned_or_a_chat_goes_stale(monkeypatch):
    monkeypatch.setitem(dynamics.STEER_CHANCE, "touchy", 1.0)
    monkeypatch.setitem(dynamics.STEER_CHANCE, "stale", 1.0)
    p = _g("a", persona={"interests": ["bikes"], "style": "asker"})
    assert dynamics.steer_due(random.Random(1), p, ["Ask Dee about it."], ["Dee"], False, 0)[0] == "touchy"
    assert dynamics.steer_due(random.Random(1), p, ["Same old."], [], False, 7)[0] == "stale"
    assert dynamics.steer_due(random.Random(1), p, ["Same old."], [], False, 2) is None


def test_a_close_pair_with_a_shared_interest_splits_off_a_big_table(monkeypatch):
    monkeypatch.setattr(dynamics, "SPLINTER_CHANCE", 1.0)
    guests = [_g("a", persona={"interests": ["bikes"]}), _g("b", persona={"interests": ["bikes"]}),
              _g("c", persona={"interests": ["golf"]}), _g("d", persona={"interests": ["opera"]})]
    rel = _rels(**{"a-b": RelState(familiarity=60, affinity=40, bond="friends")})
    assert dynamics.splinter(random.Random(1), guests, rel) == ("a", "b")
    assert dynamics.splinter(random.Random(1), guests[:3], rel) is None  # too small a table
    assert dynamics.splinter(random.Random(1), guests, _rels()) is None  # nobody is close


def test_floor_share_and_the_report():
    threads = {1: {"kind": "chat"}, 2: {"kind": "chat"}, 3: {"kind": "order"}}
    even = [(i, s, "x") for i in range(1, 9) for s in "abcabcabc"]
    chats = {i: {"kind": "chat"} for i in range(1, 9)}
    assert dynamics.floor(even, chats)["band"] == "amber"  # a perfect rota is too tidy
    lively = [(i, s, "x") for i in range(1, 9) for s in "aabcabcab"]
    got = dynamics.floor(lively, chats)
    assert got["band"] == "green" and got["chats"] == 8 and 40 <= got["share"] <= 50
    mono = [(i, s, "x") for i in range(1, 9) for s in "aaaaaaabc"]
    assert dynamics.floor(mono, chats)["band"] == "red"
    assert dynamics.floor(even[:12], threads)["band"] == "none"
    log = [{"kind": "joke", "result": "landed"}, {"kind": "joke", "result": "flat"}, {"kind": "split"}, {"kind": "interrupt"},
           {"kind": "steer"}, {"kind": "steer"}, {"kind": "outsider"}]
    r = dynamics.report(log, [], {}, 4)
    assert r["jokes"] == {"landed": 1, "mixed": 0, "flat": 1} and r["steers"] == 2 and r["splits"] == 1
    assert r["per_patron_day"]["joke"] == 0.5 and dynamics.report([], [], {}, 0)["per_patron_day"]["joke"] is None


# ---------------------------------------------------------------- the scene and the mock


def _table(d, n=3):
    for i in range(2, n):
        if f"p{i}" not in d.people:
            d.people[f"p{i}"] = PersonState(id=f"p{i}", name=f"P{i} X", short=f"P{i}", display=f"P{i} X", role="patron",
                                            pronouns="they/them", color="#000", persona={"talk": 0.5})
        d.people[f"p{i}"].present = True
        d.people[f"p{i}"].persona["job"] = "welder"
    return d


def _scene(d, t, pid="p0"):
    d.persona_text.update({k: "" for k in d.people})
    return build_turn(d, t, d.people[pid], False)


def _three(lines=None, turns=3):
    t = _chat(False, lines=lines or [("speech", "p1", "So.")], turns=turns)
    t.members, t.ever = ["p0", "p1", "p2"], dict.fromkeys(["p0", "p1", "p2"])
    return t


def test_the_scene_carries_every_group_hint():
    from tests.test_sim import _scene_director

    d = _table(_scene_director())
    t = _three()
    t.vibe, t.outsider = 0.6, "p0"
    t.interrupt, t.joking, t.steer = ("p0", "p1"), "p0", {"p0": "bikes"}
    t.joke = {"teller": "p1", "by": {"p0": "flat"}}
    req = _scene(d, t)
    assert req.interrupted and req.joke and req.outsider and req.steer == "bikes" and req.laughed is False and req.vibe == "lively"
    for text in ("mood at the table is lively", "on the outside", "talks over you", "Make a joke", "Change the subject on purpose to bikes",
                 "didn't land with you"):
        assert text in req.context
    assert not t.steer and not t.joke["by"]  # told once
    t.interrupt = ("p2", "p0")
    req = _scene(d, t)
    assert req.interrupting == "P2" and "Cut in on P2" in req.context


def test_the_quiet_ones_are_told_when_one_person_runs_the_table():
    from tests.test_sim import _scene_director

    d = _table(_scene_director())
    lines = [("speech", "p1", "blah")] * 7 + [("speech", "p2", "ok")]
    assert "P1 has been doing most of the talking" in _scene(d, _three(lines), "p0").context
    assert "doing most of the talking" not in _scene(d, _three(lines), "p1").context


def test_a_split_off_chat_starts_with_a_note():
    from tests.test_sim import _scene_director

    d = _scene_director()
    t = _chat(False)
    t.split_from = 9
    assert "broke off from the bigger table" in _scene(d, t).context


def test_the_mock_voices_each_group_behaviour():
    mock = MockLLM()
    base = dict(person_id="p0", person_name="Pat", world="", persona="", context="", last_line="Hi")
    say = lambda **kw: _run(mock.speak(TurnRequest(**base, **kw))).say
    assert say(interrupting="Dee").count("Dee") == 1
    assert say(interrupted=True).endswith("—")
    assert say(joke=True) in __import__("app.llm.mock", fromlist=["_JOKES"])._JOKES
    assert "bikes" in say(steer="bikes")
    laughs = {say(laughed=True) for _ in range(60)}
    assert any(x.startswith(("Ha", "Oh")) for x in laughs)


# ---------------------------------------------------------------- the director


def _live(utt):
    d, posts = _turn_director(utt)
    _table(d)
    d.social.apply_delta = _noop
    return d, posts


async def _noop(*a, **k):
    return None


def test_a_dominant_member_talks_over_the_speaker_and_speaks_next(monkeypatch):
    monkeypatch.setattr(dynamics, "INTERRUPT_CHANCE", 1.0)
    d, posts = _live(Utterance(say="Well, I was going to say that the thing about it is"))
    d.people["p1"].persona.update({"big5": {"e": 5, "a": 1}, "style": "debater"})
    d.people["p0"].persona.update({"big5": {"e": 1, "a": 5}, "style": "listener"})
    d.people["p2"].persona.update({"big5": {"e": 1, "a": 5}, "style": "listener"})
    t = _three([("speech", "p1", "So."), ("speech", "p2", "Right.")], turns=3)
    d.threads[t.id] = t
    d.roll_dynamics(t, d.people["p0"])
    assert t.interrupt == ("p0", "p1")
    _run(d.take_turn(t, d.people["p0"]))
    assert d.group_log[-1]["kind"] == "interrupt"
    assert d.pick_speaker(t).id == "p1"
    _run(d.take_turn(t, d.people["p1"]))
    assert t.interrupt is None


def test_the_interruption_passes_if_someone_else_speaks(monkeypatch):
    d, _ = _live(Utterance(say="Hm."))
    t = _three(turns=3)
    t.interrupt = ("p0", "p1")
    d.threads[t.id] = t
    d.roll_dynamics(t, d.people["p2"])
    assert t.interrupt is None


def test_a_joke_gets_one_reaction_line_and_moves_moods(monkeypatch):
    monkeypatch.setattr(dynamics, "joke_due", lambda rng, p: p.id == "p0")
    monkeypatch.setattr(dynamics, "steer_due", lambda *a: None)
    monkeypatch.setattr(dynamics, "interrupter", lambda *a: None)
    d, posts = _live(Utterance(say="Why did the hop cross the road?"))
    t = _three([("speech", "p1", "So."), ("speech", "p2", "Right.")], turns=3)
    d.threads[t.id] = t
    d.rng = random.Random(0)
    before = {k: d.people[k].mood for k in d.people}
    _run(d.take_turn(t, d.people["p0"]))
    reactions = [x for k, s, x in posts if k == "action" and "lands a joke" in x]
    assert len(reactions) == 1 and reactions[0].startswith("P0 lands a joke.")
    assert t.joke["teller"] == "p0" and set(t.joke["by"]) == {"p1", "p2"} and t.joking == ""
    assert d.group_log[-1]["kind"] == "joke" and d.group_log[-1]["result"] in ("landed", "mixed", "flat")
    assert any(d.people[k].mood != before[k] for k in ("p0", "p1", "p2"))


def test_a_silent_turn_does_not_tell_a_joke(monkeypatch):
    monkeypatch.setattr(dynamics, "joke_due", lambda rng, p: p.id == "p0")
    monkeypatch.setattr(dynamics, "steer_due", lambda *a: None)
    monkeypatch.setattr(dynamics, "interrupter", lambda *a: None)
    d, posts = _live(Utterance(say="", beat="shrugs"))
    t = _three(turns=3)
    d.threads[t.id] = t
    _run(d.take_turn(t, d.people["p0"]))
    assert not any("lands a joke" in x for _, _, x in posts) and t.joke is None


def test_the_table_catches_a_mood():
    d, _ = _live(Utterance(say="Great night."))
    t = _three(turns=3)
    d.threads[t.id] = t
    d.people["p0"].mood, d.people["p1"].mood, d.people["p2"].mood = 0.9, 0.0, -0.3
    _run(d.take_turn(t, d.people["p1"]))
    assert t.vibe > 0 and d.people["p2"].mood > -0.3


def test_the_odd_one_out_is_noticed_and_may_bow_out(monkeypatch):
    monkeypatch.setattr(dynamics, "OUTSIDER_EXCUSE", 1.0)
    d, _ = _live(Utterance(say="Hm."))
    d.social.rels[pair_key("p1", "p2")] = COUPLE
    t = _three([("speech", "p1", "So."), ("speech", "p2", "Right.")], turns=5)
    d.threads[t.id] = t
    d.roll_dynamics(t, d.people["p0"])
    assert t.outsider == "p0" and "p0" in t.excuse and d.group_log[-1] == {**d.group_log[-1], "kind": "outsider", "pids": ["p0"]}
    assert d.pick_speaker(t) is not None


def test_a_big_table_splits_into_two_chats_at_the_same_table(monkeypatch):
    monkeypatch.setattr(dynamics, "SPLINTER_CHANCE", 1.0)
    d, posts = _live(Utterance(say="Yeah."))
    _table(d, 4)
    for pid in ("p0", "p1", "p2", "p3"):
        d.people[pid].persona["interests"] = ["bikes"] if pid in ("p0", "p1") else [pid]
        d.people[pid].thread_id = 1
    d.social.rels[pair_key("p0", "p1")] = RelState(familiarity=70, affinity=50, bond="friends")
    t = ThreadState(id=1, channel="inside-tables", kind="chat", started=NOW, members=["p0", "p1", "p2", "p3"],
                    ever=dict.fromkeys(["p0", "p1", "p2", "p3"]), max_turns=8, turns=5,
                    lines=[("speech", "p2", "So."), ("speech", "p3", "Yep.")], table=2)
    t.span = {m: [0, None] for m in t.members}
    d.threads[1] = t
    opened = []

    async def open_thread(channel, kind, members, max_turns, **kw):
        side = ThreadState(id=2, channel=channel, kind=kind, started=NOW, members=list(members), ever=dict.fromkeys(members),
                           max_turns=max_turns, table=t.table)
        opened.append(side)
        return side

    d.open_thread = open_thread
    _run(d.take_turn(t, d.people["p2"]))
    assert t.members == ["p2", "p3"] and t.max_turns == 11
    assert opened and opened[0].members == ["p0", "p1"] and opened[0].split_from == 1 and opened[0].table == t.table
    assert any("drift into a conversation of their own" in x for _, _, x in posts)
    assert d.group_log[-1]["kind"] == "split"
    assert t.span["p0"][1] is not None and t.span["p1"][1] is not None


def test_group_events_round_trip_into_the_report():
    d, _ = _live(Utterance(say="Hm."))
    d.log_group("split", ["p0", "p1"], size=4)
    d.log_group("joke", ["p0", "p1"], result="mixed")
    d.log_group("steer", ["p0"], why="avoid")
    day = d.group_log[0]["day"]
    r = dynamics.report([e for e in d.group_log if e["day"] == day], [], {}, 2)
    assert r["splits"] == 1 and r["jokes"]["mixed"] == 1 and r["steers"] == 1
    for _ in range(dynamics.LOG_KEEP + 10):
        d.log_group("steer", ["p0"])
    assert len(d.group_log) == dynamics.LOG_KEEP

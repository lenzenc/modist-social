import asyncio
import random
from datetime import datetime, timedelta

import yaml

from app.agents.prompts import persona_prompt
from app.seed.loader import HERE
from app.sim import environment, human
from app.sim.clock import SimClock
from app.sim.social import RECALL_MAX, Social, rel_time
from app.sim.state import MemoryRec, PersonState, RelState, ThreadState

NOW = datetime(2026, 10, 21, 20, 0)  # a Wednesday evening


def _p(**persona):
    return PersonState(id="p0", name="P0 X", short="P0", display="P0 X", role="patron", pronouns="they/them",
                       color="#000", persona={"talk": 0.5, "age": 30, **persona})


class _Rng:
    """A random source that always rolls the same number."""

    def __init__(self, v):
        self.v = v

    def random(self):
        return self.v


# ---------------------------------------------------------------- personas


def test_every_seed_person_has_the_new_persona_fields():
    rows = yaml.safe_load((HERE / "patrons.yaml").read_text()) + yaml.safe_load((HERE / "bartenders.yaml").read_text())
    assert len(rows) == 45
    for r in rows:
        assert set(r["big5"]) == set("ocean"), r["id"]
        assert all(1 <= v <= 5 for v in r["big5"].values()), r["id"]
        assert r["life"] and r["beer"] in human.BEER_TEXT and r["style"] in human.STYLE_TEXT
        assert r["takes"] and r["tics"] and r["reasons"] and set(r["reasons"]) <= set(human.REASON_TEXT), r["id"]
    for r in yaml.safe_load((HERE / "patrons.yaml").read_text()):
        e = r["big5"]["e"]
        assert (e <= 2) if r["talk"] < 0.35 else (e >= 4) if r["talk"] > 0.65 else (2 <= e <= 4), r["id"]


def test_persona_prompt_uses_the_new_fields_and_still_renders_without_them():
    base = {"age": 40, "job": "welder", "traits": ["dry"], "politics": "centrist", "drink": "amber",
            "interests": ["fishing"], "quirk": "hums", "voice": "slow"}
    old = persona_prompt(_p(**base))
    assert "Opinions you hold firmly" not in old and "YOU ARE" in old
    rich = persona_prompt(
        _p(**base, big5={"o": 2, "c": 4, "e": 5, "a": 1, "n": 3}, life="Just got laid off.", takes=["hazy IPAs are a fad"],
           avoid=["work"], tics=["says 'honestly though'"], style="joker", beer="nerd"),
        lately="Interviewing at the mill.",
    )
    for needle in ("very outgoing and loud", "blunt and quick to argue", "Just got laid off. Lately: Interviewing",
                   "hazy IPAs are a fad", "Things you steer away from: work", "honestly though", "joke and tease", "know beer deeply"):
        assert needle in rich, needle
    assert "5" not in human.trait_words({"big5": {"e": 5, "a": 3}})  # traits are words, never numbers


# ---------------------------------------------------------------- state over time


def test_buzz_rises_with_drinks_and_wears_off():
    p = _p()
    for _ in range(3):
        p.buzz = human.add_drink(p.buzz, p.persona)
    assert 0.45 < p.buzz < 0.7
    human.tick(p, 60)
    assert 0.35 < p.buzz < 0.6
    human.tick(p, 600)
    assert p.buzz == 0.0


def test_battery_drains_faster_for_the_reserved_and_recovers_when_free():
    shy, loud = _p(big5={"e": 1}), _p(big5={"e": 5})
    for _ in range(10):
        human.spoke(shy), human.spoke(loud)
    assert shy.battery < loud.battery < 1.0
    shy.thread_id = 5
    before = shy.battery
    human.tick(shy, 60)
    assert shy.battery == before  # no rest while in a conversation
    shy.thread_id = None
    human.tick(shy, 60)
    assert shy.battery > before


def test_mood_blends_in_what_the_model_reports_and_settles_back():
    p = _p(big5={"n": 5})
    human.blend_mood(p, "down")
    assert p.mood < -0.15
    human.blend_mood(p, "nonsense")  # unknown tags are ignored
    m = p.mood
    assert p.mood == m
    human.tick(p, 600)
    assert abs(p.mood) < 0.01


def test_excuse_is_due_for_a_need_or_a_drained_battery_but_not_early_on():
    p = _p()
    assert human.excuse_due(p, NOW, 5, _Rng(0.0)) == ""
    p.need, p.need_at = "restroom", NOW - timedelta(minutes=1)
    assert "restroom" in human.excuse_due(p, NOW, 0, _Rng(0.9))
    p.need, p.need_at = "", None
    p.battery = 0.1
    assert human.excuse_due(p, NOW, 1, _Rng(0.0)) == ""  # too soon into the chat
    assert "socially spent" in human.excuse_due(p, NOW, 4, _Rng(0.0))
    p.wants_leave = True
    assert human.excuse_due(p, NOW, 4, _Rng(0.0)) == ""  # they're leaving anyway


def test_traits_change_behaviour_not_just_words():
    shy, social = _p(big5={"e": 1}), _p(big5={"e": 5})
    assert human.drive(shy, NOW) < human.drive(social, NOW)
    solo = _p(big5={"e": 3})
    base = human.drive(solo, NOW)
    solo.reason = "solo"
    assert human.drive(solo, NOW) < base
    solo.battery = 0.1
    assert human.drive(solo, NOW) < base / 2
    assert human.escalation({"big5": {"a": 1}}) > human.escalation({}) > human.escalation({"big5": {"a": 5}})
    assert human.event_interest({"big5": {"o": 5}}) > human.event_interest({"big5": {"o": 1}})
    assert human.avoids(-30) and not human.avoids(-29)
    assert human.affinity_weight(60) > 1 > human.affinity_weight(-60) >= 0.1


def test_length_modes_follow_style_and_energy():
    def share(p, mode, n=3000):
        rng = random.Random(1)
        return sum(human.length_mode(p, rng) == mode for _ in range(n)) / n

    assert share(_p(style="storyteller"), "story") > share(_p(style="listener"), "story")
    assert share(_p(style="listener"), "react") > share(_p(style="storyteller"), "react")
    tired = _p(style="storyteller")
    tired.battery = 0.1
    assert share(tired, "story") < 0.05 and share(tired, "react") > 0.4


def test_right_now_line_reflects_state():
    p = _p()
    p.reason = "unwind"
    assert human.right_now(p, NOW) == "Right now: here to unwind after the day."
    p.drinks, p.buzz, p.battery, p.mood = 3, 0.3, 0.2, -0.3
    p.need, p.need_at = "air", NOW + timedelta(minutes=5)
    line = human.right_now(p, NOW)
    for needle in ("drink number 3", "feeling it a little", "socially drained", "irritable", "step outside"):
        assert needle in line, needle
    p.buzz = 0.6
    assert "properly drunk" in human.right_now(p, NOW)


# ---------------------------------------------------------------- memory


def _mem(text, hours_ago, importance=5, about=(), kind="event"):
    return MemoryRec(NOW - timedelta(hours=hours_ago), text, list(about), importance, kind)


def test_recall_prefers_important_and_relevant_over_merely_recent():
    s = Social()
    s.memories["p0"] = [
        _mem("big promise", 200, importance=9),
        _mem("about the person here", 300, importance=4, about=["p1"]),
        _mem("recent small talk", 1, importance=2),
    ] + [_mem(f"filler {i}", 100 + i, importance=2) for i in range(10)]
    got = s.recall("p0", {"p1"}, k=3, now=NOW)
    assert "about the person here" in got and "big promise" in got and "recent small talk" not in got


def test_recall_returns_up_to_twenty_oldest_first():
    s = Social()
    s.memories["p0"] = [_mem(f"m{i}", 100 - i) for i in range(60)]
    got = s.recall_recs("p0", set(), NOW)
    assert RECALL_MAX == 20 and 15 < len(got) <= 20
    assert [m.sim_ts for m in got] == sorted(m.sim_ts for m in got)
    few = Social()
    few.memories["p0"] = [_mem(f"m{i}", i) for i in range(4)]
    assert len(few.recall("p0", set(), now=NOW)) == 4  # twenty is a cap, not a quota


def test_recall_keywords_pull_in_memories_about_what_is_being_said():
    s = Social()
    s.memories["p0"] = [_mem("their dog Biscuit is sick", 50), *[_mem(f"unrelated {i}", 40) for i in range(8)]]
    assert "their dog Biscuit is sick" in s.recall("p0", set(), k=2, now=NOW, text="how is the dog Biscuit doing")


def test_followups_surface_once_for_the_person_they_are_about():
    from app.agents.agent import build_turn

    from tests.test_sim import _chat, _scene_director

    d = _scene_director()
    d.clock = SimClock(start=NOW)
    p = d.people["p0"]
    d.social.memories["p0"] = [_mem("Ask P1 how the interview went", 30, 6, ["p1"], "followup")]
    d.persona_text["p0"] = ""
    first = build_turn(d, _chat(False), p, False)
    assert "(to bring up if it fits) Ask P1 how the interview went" in first.context
    again = build_turn(d, _chat(False, tid=2), p, False)
    assert "interview" not in again.context
    assert d.social.memories["p0"][0].kind == "done"


def test_relative_time():
    assert rel_time(NOW, NOW) == "earlier today"
    assert rel_time(NOW - timedelta(days=1), NOW) == "yesterday"
    assert rel_time(NOW - timedelta(days=3), NOW) == "on Sunday"
    assert rel_time(NOW - timedelta(days=9), NOW) == "last Monday"
    assert rel_time(NOW - timedelta(days=21), NOW) == "3 weeks ago"


# ---------------------------------------------------------------- first meetings


class _Wrap:
    """A Director whose social layer records instead of writing to the database."""

    def __init__(self, summary=None):
        from tests.test_sim import _director

        self.d = _director()
        self.d.clock = SimClock(start=NOW)
        self.deltas, self.met, self.mems = [], [], []
        s = self.d.social

        async def apply_delta(a, b, fam, aff, note):
            self.deltas.append((a, b, fam, note))

        async def mark_met(a, b, ts):
            self.met.append((a, b))

        async def add_memory(pid, ts, text, about, importance=5, kind="event"):
            self.mems.append((pid, text, importance, kind))
            return MemoryRec(ts, text, about, importance, kind)

        s.apply_delta, s.mark_met, s.add_memory = apply_delta, mark_met, add_memory

        class Llm:
            async def summarize(_, transcript, roster):
                return summary

        self.d.llm = Llm()

    def thread(self, lines, span=None):
        t = ThreadState(id=1, channel="inside-tables", kind="chat", started=NOW, members=[], ever={"p0": None, "p1": None},
                        max_turns=8, lines=[("speech", s, "hi") for s in lines])
        t.span = span or {"p0": [0, None], "p1": [0, None]}
        return t


def test_strangers_who_share_a_conversation_are_recorded_even_when_the_summary_fails():
    from app.agents.memory import wrap_up

    w = _Wrap(summary=None)
    asyncio.run(wrap_up(w.d, w.thread(["p0", "p1"])))  # two lines: too short to summarize, long enough to meet
    assert w.deltas == [("p0", "p1", 6, "First met Wednesday Oct 21 at the inside tables by the front windows")]
    assert w.met == [("p0", "p1")]
    assert sorted((p, t) for p, t, _, _ in w.mems) == [
        ("p0", "Met P1 for the first time at the inside tables by the front windows."),
        ("p1", "Met P0 for the first time at the inside tables by the front windows."),
    ]
    assert all(imp == 6 for _, _, imp, _ in w.mems)


def test_one_shared_line_is_not_a_meeting_and_friends_are_not_strangers():
    from app.agents.memory import first_meetings

    w = _Wrap()
    brief = w.thread(["p0", "p1"], span={"p0": [0, None], "p1": [1, None]})  # p1 only there for the last line
    assert first_meetings(w.d, brief) == []
    full = w.thread(["p0", "p1", "p0"])
    assert [(a, b) for a, b, _ in first_meetings(w.d, full)] == [("p0", "p1")]
    w.d.social.rels[("p0", "p1")] = RelState(familiarity=20)
    assert first_meetings(w.d, full) == []
    w.d.social.rels[("p0", "p1")] = RelState(met_at=NOW)
    assert first_meetings(w.d, full) == []


def test_summary_that_covers_the_meeting_is_not_duplicated():
    from app.agents.memory import wrap_up

    summary = {
        "memories": [{"person": "P0", "text": "P1 seems nice and likes hockey.", "about": ["P1"], "importance": 3,
                      "followup": "Ask P1 about hockey"}],
        "relationships": [{"a": "P0", "b": "P1", "familiarity_delta": 4, "affinity_delta": 2, "note": ""}],
    }
    w = _Wrap(summary)
    asyncio.run(wrap_up(w.d, w.thread(["p0", "p1", "p0", "p1"])))
    texts = {(p, t) for p, t, _, _ in w.mems}
    assert ("p0", "P1 seems nice and likes hockey.") in texts
    assert ("p0", "Ask P1 about hockey") in texts and ("p1", "Met P0 for the first time at the inside tables by the front windows.") in texts
    assert not any(p == "p0" and t.startswith("Met P1") for p, t in texts)  # the summary already covered p0's side
    assert w.mems[0][2] == 6  # a first impression is never minor
    assert w.deltas == [("p0", "p1", 4, "")]  # the summary's relationship stands; no second +6
    assert w.met == [("p0", "p1")]


# ---------------------------------------------------------------- the turn


def test_excuse_leaves_the_chat_but_not_the_taproom():
    from tests.test_sim import _chat, _scene_director

    d = _scene_director()
    posts, departed = [], []

    async def post(channel, text, speaker=None, kind="speech", thread=None, thought=None):
        posts.append(text)

    async def depart(p):
        departed.append(p.id)

    d.post, d.depart = post, depart
    t = _chat(False)
    t.excuse["p0"] = "You need to use the restroom. Say so naturally and excuse yourself."
    p = d.people["p0"]
    p.need, p.need_at, p.thread_id = "restroom", NOW, t.id
    d.threads[t.id] = t
    utt = type("U", (), {"action": "none", "target": "", "say": "x"})()
    asyncio.run(d.apply_action(t, p, utt, forced_leave=False))
    assert "p0" not in t.members and not departed and p.present
    assert posts == ["P0 excuses themselves to use the restroom."]
    assert p.free_since > d.clock.now() and p.need == "" and "p0" not in t.excuse


def test_scene_carries_state_room_and_own_lines():
    from app.agents.agent import build_turn

    from tests.test_sim import _chat, _scene_director

    d = _scene_director()
    d.clock = SimClock(start=NOW)
    d.persona_text["p0"] = ""
    p, q = d.people["p0"], d.people["p1"]
    p.reason, p.drinks, p.buzz = "catch_up", 2, 0.3
    q.arrived_at, q.gap_days = NOW - timedelta(minutes=10), 9
    d.social.rels[("p0", "p1")] = RelState(kind="friend", familiarity=60)
    t = _chat(False)
    ctx = build_turn(d, t, p, False).context
    assert "Right now: hoping to catch up with friends" in ctx and "feeling it a little" in ctx
    assert "The taproom is quiet." in ctx and "Trivia is going at the inside tables." in ctx
    assert "P1 just got here and you haven't seen them in 9 days" in ctx
    t.lines = [("speech", "p0", "so anyway"), ("speech", "p1", "yeah")]
    ctx = build_turn(d, t, p, False).context
    assert "P0 (you): so anyway" in ctx and "P1: yeah" in ctx


def test_regulars_get_the_usual_from_the_bartender():
    from app.agents.agent import _register_note

    g = _p(drink="Fallforge")
    g.gap_days = 6
    note = _register_note(NOW, g, {"n": 7, "last": NOW.isoformat()})
    assert "regular (visit number 7, last here 6 days ago); their usual is Fallforge" in note
    assert "regular" not in _register_note(NOW, g, {"n": 2})


def test_sanitize_accepts_excuse_and_known_moods_only():
    from app.agents.agent import sanitize
    from app.llm.types import Utterance

    u = sanitize(Utterance(say="brb", action="excuse", mood="down"), _p())
    assert (u.action, u.mood) == ("excuse", "down")
    u = sanitize(Utterance(say="brb", action="teleport", mood="ecstatic"), _p())
    assert (u.action, u.mood) == ("none", "")


# ---------------------------------------------------------------- the room


def test_environment_is_deterministic_per_date():
    a, b = datetime(2026, 11, 1, 12, 30), datetime(2026, 11, 1, 16, 0)
    assert environment.weather(a) == environment.weather(b)
    assert environment.game_on(a) == environment.game_on(b)
    g = environment.game_on(a)  # a Sunday in season
    assert g is None or (g.team == "Vikings" and g.start.hour == 12)
    for day in range(30):
        g = environment.game_on(datetime(2026, 10, 1) + timedelta(days=day))
        if g:
            us, them = environment.score(g, g.start + timedelta(minutes=environment.GAME_MINUTES))
            assert us + them > 0
            assert environment.score(g, g.start - timedelta(minutes=1)) == (0, 0)


def test_new_plays_are_reported_once():
    g = next(g for day in range(60) if (g := environment.game_on(datetime(2026, 10, 1) + timedelta(days=day))))
    start, end = g.start - timedelta(minutes=1), g.start + timedelta(minutes=environment.GAME_MINUTES)
    mid = g.start + timedelta(minutes=90)
    first, second = environment.new_plays(g, start, mid), environment.new_plays(g, mid, end)
    assert len(first) + len(second) == len(g.plays)
    assert environment.new_plays(g, end, end + timedelta(hours=1)) == []


def test_room_line_covers_weather_noise_and_trivia():
    line = environment.room_line(NOW, 3)
    assert "Outside it is" in line and "quiet" in line and "Trivia" in line
    assert "Trivia" not in environment.room_line(NOW.replace(hour=15), 3)
    assert environment.noise(30) == "loud and packed" and environment.is_loud(14) and not environment.is_loud(5)
    assert environment.fan_of("Vikings", {"interests": ["Vikings football"]})
    assert environment.fan_of("Timberwolves", {"traits": ["wolves die-hard"]})
    assert not environment.fan_of("Vikings", {"interests": ["knitting"]})

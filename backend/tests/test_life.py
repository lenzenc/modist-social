import asyncio
import random
import re
from datetime import date, datetime, timedelta

from app.sim import life
from app.sim.life import LifeEventRec, catalog

DAY = date(2026, 10, 21)  # a Wednesday
NOW = datetime(2026, 10, 21, 17, 0)
PERSONA = {"age": 34, "job": "nurse", "interests": ["climbing", "true crime"], "big5": {"n": 3}, "stay": 60}


def _event(kind, occurred=DAY, seed=1):
    return life.make(catalog()[kind], PERSONA, occurred, random.Random(seed))


# ---------------------------------------------------------------- the catalog


def test_catalog_is_consistent():
    cat = catalog()
    assert len(cat) >= 30
    for kind, e in cat.items():
        assert {"cat", "weight", "text", "keys", "days", "mood", "visit", "stay", "drinks"} <= set(e), kind
        assert e["cat"] in life.IMPORTANCE, kind
        assert e["days"] > 0 and e["keys"], kind
        for n in e.get("then", []):
            assert n["kind"] in cat, (kind, n)
            assert cat[n["kind"]]["weight"] == 0, f"{n['kind']} only ever follows an arc"
            assert 0 < n["after"][0] <= n["after"][1] < e["days"] + 3, kind
    assert any(e["weight"] > 0 for e in cat.values())


def test_templates_fill_cleanly_without_pronouns():
    for kind, e in catalog().items():
        text = life.fill(e["text"], PERSONA, DAY, random.Random(0))
        assert "{" not in text and "}" not in text, kind
        assert not re.search(r"\b(he|she|his|her|him|hers)\b", text.lower()), (kind, text)
    assert life.fill("a thing {day}, since {since}", PERSONA, DAY, random.Random(0)) == "a thing on Wednesday, since Wednesday"


# ---------------------------------------------------------------- rolling


def test_a_day_always_rolls_the_same():
    assert life.roll_day("p1", PERSONA, [], DAY) == life.roll_day("p1", PERSONA, [], DAY)


def test_roll_rate_and_limits_over_a_long_stretch():
    events: list[LifeEventRec] = []
    for i in range(600):
        day = DAY + timedelta(days=i)
        events += life.roll_day("p1", PERSONA, events, day)
        live = life.active(events, datetime.combine(day, datetime.min.time()).replace(hour=9))
        assert len(live) <= life.MAX_ACTIVE
        assert len({e.kind for e in live}) == len(live)  # never the same thing twice at once
    assert 0.05 < len(events) / 600 < 0.25


def test_the_young_do_not_get_events_meant_for_older_people():
    kinds = set()
    young = {**PERSONA, "age": 22}
    for i in range(3000):
        kinds |= {e.kind for e in life.roll_day(f"p{i}", young, [], DAY + timedelta(days=i))}
    assert kinds and not kinds & {"kid_sick", "parent_unwell", "anniversary"}


def test_follow_on_only_events_are_never_rolled_directly():
    kinds = set()
    for i in range(3000):
        kinds |= {e.kind for e in life.roll_day(f"p{i}", PERSONA, [], DAY + timedelta(days=i))}
    assert not kinds & {k for k, e in catalog().items() if e["weight"] == 0}


def test_an_arc_resolves_once_when_due():
    e = _event("job_interview")
    assert e.next_kind in {"got_the_job", "didnt_get_the_job"}
    assert e.started_at + timedelta(days=2) <= e.due_at <= e.started_at + timedelta(days=4)
    assert life.due_followups([e], PERSONA, e.due_at - timedelta(hours=1), random.Random(0)) == []
    out = life.due_followups([e], PERSONA, e.due_at + timedelta(hours=1), random.Random(0))
    assert [x.kind for x in out] == [e.next_kind] and e.resolved
    assert e.ends_at <= e.due_at + timedelta(hours=1)  # the worry ends when the news comes
    assert life.due_followups([e], PERSONA, e.due_at + timedelta(days=1), random.Random(0)) == []


# ---------------------------------------------------------------- effects


def test_effects_fade_from_full_strength_to_nothing():
    e = _event("bad_cold")
    start, mid, end = e.started_at, e.started_at + (e.ends_at - e.started_at) / 2, e.ends_at - timedelta(seconds=1)
    assert life.freshness(e, start) == 1.0 and 0.45 < life.freshness(e, mid) < 0.55 and life.freshness(e, e.ends_at) == 0.0
    assert life.visit_mult([e], start) < 0.4 < 0.5 < life.visit_mult([e], mid) < life.visit_mult([e], end) <= 1.0
    assert life.mood_shift([e], start) < life.mood_shift([e], mid) < 0
    assert life.stay_mult([e], start) < 1.0
    assert life.drink_delta([e], start) == -1 and life.drink_delta([e], e.ends_at) == 0
    assert life.visit_mult([e], e.ends_at + timedelta(days=1)) == 1.0 and life.mood_shift([e], e.ends_at) == 0.0


def test_good_news_brings_people_in_and_sets_the_mood():
    e = _event("got_the_job")
    assert life.visit_mult([e], e.started_at) > 1.3 and life.mood_shift([e], e.started_at) > 0.3
    assert life.reason_override([e], e.started_at) == "catch_up"
    assert life.reason_override([e], e.ends_at - timedelta(minutes=1)) == ""  # too faded to decide why they came


def test_money_trouble_means_paying_by_card():
    e = _event("car_trouble")
    assert life.pay_override([e], e.started_at) == "card"
    assert life.pay_override([_event("recovered")], NOW) == ""


def test_effects_combine_and_stay_in_bounds():
    evs = [_event("bad_cold"), _event("kid_sick"), _event("parent_unwell")]
    t = datetime.combine(DAY, datetime.min.time()).replace(hour=9)
    assert 0.15 <= life.visit_mult(evs, t) < 0.35 and -0.8 <= life.mood_shift(evs, t) <= -0.5
    assert life.stay_mult(evs, t) >= 0.5


# ---------------------------------------------------------------- in the scene


def test_on_mind_shows_the_freshest_two():
    old, mid, new = _event("bad_cold", DAY - timedelta(days=2)), _event("car_trouble", DAY - timedelta(days=1)), _event("windfall")
    line = life.on_mind([old, mid, new], NOW)
    assert new.text in line and mid.text in line and old.text not in line
    assert "fresh" in line.split(new.text)[0] and "first line or two" in line  # raw news is meant to come up early
    stale = _event("car_trouble", DAY - timedelta(days=4))  # most of the way through its five days
    calm = life.on_mind([stale], NOW)
    assert "On your mind lately:" in calm and "fresh" not in calm and "first line or two" not in calm
    assert life.on_mind([], NOW) == "" and life.on_mind([_event("bad_cold", DAY - timedelta(days=30))], NOW) == ""


def test_mentioned_uses_the_events_own_words():
    e = _event("car_trouble")
    assert life.mentioned("Ugh, the transmission is shot.", [e])
    assert life.mentioned("my brother drove me to the game", [e]) is False
    assert life.mentioned("Honestly the Twins need pitching.", [e]) is False
    assert life.mentioned("laid off last week", [_event("lost_the_job")])  # multi-word keys


def test_keywords_do_not_collide_with_ordinary_taproom_talk():
    common = {"flight", "round", "tab", "bill", "cold", "work", "game", "show", "new", "friend", "job", "money", "tired",
              "sleep", "back", "test", "dinner", "plans", "gift", "dog", "cat", "pet", "family", "beer", "drink", "boss"}
    for kind, e in catalog().items():
        assert not {k.lower() for k in e["keys"]} & common, kind
    ordinary = "Can I get a taster flight? Put it on my tab. A cold one, and the next round is on me; my dog loves this place."
    assert not life.mentioned(ordinary, [life.make(e, PERSONA, DAY, random.Random(0)) for e in catalog().values()])


def test_continuity_counts_visits_where_it_came_up():
    e = life.make(catalog()["car_trouble"], PERSONA, DAY, random.Random(1))
    e.ends_at = datetime.combine(DAY, datetime.min.time()) + timedelta(days=20)
    names = {"p1": "Pat"}
    # eight visits on eight different days, and the car comes up in four of them
    lines = [(DAY + timedelta(days=i), "p1", t) for i in range(8) for t in ("so anyway", "good beer", "the car repair was brutal" if i < 4 else "yep")]
    out = life.continuity(lines, {"p1": [e]}, names)
    assert (out["visits"], out["mentioned"], out["rate"], out["band"]) == (8, 4, 50, "green")
    assert out["events"][0]["person"] == "Pat" and out["events"][0]["came_up"]
    assert life.continuity(lines[:6], {"p1": [e]})["rate"] is None  # too few visits to judge
    assert life.continuity(lines, {})["visits"] == 0


# ---------------------------------------------------------------- the director


def _arrive(d, p, events, seed=7):
    from app.sim.clock import SimClock

    d.clock = SimClock(start=datetime(2026, 10, 21, 16, 0))
    d.rng = random.Random(seed)
    d.life = {p.id: events}
    d.check_in(p)
    return p


def _director_with(persona):
    from tests.test_sim import _director

    d = _director()
    d.people["p0"].persona = {**PERSONA, "pay": "tab", **persona}
    return d, d.people["p0"]


def test_arriving_with_a_bad_cold_means_a_shorter_quieter_visit():
    d, p = _director_with({})
    well = _arrive(d, p, [])
    well_stay, well_mood, well_goal = well.leave_at - well.arrived_at, well.mood, well.drink_goal
    cold = _event("bad_cold", datetime(2026, 10, 21).date())
    _arrive(d, p, [cold])
    assert p.leave_at - p.arrived_at < well_stay
    assert p.mood < well_mood and p.drink_goal <= well_goal and p.drink_goal >= 1
    assert p.reason == "solo" and p.pay_mode == "tab"  # a cold is not about money


def test_good_news_sets_the_reason_and_money_trouble_the_card():
    d, p = _director_with({})
    _arrive(d, p, [_event("got_the_job")])
    assert p.reason == "catch_up"
    _arrive(d, p, [_event("car_trouble")])
    assert p.pay_mode == "card"


def test_the_guest_sees_what_is_on_their_mind_and_nobody_else_does():
    from app.agents.agent import build_turn

    from tests.test_sim import _chat, _scene_director

    d = _scene_director()
    d.persona_text["p0"] = d.persona_text["p1"] = ""
    d.life = {"p0": [_event("car_trouble", d.clock.now().date())]}
    mine = build_turn(d, _chat(False), d.people["p0"], False)
    assert "On your mind, and fresh:" in mine.context and "car" in mine.life
    theirs = build_turn(d, _chat(False, tid=2), d.people["p1"], False)
    assert "On your mind" not in theirs.context and theirs.life == ""


def test_polish_replaces_the_text_only_with_something_usable():
    from tests.test_sim import _director

    class Llm:
        def __init__(self, reply):
            self.reply = reply

        async def polish(self, who, event):
            return self.reply

    d = _director()
    p = d.people["p0"]
    p.persona = PERSONA
    for reply, expect in (('"had the Corolla\'s transmission finally give out on Tuesday."', "had the Corolla's transmission finally give out on Tuesday"),
                          ("two\nlines", None), ("", None), (None, None), ("x" * 300, None),
                          ("P0 X, 34, has been fighting a cold", None), ("got a cold that wrecked her week", None),
                          ("spent Tuesday under a blanket", "spent Tuesday under a blanket")):
        d.llm = Llm(reply)
        e = _event("car_trouble")
        before = e.text
        asyncio.run(d.polish_event(p, e))
        assert e.text == (expect or before)


def test_the_mock_leaves_the_template_alone_and_brings_it_up_sometimes():
    from app.llm.mock import MockLLM
    from app.llm.types import TurnRequest

    assert asyncio.run(MockLLM().polish("Pat", "x")) is None
    req = TurnRequest(person_id="p0", person_name="P0", world="", persona="", context="", life="car broke down on Tuesday")
    said = {asyncio.run(MockLLM().speak(req)).say for _ in range(60)}
    assert "Ugh, car broke down on Tuesday." in said

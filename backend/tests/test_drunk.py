import asyncio
import random
from datetime import datetime, timedelta

from app.llm.mock import MockLLM
from app.llm.types import TurnRequest
from app.sim import drunk, human, menu
from app.sim.clock import SimClock
from app.sim.state import MemoryRec, PersonState, ThreadState
from tests.test_sim import NOW, _chat, _director, _scene_director, _scene_for


def _p(buzz=0.0, drinks=0, **kw):
    p = PersonState(id="p0", name="Pat X", short="Pat", display="Pat X", role="patron", pronouns="they/them",
                    color="#000", persona=kw.pop("persona", {"age": 30}), present=True)
    p.buzz, p.drinks = buzz, drinks
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _run(coro):
    return asyncio.run(coro)


def _posting(d):
    """Replace the director's post with a recorder so nothing touches the database."""
    posts = []

    async def post(channel, text, speaker=None, kind="speech", thread=None, thought=None):
        posts.append(text)

    d.post = post
    return posts


# ---------------------------------------------------------------- pure rules


def test_tiers_follow_buzz():
    assert [drunk.tier(b) for b in (0.0, 0.24, 0.25, 0.5, 0.75, 1.0)] == ["sober", "sober", "tipsy", "drunk", "wasted", "wasted"]


def test_strong_drinks_hit_harder_and_water_not_at_all():
    assert drunk.strength(0) == 0 and drunk.strength(None) == 1.0
    assert drunk.strength(16.5) > drunk.strength(8) > drunk.strength(4.5) > 0
    assert drunk.strength(16.5) == drunk.STRENGTH[1] and drunk.strength(1) == drunk.STRENGTH[0]
    persona = {"age": 30}
    assert human.add_drink(0.0, persona, drunk.strength(menu.abv("Stave Robber Special Reserve"))) > human.add_drink(0.0, persona, drunk.strength(menu.abv("Fallforge")))
    assert human.add_drink(0.3, persona, drunk.strength(menu.abv(menu.WATER))) == 0.3


def test_water_is_on_the_menu_but_never_a_pick():
    assert menu.match("just a water please") == menu.WATER
    assert menu.match("Fallforge") == "Fallforge"
    assert menu.WATER not in menu.names()
    assert menu.abv(menu.WATER) == 0.0


def test_service_slows_then_cuts():
    assert drunk.service(_p(0.3)) == "pour"
    assert drunk.service(_p(0.55)) == "slow"
    assert drunk.service(_p(0.8)) == "cut"
    assert drunk.service(_p(0.1, drinks=drunk.CUT_DRINKS)) == "cut"
    assert drunk.service(_p(0.1, cut_off=True)) == "cut"


def test_sober_never_asks_for_water_and_the_driver_asks_more():
    rng = random.Random(1)
    assert not any(drunk.wants_water(_p(0.3), rng) for _ in range(200))
    plain = sum(drunk.wants_water(_p(0.55), rng) for _ in range(500))
    driver = sum(drunk.wants_water(_p(0.55, persona={"quirk": "always the designated driver"}), rng) for _ in range(500))
    assert 0 < plain < driver


def test_water_speeds_up_sobering():
    now = NOW
    dry, wet = _p(0.6), _p(0.6, on_water_until=now + timedelta(minutes=20))
    human.tick(dry, 60, drunk.decay_mult(dry, now))
    human.tick(wet, 60, drunk.decay_mult(wet, now))
    assert wet.buzz < dry.buzz
    assert wet.peak_buzz == wet.buzz


def test_hints_scale_with_the_tier():
    assert drunk.speech_hint(0.1) == ""
    assert "slurred" in drunk.speech_hint(0.55) and "slurring" in drunk.speech_hint(0.9)
    assert "Cut them off" in drunk.bartender_note(_p(0.9, drinks=5), "cut")
    assert "Slow them down" in drunk.bartender_note(_p(0.55, drinks=3), "slow")
    assert drunk.bartender_note(_p(0.1), "pour") == ""


def test_ride_home():
    rng = random.Random(0)
    sober_friend = _p(0.0)
    sober_friend.id = "p1"
    assert drunk.ride_home(_p(0.1), [sober_friend], rng) is None
    assert drunk.ride_home(_p(0.8), [sober_friend], rng) == ("driver", "p1")
    assert drunk.ride_home(_p(0.8), [], rng) == ("rideshare", None)
    also_drunk = _p(0.6)
    also_drunk.id = "p1"
    assert drunk.ride_home(_p(0.8), [also_drunk], rng) == ("rideshare", None)


def test_record_only_for_drunk_visits_and_regret_names_what_happened():
    assert drunk.record(_p(peak_buzz=0.4), "2026-10-19", "") is None
    p = _p(peak_buzz=0.8, drinks=6, cut_off=True, slops=["dropped a glass"])
    h = drunk.record(p, "2026-10-19", "rideshare")
    text = drunk.regret_text(h)
    for needle in ("6 drinks", "cut off", "dropped a glass", "rideshare"):
        assert needle in text


def test_consequences_scorecard():
    quiet = {"cut_off": False, "slops": [], "water": False, "ride": ""}
    busy = {**quiet, "cut_off": True}
    assert drunk.consequences([busy, busy])["band"] == "none"
    assert drunk.consequences([busy] * 4)["band"] == "green"
    assert drunk.consequences([quiet] * 4)["band"] == "red"
    assert drunk.consequences([busy, quiet, quiet, quiet])["cut_offs"] == 1


# ---------------------------------------------------------------- the director


def test_cutting_off_swaps_the_beer_for_water_and_sends_them_home():
    d = _director()
    d.clock = SimClock(start=NOW)
    posts = _posting(d)
    charged = []

    async def charge(p, drink, bt, t):
        charged.append(drink)

    d.charge = charge
    guest = d.people["p0"]
    guest.present, guest.buzz, guest.drinks, guest.drink_goal = True, 0.85, 5, 7
    guest.leave_at = NOW + timedelta(hours=2)
    t = ThreadState(id=1, channel="bar", kind="order", started=NOW, members=["p0", "b1"], ever={"p0": None, "b1": None},
                    max_turns=3, again=True, ordered=True, order_drink="Fallforge")
    _run(d.finish_order(t))
    assert charged == [menu.WATER]
    assert guest.cut_off and guest.drink_goal == guest.drinks and guest.next_drink_at is None
    assert guest.leave_at <= NOW + timedelta(minutes=drunk.CUT_LEAVE_MIN[1])
    assert any("cuts Pat" in x or "cuts P0" in x for x in posts)


def test_a_sober_guest_is_served_normally():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    charged = []

    async def charge(p, drink, bt, t):
        charged.append(drink)

    d.charge = charge
    guest = d.people["p0"]
    guest.present, guest.buzz, guest.drinks = True, 0.2, 1
    t = ThreadState(id=1, channel="bar", kind="order", started=NOW, members=["p0", "b1"], ever={"p0": None, "b1": None},
                    max_turns=3, again=True, ordered=True, order_drink="Fallforge")
    _run(d.finish_order(t))
    assert charged == ["Fallforge"] and not guest.cut_off


def test_water_is_free_and_counts_as_a_round():
    d = _director()
    d.clock = SimClock(start=NOW)
    posts = _posting(d)
    guest = d.people["p0"]
    guest.present, guest.buzz, guest.drinks, guest.drink_goal = True, 0.55, 3, 5
    guest.leave_at = NOW + timedelta(hours=2)
    t = ThreadState(id=1, channel="bar", kind="order", started=NOW, members=["p0", "b1"], ever={"p0": None, "b1": None}, max_turns=3)
    _run(d.charge(guest, menu.WATER, "b1", t))
    assert guest.drink == menu.WATER and guest.drinks == 3 and guest.drink_goal == 4
    assert guest.on_water_until > NOW and any("gets a water" in x for x in posts)


def test_the_drunk_make_a_mess():
    d = _director()
    d.clock = SimClock(start=NOW)
    d.rng = random.Random(3)
    posts = _posting(d)
    guest = d.people["p0"]
    guest.present, guest.location, guest.buzz, guest.drink = True, "patio", 0.9, "Fallforge"
    _run(d.sloppy_step(600))
    assert guest.drink == "" and len(guest.slops) == 1 and len(posts) == 1
    sober = d.people["p1"]
    sober.present, sober.location, sober.buzz, sober.drink = True, "patio", 0.1, "Fallforge"
    _run(d.sloppy_step(600))
    assert sober.drink == "Fallforge"


def test_an_overshare_is_queued_for_a_chat_not_a_drink():
    d = _director()
    d.clock = SimClock(start=NOW)
    d.rng = random.Random(5)
    _posting(d)
    guest = d.people["p0"]
    guest.present, guest.location, guest.buzz, guest.thread_id = True, "inside-tables", 0.9, 1
    d.threads[1] = _chat(False)
    for _ in range(40):
        _run(d.sloppy_step(600))
        if guest.overshare_pending:
            break
    assert guest.overshare_pending and not guest.slops


def test_leaving_drunk_gets_a_ride_and_a_hangover_that_becomes_a_memory():
    d = _director()
    d.clock = SimClock(start=NOW)
    posts = _posting(d)
    guest = d.people["p0"]
    guest.present, guest.location, guest.buzz, guest.peak_buzz, guest.drinks = True, "bar", 0.8, 0.9, 6
    guest.cut_off, guest.slops, guest.overshared_with = True, ["said something you shouldn't have"], {"p1"}
    guest.visited_day = "2026-10-19"
    _run(d.depart(guest))
    assert any("rideshare" in x for x in posts) and not guest.present
    h = d.hangovers["p0"]
    assert h["peak"] == "wasted" and h["cut_off"] and not h["written"]
    assert d.drunk_log and d.drunk_log[-1]["pid"] == "p0"

    mems = []

    async def add_memory(pid, ts, text, about, importance=5, kind="event"):
        mems.append((pid, text, importance, kind, about))
        return MemoryRec(ts, text, about, importance, kind)

    d.social.add_memory = add_memory
    _run(d.morning_after(NOW + timedelta(days=1), "2026-10-20"))
    assert mems[0][0] == "p0" and "overdid it" in mems[0][1] and mems[0][2] == drunk.MEMORY_IMPORTANCE and mems[0][4] == ["p1"]
    assert mems[1][3] == "followup" and "P1" in mems[1][1]
    _run(d.morning_after(NOW + timedelta(days=1), "2026-10-20"))
    assert len(mems) == 2  # written once


def test_a_friend_who_stayed_sober_drives():
    d = _director()
    d.clock = SimClock(start=NOW)
    posts = _posting(d)
    from app.sim.state import PartyState

    d.parties[1] = PartyState(id=1, members=["p0", "p1"], leader="p0", area="bar", tables=[])
    a, b = d.people["p0"], d.people["p1"]
    a.present, a.party, a.buzz, a.peak_buzz, a.location = True, 1, 0.8, 0.8, "bar"
    b.present, b.party, b.buzz, b.location = True, 1, 0.0, "bar"
    b.leave_at = NOW + timedelta(hours=2)
    _run(d.depart(a))
    assert any("P1 drives" in x for x in posts)
    assert b.leave_at < NOW + timedelta(minutes=6)


def test_the_morning_after_is_a_slower_night():
    d = _director()
    d.clock = SimClock(start=NOW + timedelta(days=1))
    p = d.people["p0"]
    d.hangovers["p0"] = {"day": "2026-10-19", "written": True}
    d.rng = random.Random(0)
    d.check_in(p)
    assert "p0" not in d.hangovers and p.peak_buzz == 0.0 and not p.cut_off
    d.hangovers["p0"] = {"day": "2026-10-20", "written": False}
    p.present = False
    d.check_in(p)
    assert "p0" in d.hangovers  # not yet remembered, so not yet felt


# ---------------------------------------------------------------- what the model is told


def test_scene_tells_the_drunk_to_slur_and_the_sober_not():
    d = _scene_director()
    p = d.people["p0"]
    assert "slurring" not in _scene_for(d, _chat(False, lines=[("speech", "p1", "hi")]), p).context
    p.buzz = 0.9
    ctx = _scene_for(d, _chat(False, lines=[("speech", "p1", "hi")]), p).context
    assert "slurring" in ctx and "very drunk" in ctx


def test_overshare_reaches_the_scene_once_and_is_recorded():
    d = _scene_director()
    p = d.people["p0"]
    p.buzz, p.overshare_pending = 0.9, True
    t = _chat(False, lines=[("speech", "p1", "hi")])
    assert "filter is gone" in _scene_for(d, t, p).context
    assert not p.overshare_pending and p.overshared_with == {"p1"} and p.slops
    assert "filter is gone" not in _scene_for(d, t, p).context


def test_bartender_is_told_to_cut_off_a_drunk_guest():
    d = _scene_director()
    b, g = d.people["b1"], d.people["p0"]
    g.buzz, g.drinks = 0.9, 5
    t = ThreadState(id=2, channel="bar", kind="order", started=NOW, members=["p0", "b1"], ever={"p0": None, "b1": None}, max_turns=3, again=True)
    req = _scene_for(d, t, b)
    assert "Cut them off" in req.context and req.serve == "cut"
    g.buzz, g.drinks = 0.1, 1
    req = _scene_for(d, t, b)
    assert "Cut them off" not in req.context and req.serve == "pour"


# ---------------------------------------------------------------- mock mode


def _speak(**kw):
    base = dict(person_id="p0", person_name="Pat", world="", persona="", context="")
    return asyncio.run(MockLLM().speak(TurnRequest(**{**base, **kw})))


def test_mock_bartender_cuts_off_and_guest_takes_water():
    cut = {_speak(kind="order", is_bartender=True, serve="cut", last_line="Another Fallforge.").say for _ in range(30)}
    assert cut and all("water" in s.lower() or "last one" in s.lower() or "enough" in s.lower() for s in cut)
    u = _speak(kind="order", serve="cut", last_line="no more")
    assert u.drink == menu.WATER
    assert _speak(kind="order", water=True).drink == menu.WATER
    assert _speak(kind="order").drink != menu.WATER


def test_mock_drunk_talk_slurs():
    seen = {_speak(kind="chat", last_line="hey", drunk="drunk", buzz=0.6).say for _ in range(120)}
    assert any("sh" in s.lower() for s in seen)

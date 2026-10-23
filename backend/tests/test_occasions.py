import asyncio
import random
from datetime import date, datetime, timedelta

import pytest

from app.llm.mock import MockLLM
from app.sim import menu, occasions, taste
from app.sim.clock import SimClock
from app.sim.social import pair_key
from app.sim.state import RelState, Waiting
from tests.test_sim import NOW, _chat, _scene_director, _scene_for

D0 = date(2026, 10, 1)


def _run(coro):
    return asyncio.run(coro)


def _day(pred, n=400):
    """The first date from D0 on that satisfies pred."""
    return next(D0 + timedelta(days=i) for i in range(n) if pred(D0 + timedelta(days=i)))


@pytest.fixture(autouse=True)
def clean_board():
    menu.set_released([])
    yield
    menu.set_released([])


def _room():
    """Two guests and a bartender, with the database-touching calls recorded."""
    d = _scene_director()
    posts, memories = [], []

    async def post(channel, text, speaker=None, kind="speech", thread=None, thought=None):
        posts.append(text)

    async def add_memory(pid, ts, text, about, importance=5, kind="event", **kw):
        memories.append((pid, text, importance, kind))

    async def apply_delta(a, b, fam, aff, note):
        pass

    d.post, d.social.add_memory, d.social.apply_delta = post, add_memory, apply_delta
    d.posts, d.memories = posts, memories
    return d


def _friends(d, a="p0", b="p1"):
    d.social.rels[pair_key(a, b)] = RelState(familiarity=60, affinity=20)


# ---------------------------------------------------------------- rhythm and holidays


def test_the_weekend_is_busier_than_a_tuesday():
    tuesday, saturday = datetime(2026, 10, 20, 19), datetime(2026, 10, 24, 19)
    assert occasions.crowd(tuesday) < 1.0 < occasions.crowd(saturday)


def test_holidays_land_on_the_right_nights():
    assert occasions.holiday(date(2026, 10, 31)).key == "halloween"
    assert occasions.holiday(date(2026, 11, 25)).key == "thanksgiving_eve"  # Thanksgiving 2026 is Nov 26
    assert occasions.holiday(date(2026, 12, 31)).key == "nye"
    assert occasions.holiday(date(2028, 2, 14)).key == "valentines"
    assert occasions.holiday(date(2027, 2, 14)).key == "superbowl"  # the second Sunday of February
    assert occasions.holiday(date(2026, 10, 20)) is None
    halloween = datetime(2026, 10, 31, 19)
    assert occasions.crowd(halloween) == pytest.approx(occasions.DAY_PULSE[5] * 1.25)
    assert occasions.mood_shift(halloween) > 0 == occasions.mood_shift(datetime(2026, 10, 20, 19))


def test_music_parties_and_incidents_are_set_by_the_date():
    days = [D0 + timedelta(days=i) for i in range(120)]
    assert [occasions.band_for(d) for d in days] == [occasions.band_for(d) for d in days]
    assert [occasions.party_for(d) for d in days] == [occasions.party_for(d) for d in days]
    assert [occasions.incident_for(d) for d in days] == [occasions.incident_for(d) for d in days]
    assert any(occasions.band_for(d) for d in days) and any(occasions.party_for(d) for d in days)
    assert any(occasions.incident_for(d) for d in days)
    assert all(occasions.band_for(d).start.weekday() in (4, 5) for d in days if occasions.band_for(d))
    assert all(not occasions.party_for(d) or d.weekday() in (3, 4, 5) for d in days)


def test_a_band_quiets_the_jukebox_and_shows_in_the_room_line():
    d = _day(lambda x: occasions.band_for(x) is not None)
    band = occasions.band_for(d)
    during = band.start + timedelta(minutes=30)
    assert occasions.band_on(during) and occasions.music_off(during)
    assert not occasions.music_off(band.end + timedelta(minutes=1))
    assert any(band.name in bit for bit in occasions.room_bits(during, []))
    assert occasions.label(during, []) == f"Live music: {band.name}"
    assert occasions.label(datetime(2026, 10, 20, 19), []) == ""


# ---------------------------------------------------------------- birthdays


def test_a_birthday_is_stable_and_a_persona_can_set_it():
    assert occasions.birthday("p07", {}) == occasions.birthday("p07", {})
    assert occasions.birthday("p07", {"birthday": "03-09"}) == (3, 9)
    assert occasions.is_birthday("p07", {"birthday": "03-09"}, date(2027, 3, 9))
    spread = {occasions.birthday(f"p{i:02d}", {}) for i in range(30)}
    assert len(spread) > 20


def test_whose_birthday_it_is_follows_the_clock():
    d = _room()
    d.people["p0"].persona["birthday"] = "10-19"
    assert d.birthdays_today() == {"p0"}
    d.clock = SimClock(start=datetime(2026, 10, 20, 16))
    assert d.birthdays_today() == set()
    d.people["p0"].persona["birthday"] = "10-20"
    d.moved["p0"] = {"city": "Denver", "day": "2026-10-01"}
    assert d.birthdays_today() == set()  # whoever moved away doesn't turn up for it


def test_a_friend_buys_the_birthday_guest_a_round():
    d = _room()
    d.people["p0"].persona["birthday"] = "10-19"
    d.toast = {"p0": "birthday"}
    p0, p1 = d.people["p0"], d.people["p1"]
    for p in (p0, p1):
        p.location, p.arrived_at, p.free_since = "bar", NOW - timedelta(minutes=30), NOW - timedelta(minutes=10)
    _friends(d)
    orders = []

    async def request_order(p, party=None, treat=False):
        orders.append((p.id, party, treat))

    d.request_order = request_order
    d.bartenders_on = lambda: [d.people["b1"]]
    _run(d.toasts(NOW))
    assert orders == [("p1", ["p0"], True)] and d.toast == {}
    assert d.history[-1]["kind"] == "birthday" and "birthday" in d.memories[-1][1]
    assert "birthday" in d.day_events


def test_nobody_buys_before_the_guest_has_settled_in():
    d = _room()
    d.toast = {"p0": "birthday"}
    d.people["p0"].arrived_at = NOW - timedelta(minutes=2)
    _friends(d)
    d.request_order = lambda *a, **k: pytest.fail("too soon")
    _run(d.toasts(NOW))
    assert d.toast == {"p0": "birthday"}


# ---------------------------------------------------------------- new beers


def test_a_release_joins_the_board_and_the_tap_list_for_good():
    entry = occasions.release_pool()[0]
    assert entry["name"] not in menu.names()
    menu.set_released([entry])
    assert entry["name"] in menu.names() and entry["name"] in menu.render_tap_list()
    assert menu.match(f"a pint of {entry['name']}") == entry["name"] and menu.abv(entry["name"]) == entry["abv"]
    assert all("blurb" not in x for x in menu.drinks())


def test_releases_come_every_other_thursday_in_order():
    thursdays = [d for d in (D0 + timedelta(days=i) for i in range(60)) if occasions.release_due(d)]
    assert all(d.weekday() == 3 for d in thursdays) and 3 <= len(thursdays) <= 5
    assert all((b - a).days == 14 for a, b in zip(thursdays, thursdays[1:], strict=False))
    first = occasions.next_release([])
    assert occasions.next_release([{"name": first["name"], "day": "2026-10-22"}])["name"] != first["name"]
    assert occasions.release_tonight([{"name": first["name"], "day": "2026-10-22"}], datetime(2026, 10, 22, 18))["name"] == first["name"]
    assert occasions.release_tonight([{"name": first["name"], "day": "2026-10-22"}], datetime(2026, 10, 23, 18)) is None


def test_a_curious_guest_goes_for_the_new_beer_on_release_night():
    rec = taste.TasteRec()
    persona = {"age": 30, "beer": "nerd", "big5": {"o": 5}, "drink": "Fallforge"}
    picks = [taste.intend(rec, persona, "", random.Random(i), "2026-10-22", release="Lantern Light") for i in range(200)]
    wanted = [p for p in picks if p.drink == "Lantern Light"]
    assert 30 < len(wanted) < 140
    tried = taste.TasteRec(tried=["Lantern Light"])
    assert not any(taste.intend(tried, persona, "", random.Random(i), "2026-10-22", release="Lantern Light").drink == "Lantern Light" and
                   taste.intend(tried, persona, "", random.Random(i), "2026-10-22", release="Lantern Light").reason.startswith("it's the night")
                   for i in range(100))


def test_the_release_is_announced_once_and_enters_the_history():
    d = _room()
    d.clock = SimClock(start=datetime(2026, 10, 22, 18))
    d.released = [{"name": "Lantern Light", "day": "2026-10-22"}]
    menu.set_released([occasions.release_entry("Lantern Light")])
    now = d.clock.now()
    _run(d.calendar_step(now, "2026-10-22"))
    _run(d.calendar_step(now, "2026-10-22"))
    assert sum("Lantern Light" in p for p in d.posts) == 1
    assert [h["kind"] for h in d.history] == ["release"]


# ---------------------------------------------------------------- moving away


def test_a_farewell_is_rare_and_the_last_night_comes_days_after_the_news():
    plans = [occasions.roll_farewell(["a", "b"], D0, random.Random(i)) for i in range(400)]
    made = [p for p in plans if p]
    assert 5 < len(made) < 40
    assert all(5 <= (date.fromisoformat(p["night"]) - D0).days <= 8 for p in made)
    assert occasions.roll_farewell([], D0, random.Random(0)) is None
    plan = made[0]
    night = date.fromisoformat(plan["night"])
    assert [occasions.farewell_phase(plan, night + timedelta(days=k)) for k in (-1, 0, 1)] == ["announced", "tonight", "over"]
    assert occasions.farewell_phase(None, D0) == ""


def test_a_move_runs_from_the_news_to_a_quiet_goodbye():
    d = _room()
    _friends(d)
    plan = {"pid": "p0", "city": "Denver", "announced": "2026-10-19", "night": "2026-10-24"}
    _run(d.announce_move(plan, NOW))
    assert any(pid == "p1" and kind == "followup" and "Denver" in text for pid, text, _, kind in d.memories)
    assert any(pid == "p0" and "moving to Denver" in text for pid, text, _, _ in d.memories)
    d.farewell = plan
    last = datetime(2026, 10, 24, 20)
    d.clock = SimClock(start=last)
    _run(d.send_off(d.people["p0"], last))
    assert d.moved["p0"] == {"city": "Denver", "day": "2026-10-24"} and d.farewell is None
    assert d.history[-1]["kind"] == "farewell" and "Denver" in d.history[-1]["title"]
    assert any(pid == "p1" and imp == 8 for pid, _, imp, _ in d.memories)
    assert "farewell" in d.day_events


def test_a_plan_whose_night_passed_unseen_is_finished_quietly():
    d = _room()
    d.farewell = {"pid": "p0", "city": "Boise", "announced": "2026-10-01", "night": "2026-10-05"}
    d.clock = SimClock(start=datetime(2026, 10, 7, 12))
    _run(d.occasion_day(d.clock.now(), "2026-10-07"))
    assert d.moved.get("p0", {}).get("city") == "Boise" and "farewell" not in d.day_events


def test_the_last_night_keeps_the_leaver_longer_and_sets_a_toast():
    d = _room()
    d.farewell = {"pid": "p0", "city": "Boise", "announced": "2026-10-14", "night": "2026-10-19"}
    assert d.occasion_stay(d.people["p0"], NOW) == 1.6 and d.occasion_stay(d.people["p1"], NOW) == 1.0
    d.visits = {"p0": {"n": 9}}
    d.people["p0"].present = False
    _friends(d)
    _run(d.occasion_day(NOW, "2026-10-19"))
    assert d.toast["p0"] == "farewell" and d.people["p0"].pending_arrival is not None


def test_someone_who_moved_away_rarely_comes_back():
    d = _room()
    arrivals = []

    async def arrive(p):
        arrivals.append(p.id)

    d.arrive = arrive
    d.rng = type("R", (), {"random": lambda self: 0.05})()
    for p in (d.people["p0"], d.people["p1"]):
        p.present = False
        p.persona.update({"freq": 3, "days": [0, 1, 2, 3, 4, 5, 6], "window": [15, 22]})
    d.moved["p0"] = {"city": "Denver", "day": "2026-10-01"}
    _run(d.arrivals(NOW, 60, "2026-10-19"))
    assert arrivals == ["p1"]


def test_a_visitor_is_back_in_town_to_themselves_and_to_friends():
    d = _scene_director()
    _friends(d)
    d.moved["p0"] = {"city": "Denver", "day": "2026-10-01"}
    d.visiting.add("p0")
    mine = _scene_for(d, _chat(False), d.people["p0"])
    theirs = _scene_for(d, _chat(False), d.people["p1"])
    assert mine.back_in_town and "back in town" in mine.context
    assert not theirs.back_in_town and "P0 moved to Denver" in theirs.context


# ---------------------------------------------------------------- incidents and the room's history


def test_a_power_cut_holds_the_orders_until_the_lights_return():
    day = _day(lambda x: (i := occasions.incident_for(x)) is not None and i.kind == "power_out")
    inc = occasions.incident_for(day)
    mid, after = inc.start + timedelta(minutes=5), inc.end + timedelta(minutes=1)
    assert occasions.outage(mid) and not occasions.outage(after) and occasions.music_off(mid)
    assert "power is out" in " ".join(occasions.room_bits(mid, []))
    d = _room()
    d.clock = SimClock(start=mid)
    p = d.people["p0"]
    p.waiting = True
    d.queue = [Waiting("p0", mid - timedelta(minutes=5), False)]
    served = []

    async def open_order(p, b, w):
        served.append(p.id)

    d.open_order = open_order
    d.pick_bartender = lambda p: d.people["b1"]
    _run(d.serve_queue(mid))
    assert served == [] and len(d.queue) == 1
    _run(d.serve_queue(after))
    assert served == ["p0"]


def test_an_incident_is_remembered_by_everyone_there_and_by_the_room():
    d = _room()
    inc = occasions.Incident("power_out", NOW, 30)
    guests = [d.people["p0"], d.people["p1"], d.people["p2"]]
    _run(d.run_incident(inc, guests, NOW, "2026-10-19"))
    assert [pid for pid, _, imp, _ in d.memories if imp == 8] == ["p0", "p1", "p2"]
    assert d.history[-1]["title"] == "the night the power went out" and "candle" in d.history[-1]["keys"]
    assert d.posts and "power goes out" in d.posts[0] and "incident" in d.day_events


def test_a_snowstorm_keeps_people_later():
    d = _room()
    d.people["p0"].leave_at = NOW + timedelta(minutes=20)
    _run(d.run_incident(occasions.Incident("snowed_in", NOW, 0), [d.people["p0"]], NOW, "2026-10-19"))
    assert d.people["p0"].leave_at == NOW + timedelta(minutes=60)


def test_a_proposal_needs_a_couple_in_the_room():
    d = _room()
    inc = occasions.Incident("proposal", NOW, 0)
    guests = [d.people["p0"], d.people["p1"]]
    _run(d.run_incident(inc, guests, NOW, "2026-10-19"))
    assert d.history == [] and d.posts == []
    d.social.rels[pair_key("p0", "p1")] = RelState(bond="couple", familiarity=80, affinity=80)
    _run(d.run_incident(inc, guests, NOW, "2026-10-19"))
    assert d.history[-1]["kind"] == "proposal" and any("one knee" in p for p in d.posts)


def test_an_incident_waits_for_people_and_fires_once():
    day = _day(lambda x: (i := occasions.incident_for(x)) is not None and i.kind == "keg_kicked")
    inc = occasions.incident_for(day)
    d = _room()
    d.clock = SimClock(start=inc.start + timedelta(minutes=1))
    now, ds = d.clock.now(), day.isoformat()
    d.people["p2"].present = False
    _run(d.calendar_step(now, ds))
    assert d.history == []  # two guests aren't an audience
    d.people["p2"].present = True
    _run(d.calendar_step(now, ds))
    _run(d.calendar_step(now, ds))
    assert len(d.history) == 1 and inc.detail in d.history[0]["title"]


def test_regulars_bring_up_the_night_and_newer_faces_do_not():
    history = [occasions.history_row("2026-10-12", "power_out", "the night the power went out", ["A"], ["power"])]
    now = datetime(2026, 10, 19, 19)
    lines = [occasions.lore_line(history, now, 6, random.Random(i)) for i in range(60)]
    assert any("the night the power went out" in x for x in lines) and "" in lines
    assert not any(occasions.lore_line(history, now, 1, random.Random(i)) for i in range(60))
    assert not any(occasions.lore_line([dict(history[0], day="2026-10-19")], now, 6, random.Random(i)) for i in range(60))
    assert not any(occasions.lore_line([dict(history[0], day="2026-06-01")], now, 6, random.Random(i)) for i in range(60))


# ---------------------------------------------------------------- the scene and the mock


def test_the_scene_carries_the_birthday_and_the_move():
    d = _scene_director()
    _friends(d)
    d.people["p0"].persona["birthday"] = "10-19"
    d.farewell = {"pid": "p1", "city": "Denver", "announced": "2026-10-17", "night": "2026-10-22"}
    mine, theirs = _scene_for(d, _chat(False), d.people["p0"]), _scene_for(d, _chat(False), d.people["p1"])
    assert mine.birthday == "you" and "It's your birthday" in mine.context
    assert theirs.birthday == "P0" and "It's P0's birthday" in theirs.context
    assert mine.farewell == "P1" and "P1 is moving to Denver" in mine.context
    assert theirs.farewell == "you" and "You're moving to Denver" in theirs.context


def test_a_tuesday_scene_has_none_of_it():
    d = _scene_director()
    d.clock = SimClock(start=datetime(2026, 10, 20, 16))
    req = _scene_for(d, _chat(False), d.people["p0"])
    assert (req.occasion, req.birthday, req.farewell, req.back_in_town, req.incident) == ("", "", "", False, "")
    assert "slow Tuesday" in req.context


def test_the_mock_voices_the_occasion():
    d = _scene_director()
    _friends(d)
    d.people["p0"].persona["birthday"] = "10-19"
    req = _scene_for(d, _chat(False), d.people["p0"])
    said = {_run(MockLLM().speak(req)).say for _ in range(150)}
    assert any("birthday" in s for s in said)
    d.farewell = {"pid": "p0", "city": "Denver", "announced": "2026-10-17", "night": "2026-10-22"}
    d.people["p0"].persona.pop("birthday")
    d._bdays = None
    req = _scene_for(d, _chat(False), d.people["p0"])
    assert any("leaving" in s or "move" in s for s in {_run(MockLLM().speak(req)).say for _ in range(150)})


def test_the_calendar_leaves_a_row_for_each_day_and_a_private_party_keeps_its_area():
    d = _room()
    d.day_events = {"birthday"}
    d.log_calendar(NOW, "2026-10-19")
    assert d.calendar_log[-1] == {"day": "2026-10-19", "kinds": ["birthday"]} and d.day_events == set()
    day = _day(lambda x: occasions.party_for(x) is not None)
    party = occasions.party_for(day)
    d.clock = SimClock(start=party.start + timedelta(minutes=30))
    assert all(d.choose_area(d.people["p0"]) != party.area for _ in range(150))


# ---------------------------------------------------------------- the scorecard


def test_the_rhythm_report_grades_variety_and_counts_callbacks():
    log = [{"day": f"2026-10-{19 + i}", "kinds": k} for i, k in enumerate([["holiday"], [], ["band", "party"], ["incident"]])]
    history = [occasions.history_row("2026-10-21", "power_out", "the night the power went out", [], ["candle"])]
    lines = [(date(2026, 10, 20), "p1", "so about that candle"), (date(2026, 10, 23), "p2", "remember the candle night?")]
    r = occasions.report(log, history, lines)
    assert r["rate"] == 75 and r["band"] == "green" and r["days"] == 4
    assert r["counts"] == {"holiday": 1, "band": 1, "party": 1, "incident": 1} and r["recalled"] == 1
    flat = occasions.report([{"day": f"2026-10-{19 + i}", "kinds": []} for i in range(5)], [], [])
    assert flat["band"] == "red" and occasions.report(log[:2], [], [])["band"] == "none"


def test_a_round_offered_is_bought_even_if_the_buyer_passes_on_their_own():
    from app.sim.state import ThreadState

    d = _room()
    rounds = []

    async def round_for(buyer, t, bt):
        rounds.append((buyer.id, t.party))

    d.round_for = round_for
    t = ThreadState(id=7, channel="bar", kind="order", started=NOW, members=["p1", "b1"], ever={"p1": None, "b1": None},
                    max_turns=3, again=True, treat=True, party=["p0"])
    _run(d.finish_order(t))
    assert rounds == [("p1", ["p0"])]

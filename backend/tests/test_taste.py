import asyncio
import random
from datetime import datetime, timedelta

from app.llm.mock import _ASK_REC, MockLLM
from app.llm.types import TurnRequest, Utterance
from app.sim import life, menu, taste
from app.sim.clock import SimClock
from app.sim.social import pair_key
from app.sim.state import PersonState, RelState, ThreadState
from tests.test_sim import NOW, _director, _scene_for

DAY = "2026-10-19"
FAV = "Fallforge"
NERD = {"age": 30, "beer": "nerd", "big5": {"o": 5}, "drink": FAV}
NEWBIE = {"age": 30, "beer": "newbie", "big5": {"o": 1}, "drink": FAV}


def _run(coro):
    return asyncio.run(coro)


def _posting(d):
    """Replace the director's post and memory writes with recorders so nothing touches the database."""
    posts, memories = [], []

    async def post(channel, text, speaker=None, kind="speech", thread=None, thought=None):
        posts.append(text)

    async def add_memory(pid, ts, text, about, importance=5, kind="event", **kw):
        memories.append((pid, text))

    async def apply_delta(a, b, fam, aff, note):
        pass

    d.post, d.social.add_memory, d.social.apply_delta = post, add_memory, apply_delta
    return posts, memories


def _event(kind, cat="money", days=10, age_days=0):
    start = NOW - timedelta(days=age_days)
    return life.LifeEventRec(kind=kind, text="x", started_at=start, ends_at=start + timedelta(days=days), cat=cat)


def _order(guest="p0", **kw):
    return ThreadState(id=1, channel="bar", kind="order", started=NOW, members=[guest, "b1"], ever={guest: None, "b1": None}, max_turns=3, **kw)


# ---------------------------------------------------------------- pure rules


def test_seeding_favors_the_usual_and_drinks_in_its_style():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    assert rec.like[FAV] == taste.LIKE_USUAL
    assert taste.top(rec, 1) == [FAV]
    same = [d for d in menu.names() if d != FAV and taste.section(d) == taste.section(FAV)]
    assert same and all(0 < rec.like[d] < taste.LIKE_USUAL for d in same)


def test_a_persona_with_no_usual_still_gets_some_favorites():
    rec = taste.seed({"drink": "tastes everything"}, random.Random(1))
    assert len(taste.top(rec)) == 3


def test_a_long_streak_wears_a_favorite_out_and_it_wears_back_in():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    rng = random.Random(2)
    worn = [taste.first_of_visit(rec, FAV, DAY, rng) for _ in range(taste.TIRED_STREAK)]
    assert worn == [False] * (taste.TIRED_STREAK - 1) + [True]
    assert taste.tired_of(rec, DAY) == [FAV]
    # Tired of it, they don't pick it again.
    picks = {taste.intend(rec, {"drink": FAV}, FAV, random.Random(i), DAY).drink for i in range(60)}
    assert FAV not in picks
    taste.daily(rec, "2027-01-01")
    assert taste.tired_of(rec, "2027-01-01") == []


def test_a_new_drink_breaks_the_streak():
    rec = taste.TasteRec()
    rng = random.Random(1)
    for _ in range(taste.TIRED_STREAK - 1):
        taste.first_of_visit(rec, FAV, DAY, rng)
    assert not taste.first_of_visit(rec, "Supra Deluxe", DAY, rng)
    assert rec.streak == ["Supra Deluxe", 1]


def test_newbies_stick_to_their_drink_and_nerds_roam():
    def repeats(persona):
        rec = taste.seed(persona, random.Random(1))
        return sum(taste.intend(rec, persona, FAV, random.Random(i), DAY).drink == FAV for i in range(400))

    assert taste.adventurous(NERD) > taste.adventurous(NEWBIE)
    assert repeats(NEWBIE) > repeats(NERD) + 40


def test_daily_drift_is_deterministic_and_keeps_the_top_two():
    def drifted():
        rec = taste.TasteRec(like={"A": 0.9, "B": 0.8, "C": 0.5, "D": -0.5, "E": 0.02})
        taste.daily(rec, DAY)
        return rec.like

    assert drifted() == drifted()
    like = drifted()
    assert like["A"] == 0.9 and like["B"] == 0.8
    assert like["C"] < 0.5 and like["D"] > -0.5
    assert "E" not in like  # a faint taste fades out altogether


def test_a_tight_budget_leans_toward_the_specials():
    persona = {"drink": FAV, "beer": "casual", "big5": {"o": 3}}
    rec = taste.seed(persona, random.Random(1))
    specials = ["Supra Deluxe", "Supra Light"]
    picks = [taste.intend(rec, persona, "", random.Random(i), DAY, specials=specials, tight=True).drink for i in range(300)]
    loose = [taste.intend(rec, persona, "", random.Random(i), DAY, specials=specials, tight=False).drink for i in range(300)]
    assert sum(p in specials for p in picks) > sum(p in specials for p in loose) + 30


def test_a_recommendation_is_something_untried_in_a_style_they_like():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    for i in range(20):
        pick = taste.recommend({}, rec, random.Random(i), DAY)
        assert pick in menu.names() and pick not in rec.tried
        assert taste.section(pick) == taste.section(FAV)


def test_a_recommendation_skips_what_they_are_tired_of():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    close = [d for d in menu.names() if d not in rec.tried and taste.section(d) == taste.section(FAV)]
    rec.tired = {d: "2999-01-01" for d in close[:-1]}
    assert {taste.recommend({}, rec, random.Random(i), DAY) for i in range(30)} == {close[-1]}


def test_openness_and_trust_make_a_suggestion_land():
    def rate(persona, fam):
        return sum(taste.takes_rec(persona, fam, random.Random(i)) for i in range(400))

    assert rate(NERD, 0) > rate(NEWBIE, 0)
    assert rate(NEWBIE, 90) > rate(NEWBIE, 0)


def test_a_drink_lands_and_moves_their_taste():
    rec = taste.TasteRec()
    taste.after_drink(rec, FAV, "loved")
    assert rec.like[FAV] == taste.LIKE_STEP["loved"] and FAV in rec.tried and rec.history == [FAV]
    taste.after_drink(rec, FAV, "meh")
    assert rec.like[FAV] < taste.LIKE_STEP["loved"]
    for _ in range(taste.HISTORY_KEEP + 5):
        taste.after_drink(rec, "Supra Deluxe", "fine")
    assert len(rec.history) == taste.HISTORY_KEEP


def test_a_style_they_like_lands_better_than_one_they_do_not():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    other = next(d for d in menu.names() if taste.section(d) != taste.section(FAV) and rec.like.get(d, 0) <= 0)
    near = next(d for d in menu.names() if d != FAV and taste.section(d) == taste.section(FAV))
    loved = lambda drink: sum(taste.verdict(rec, {}, drink, random.Random(i)) == "loved" for i in range(500))
    assert loved(near) > loved(other)


def test_the_taste_record_survives_being_saved_and_loaded():
    rec = taste.seed({"drink": FAV}, random.Random(1))
    rec.owes["p1"] = 2
    rec.tired["Supra Deluxe"] = "2999-01-01"
    back = taste.TasteRec.load(rec.dump())
    assert back == rec
    assert taste.TasteRec.load({"like": {"A": 0.5}, "junk": 1}).like == {"A": 0.5}


# ---------------------------------------------------------------- money


def test_budget_comes_from_the_persona_or_from_their_life():
    assert taste.budget({"budget": "flush"}) == "flush"
    assert taste.budget({"life": "behind on rent", "tipper": "generous"}) == "tight"
    assert taste.budget({"tipper": "low"}) == "tight"
    assert taste.budget({"tipper": "generous", "job": "owns a restaurant"}) == "flush"
    assert taste.budget({"tipper": "standard"}) == "ok"


def test_money_trouble_shrinks_the_cap_and_a_windfall_grows_it():
    persona = {"tipper": "standard"}
    base = taste.visit_cap(persona, [], NOW, life.freshness)
    assert base == taste.BUDGET_CAP["ok"]
    fresh = taste.visit_cap(persona, [_event("lost_the_job")], NOW, life.freshness)
    faded = taste.visit_cap(persona, [_event("lost_the_job", age_days=8)], NOW, life.freshness)
    assert fresh < faded < base
    assert taste.visit_cap(persona, [_event("windfall", cat="good")], NOW, life.freshness) > base
    assert taste.visit_cap(persona, [_event("slammed_at_work", cat="work")], NOW, life.freshness) == base


def test_a_guest_can_afford_a_drink_up_to_their_cap():
    assert taste.can_afford(1600, 2400, 800)
    assert not taste.can_afford(1700, 2400, 800)


def test_only_someone_who_can_spare_it_buys_a_round():
    rng = random.Random(1)
    rolls = lambda persona, **kw: sum(taste.buys_round(persona, kw.get("mood", 0.0), 0.0, kw.get("owed", 0), kw.get("flush", False), random.Random(i), 2) for i in range(500))
    assert rolls({"tipper": "low"}) == 0  # a tight budget never treats
    assert rolls({"budget": "flush"}) > rolls({"budget": "ok"}) > 0
    assert rolls({"budget": "ok"}, owed=3, mood=0.5) > rolls({"budget": "ok"})
    assert not taste.buys_round({"budget": "flush"}, 1.0, 0.5, 3, True, rng, 0)  # nobody to treat


# ---------------------------------------------------------------- the director


def _patron(d, pid="p0", **kw):
    p = d.people[pid]
    p.present, p.location = True, "bar"
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def test_a_guest_who_has_spent_their_limit_holds_off_instead_of_ordering():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    p = _patron(d, drinks=2, drink_goal=4, cap=1600, spent=1600, next_drink_at=NOW - timedelta(minutes=1), leave_at=NOW + timedelta(hours=2))

    async def go():
        assert not d.wants_round(p, NOW)
        await asyncio.sleep(0)  # let the small action post

    _run(go())
    assert p.drink_goal == p.drinks and p.next_drink_at is None
    assert [x["kind"] for x in d.taste_log] == ["skip"]


def test_a_guest_with_room_in_their_budget_still_wants_the_round():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    p = _patron(d, drinks=2, drink_goal=4, cap=3200, spent=1600, next_drink_at=NOW - timedelta(minutes=1), leave_at=NOW + timedelta(hours=2))
    assert d.wants_round(p, NOW) and not d.taste_log


def test_nobody_is_limited_when_no_cap_has_been_set():
    d = _director()
    p = _patron(d, drinks=5, spent=9999)
    assert not d.broke(p)


def test_the_first_drink_is_never_refused_for_money():
    d = _director()
    p = _patron(d, drinks=0, cap=100, spent=0)
    assert not d.broke(p)


def test_check_in_sets_a_cap_that_money_trouble_lowers():
    d = _director()
    d.clock = SimClock(start=NOW)
    d.life["p0"] = [_event("lost_the_job")]
    d.life["p1"] = []
    d.people["p0"].persona.update(tipper="standard")
    d.people["p1"].persona.update(tipper="standard")
    d.check_in(d.people["p0"])
    d.check_in(d.people["p1"])
    assert 0 < d.people["p0"].cap < d.people["p1"].cap
    assert d.people["p0"].spent == 0


def test_a_suggestion_the_guest_takes_is_what_gets_poured():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append(drink)

    d.charge = charge
    guest = _patron(d)
    t = _order(intent=taste.Intent("rec"), suggest="Supra Deluxe", take_rec=True, fallback=FAV)
    _run(d.finish_order(t))
    assert charged == ["Supra Deluxe"] and guest.drink == "Supra Deluxe"
    assert [x["kind"] for x in d.taste_log] == ["rec_taken"]


def test_a_suggestion_the_guest_turns_down_gives_way_to_their_fallback():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append(drink)

    d.charge = charge
    _patron(d)
    t = _order(intent=taste.Intent("rec"), suggest="Supra Deluxe", take_rec=False, fallback=FAV)
    t.order_drink = "Supra Deluxe"  # the bartender's line was recorded as the drink on the way
    _run(d.finish_order(t))
    assert charged == [FAV]
    assert [x["kind"] for x in d.taste_log] == ["rec_declined"]


def test_a_repeat_round_still_takes_the_bartenders_suggestion():
    d = _director()
    d.clock = SimClock(start=NOW)
    guest = _patron(d, drinks=1)
    t = _order(again=True, suggest="Supra Deluxe", intent=taste.Intent("rec"))
    d.record_drink(t, d.people["b1"], Utterance(say="Try the Supra Deluxe.", drink="Supra Deluxe"))
    assert t.order_drink == "Supra Deluxe" and guest.drink == "Supra Deluxe"


def test_a_repeat_round_ignores_a_bartender_pour_nobody_asked_for():
    d = _director()
    d.clock = SimClock(start=NOW)
    _patron(d, drinks=1)
    t = _order(again=True)
    d.record_drink(t, d.people["b1"], Utterance(say="Here's a Supra Deluxe.", drink="Supra Deluxe"))
    assert t.order_drink == ""


def test_a_round_bought_charges_the_buyer_and_leaves_the_friends_owing():
    d = _director()
    d.clock = SimClock(start=NOW)
    posts, memories = _posting(d)
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append((p.id, buyer.id if buyer else None))

    d.charge = charge
    buyer, friend = _patron(d, "p0", drinks=2), _patron(d, "p1")
    t = _order(treat=True, party=["p1"], again=True, ordered=True, order_drink=FAV)
    _run(d.finish_order(t))
    assert charged == [("p0", None), ("p1", "p0")]
    assert d.tastes["p1"].owes["p0"] == 1 and d.tastes["p0"].owes["p1"] == -1
    assert any("buys a round for P1" in x for x in posts)
    assert any(pid == "p1" and "bought me a drink" in text for pid, text in memories)
    assert [x["kind"] for x in d.taste_log if x["kind"] == "round"] == ["round"]


def test_a_round_skips_a_friend_who_has_had_enough():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append(p.id)

    d.charge = charge
    _patron(d, "p0", drinks=2)
    _patron(d, "p1", buzz=0.8)
    t = _order(treat=True, party=["p1"], again=True, ordered=True, order_drink=FAV)
    _run(d.finish_order(t))
    assert charged == ["p0"]


def test_a_party_first_round_is_not_a_treat():
    d = _director()
    d.clock = SimClock(start=NOW)
    _posting(d)
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append((p.id, buyer))

    d.charge = charge
    _patron(d, "p0")
    _patron(d, "p1")
    t = _order(party=["p1"], ordered=True, order_drink=FAV)
    _run(d.finish_order(t))
    assert charged == [("p0", None), ("p1", None)]


def _friends(d, a="p0", b="p1"):
    d.social.rels[pair_key(a, b)] = RelState(kind="friend", familiarity=70, affinity=30, bond="friends")


def test_someone_who_feels_generous_treats_friends_nearby(monkeypatch):
    d = _director()
    d.clock = SimClock(start=NOW)
    _friends(d)
    p = _patron(d, "p0", drinks=1, cap=6400, spent=800)
    q = _patron(d, "p1")
    monkeypatch.setattr(taste, "buys_round", lambda *a, **k: True)
    assert d.treat_friends(p, NOW) == [q]


def test_nobody_treats_a_stranger_or_someone_who_is_busy(monkeypatch):
    d = _director()
    d.clock = SimClock(start=NOW)
    monkeypatch.setattr(taste, "buys_round", lambda *a, **k: True)
    p = _patron(d, "p0", drinks=1, cap=6400)
    q = _patron(d, "p1")
    assert d.treat_friends(p, NOW) == []  # strangers
    _friends(d)
    q.thread_id = 7
    assert d.treat_friends(p, NOW) == []  # in a conversation
    q.thread_id, q.location = None, "patio"
    assert d.treat_friends(p, NOW) == []  # elsewhere


def test_nobody_treats_beyond_what_they_can_afford(monkeypatch):
    d = _director()
    d.clock = SimClock(start=NOW)
    _friends(d)
    monkeypatch.setattr(taste, "buys_round", lambda *a, **k: True)
    p = _patron(d, "p0", drinks=1, cap=1600, spent=800)  # room for their own next drink and no more
    _patron(d, "p1")
    assert d.treat_friends(p, NOW) == []


def test_taste_moves_after_each_drink_and_a_suggestion_that_works_is_remembered(monkeypatch):
    d = _director()
    d.clock = SimClock(start=NOW)
    _, memories = _posting(d)
    guest = _patron(d, drinks=1)
    t = _order(suggest="Supra Deluxe")
    monkeypatch.setattr(taste, "verdict", lambda *a, **k: "loved")
    _run(d.taste_after(guest, "Supra Deluxe", t, "b1", None))
    rec = d.tastes["p0"]
    assert "Supra Deluxe" in rec.tried and rec.like["Supra Deluxe"] > 0
    assert any("suggested the Supra Deluxe" in text for _, text in memories)
    assert {x["kind"] for x in d.taste_log} >= {"new", "rec_loved"}


def test_taste_is_seeded_once_and_kept():
    d = _director()
    d.people["p0"].persona["drink"] = FAV
    first = d.taste_of(d.people["p0"])
    assert d.taste_of(d.people["p0"]) is first and first.like[FAV] == taste.LIKE_USUAL


def test_planning_an_order_hands_the_guest_a_decision():
    d = _director()
    d.clock = SimClock(start=NOW)
    d.people["p0"].persona.update(drink=FAV)
    t = _order()
    d.plan_order(t, d.people["p0"], d.people["b1"])
    assert t.intent is not None and (t.intent.drink or t.suggest)
    if t.intent.kind == "rec":
        assert t.suggest in menu.names() and t.fallback


def test_a_first_visit_often_gets_the_tasting_offer():
    d = _director()
    d.clock = SimClock(start=NOW)
    p = _patron(d, first_visit=True)
    kinds = []
    for i in range(80):
        d.rng = random.Random(i)
        t = _order()
        d.plan_order(t, p, d.people["b1"])
        kinds.append(t.intent.kind)
    assert kinds.count("rec") > 30


# ---------------------------------------------------------------- what the model hears


def _scene(d, t, who):
    d.clock = SimClock(start=NOW)
    for pid in ("p0", "p1", "b1"):
        d.people[pid].persona.setdefault("job", "welder")
    return _scene_for(d, t, d.people[who])


def test_the_guest_is_told_the_drink_code_chose():
    d = _director()
    _patron(d, "p0")
    t = _order(intent=taste.Intent("switch", "Supra Deluxe", "something you like"))
    ctx = _scene(d, t, "p0").context
    assert "switch to Supra Deluxe" in ctx and "exact board name" in ctx


def test_a_guest_who_wants_the_same_again_is_told_so():
    d = _director()
    _patron(d, "p0", drinks=1, drink=FAV)
    t = _order(again=True, intent=taste.Intent("same", FAV, "you're happy with it"))
    assert f"get the same again: {FAV}" in _scene(d, t, "p0").context


def test_a_guest_who_asks_for_a_suggestion_is_told_to_ask_and_not_name_a_drink():
    d = _director()
    _patron(d, "p0")
    t = _order(intent=taste.Intent("rec"), suggest="Supra Deluxe", take_rec=True, fallback=FAV)
    req = _scene(d, t, "p0")
    assert "ask the bartender" in req.context and "leave drink empty" in req.context and req.ask_rec and req.want == ""
    assert "Order a drink from the board" not in req.context


def test_the_guest_answers_the_bartenders_suggestion_the_way_code_decided():
    d = _director()
    _patron(d, "p0")
    lines = [("speech", "p0", "What's good?"), ("speech", "b1", "Try the Supra Deluxe.")]
    yes = _scene(d, _order(intent=taste.Intent("rec"), suggest="Supra Deluxe", take_rec=True, fallback=FAV, lines=lines), "p0")
    no = _scene(d, _order(intent=taste.Intent("rec"), suggest="Supra Deluxe", take_rec=False, fallback=FAV, lines=lines), "p0")
    assert "put Supra Deluxe in drink" in yes.context and yes.want == "Supra Deluxe"
    assert f"order {FAV} instead" in no.context and no.want == FAV


def test_the_bartender_is_told_what_to_recommend():
    d = _director()
    _patron(d, "p0")
    t = _order(intent=taste.Intent("rec"), suggest="Supra Deluxe")
    req = _scene(d, t, "b1")
    assert "Recommend Supra Deluxe by its exact board name" in req.context and req.suggest == "Supra Deluxe"
    assert "Recommend" not in _scene(d, _order(), "b1").context


def test_a_guest_buying_a_round_is_told_who_for():
    d = _director()
    _patron(d, "p0")
    _patron(d, "p1")
    t = _order(treat=True, party=["p1"], intent=taste.Intent("same", FAV, "x"))
    req = _scene(d, t, "p0")
    assert "buying a round for P1" in req.context and req.treat == "P1"


# ---------------------------------------------------------------- the mock


def _speak(**kw):
    base = dict(person_id="p0", person_name="P0", world="", persona="", context="", kind="order")
    return _run(MockLLM().speak(TurnRequest(**{**base, **kw})))


def test_mock_guest_orders_the_drink_it_was_told_to():
    for _ in range(20):
        assert _speak(want="Supra Deluxe").drink == "Supra Deluxe"


def test_mock_guest_asks_for_a_suggestion_without_naming_a_drink():
    u = _speak(ask_rec=True)
    assert u.drink == "" and u.say in _ASK_REC


def test_mock_bartender_recommends_and_the_guest_takes_or_declines():
    bt = _speak(is_bartender=True, suggest="Supra Deluxe", last_line="What's good?")
    assert bt.drink == "Supra Deluxe" and "Supra Deluxe" in bt.say
    yes = _speak(want="Supra Deluxe", suggest="Supra Deluxe", last_line="Try the Supra Deluxe.")
    no = _speak(want=FAV, suggest="Supra Deluxe", last_line="Try the Supra Deluxe.")
    assert yes.drink == "Supra Deluxe" and "take the Supra Deluxe" in yes.say
    assert no.drink == FAV and "not today" in no.say


def test_mock_repeat_round_stays_with_the_drink_chosen():
    for _ in range(40):
        u = _speak(again=True, want=FAV, last_line="Another?")
        assert u.drink in ("", FAV)


def test_mock_bartender_offers_another_with_a_suggestion():
    assert "Supra Deluxe" in _speak(is_bartender=True, again=True, suggest="Supra Deluxe").say


def test_mock_guest_says_when_the_round_is_on_them():
    assert "a round for Sam and Lee, on me" in _speak(want=FAV, treat="Sam and Lee").say


# ---------------------------------------------------------------- the scorecard


def test_habits_count_repeats_and_variety_among_regulars():
    steady = [("a", FAV)] * 3 + [("a", "Supra Deluxe")] * 3
    always = [("b", FAV)] * 6
    never = [("c", n) for n in menu.names()[:6]]
    h = taste.habits([], steady)
    assert h["guests"] == 1 and h["repeat"] == 0.8 and h["band"] == "amber"
    assert taste.habits([], always)["band"] == "red" and taste.habits([], never)["band"] == "red"
    assert taste.habits([], steady + never[:4])["guests"] == 2


def test_habits_ignore_people_who_have_not_had_enough_drinks():
    h = taste.habits([], [("a", FAV)] * 3)
    assert h["guests"] == 0 and h["repeat"] is None and h["band"] == "none"


def test_habits_tally_what_happened():
    log = [{"kind": k} for k in ("rec_taken", "rec_taken", "rec_declined", "rec_loved", "skip", "round", "round", "tired", "new")]
    h = taste.habits(log, [])
    assert (h["recs"], h["taken"], h["loved"], h["skips"], h["rounds"], h["tired"], h["tried_new"]) == (3, 2, 1, 1, 2, 1, 1)

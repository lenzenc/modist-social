import random
from datetime import timedelta

from app.agents.agent import build_turn
from app.llm.mock import MockLLM
from app.sim import staff
from app.sim.clock import SimClock
from app.sim.social import pair_key
from app.sim.state import PersonState, RelState, ThreadState
from tests.test_drunk import _p, _posting, _run
from tests.test_sim import NOW, _director, _scene_director

BT = {"c": 3, "n": 3}


def _persona(**kw):
    return {"job": "bartender", "big5": {**BT, **kw.pop("big5", {})}, "peeve": "impatient", "rough": ["the cat is at the vet"], **kw}


def _bar():
    """A director with two bartenders on the bar, one guest, and the database-touching calls recorded."""
    d = _scene_director()
    d.posts = _posting(d)
    d.people["b1"].persona = _persona()
    d.people["b2"] = PersonState(id="b2", name="B Two", short="B2", display="B Two", role="bartender", pronouns="they/them",
                                 color="#000", persona=_persona(), present=True, location="bar")
    d.shift = ("b1", "b2")
    d.staff = {b: staff.Shift(started=NOW) for b in ("b1", "b2")}
    deltas, memories = [], []

    async def delta(a, b, fam, aff, note):
        deltas.append((a, b, fam, aff))

    async def memory(pid, ts, text, about, importance=5, **kw):
        memories.append((pid, text, importance))

    d.social.apply_delta, d.social.add_memory = delta, memory
    d.deltas, d.memories = deltas, memories
    return d


def _order(guest="p0", bt="b1", **kw):
    t = ThreadState(id=5, channel="bar", kind="order", started=NOW, members=[guest, bt], ever=dict.fromkeys([guest, bt]), max_turns=3)
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# ---------------------------------------------------------------- the pure rules


def test_fatigue_builds_with_the_crowd_and_the_line_and_eases_when_quiet():
    quiet, busy, lined = (staff.Shift(started=NOW) for _ in range(3))
    for s, guests, queue in ((quiet, 6, 0), (busy, 20, 0), (lined, 20, 4)):
        staff.tire(s, _persona(), 60, guests, queue)
    assert 0 < quiet.fatigue < busy.fatigue < lined.fatigue
    staff.tire(quiet, _persona(), 600, 1, 0)
    assert quiet.fatigue < 0.3


def test_the_careless_and_the_anxious_tire_faster_and_a_rough_night_faster_still():
    base, careless, rough = (staff.Shift(started=NOW) for _ in range(3))
    rough.rough = "the cat is at the vet"
    staff.tire(base, _persona(), 60, 15, 0)
    staff.tire(careless, _persona(big5={"c": 1, "n": 5}), 60, 15, 0)
    staff.tire(rough, _persona(), 60, 15, 0)
    assert base.fatigue < careless.fatigue and base.fatigue < rough.fatigue


def test_a_rough_night_starts_low_and_only_sometimes():
    rolls = [staff.start_shift(_persona(), random.Random(i), NOW) for i in range(200)]
    rough = [s for s in rolls if s.rough]
    assert 10 < len(rough) < 60 and all(s.rough == "the cat is at the vet" for s in rough)
    assert not staff.start_shift({"rough": []}, random.Random(1), NOW).rough
    moods = [staff.opening_mood(_persona(), random.Random(i), rough[0]) for i in range(50)]
    plain = [staff.opening_mood(_persona(), random.Random(i), staff.Shift(started=NOW)) for i in range(50)]
    assert sum(moods) < sum(plain)


def test_slips_get_likelier_when_worn_out_rough_or_careless_and_are_capped():
    fresh = staff.Shift(started=NOW)
    worn = staff.Shift(started=NOW, fatigue=0.9, rough="x")
    assert staff.mistake_chance(fresh, _persona(), 4) < staff.mistake_chance(worn, _persona(), 4)
    assert staff.mistake_chance(fresh, _persona(), 4) < staff.mistake_chance(fresh, _persona(big5={"c": 1}), 4)
    assert staff.mistake_chance(worn, _persona(big5={"c": 1}), 20) <= staff.MISTAKE_MAX


def test_a_favourite_is_known_well_and_liked_and_an_irritant_known_and_not():
    assert staff.favorite(RelState(familiarity=70, affinity=60)) and not staff.favorite(RelState(familiarity=70, affinity=20))
    assert staff.irritant(RelState(familiarity=40, affinity=-15)) and not staff.irritant(RelState(familiarity=5, affinity=-15))
    assert "favorite" in staff.opinion(RelState(familiarity=70, affinity=60), "Pat")
    assert "nerves" in staff.opinion(RelState(familiarity=40, affinity=-15), "Pat")
    assert staff.opinion(RelState(familiarity=5, affinity=0), "Pat") == ""


def test_each_pet_peeve_is_something_the_guest_visibly_does():
    guest = _p(persona={"tipper": "low"})
    assert staff.peeve_hit("bad_tipper", guest) and not staff.peeve_hit("bad_tipper", _p())
    assert staff.peeve_hit("drunk", _p(buzz=0.6)) and not staff.peeve_hit("drunk", _p(buzz=0.1))
    assert staff.peeve_hit("impatient", guest, waited_min=3) and not staff.peeve_hit("impatient", guest, waited_min=0.5)
    assert staff.peeve_hit("indecisive", guest, intent_kind="rec") and not staff.peeve_hit("indecisive", guest, intent_kind="same")
    seated = _p(stool=3, drinks=1)
    assert staff.peeve_hit("camper", seated, stayed_min=120) and not staff.peeve_hit("camper", seated, stayed_min=30)
    assert not staff.peeve_hit("", guest, waited_min=99) and not staff.peeve_hit("camper", _p(drinks=1), stayed_min=120)


def test_friction_needs_a_line_and_grows_with_fatigue_and_bad_blood():
    calm = staff.Shift(started=NOW)
    sore = staff.Shift(started=NOW, fatigue=0.9, rough="x")
    assert staff.friction_chance(calm, 50, 0) == 0.0
    assert staff.friction_chance(calm, 50, 2) < staff.friction_chance(sore, 50, 2)
    assert staff.friction_chance(calm, 50, 2) < staff.friction_chance(calm, -40, 2)
    assert staff.friction_chance(sore, -90, 2) <= staff.FRICTION_MAX


def test_a_tired_or_sour_bartender_chats_less_and_a_cheerful_one_a_touch_more():
    fresh, worn = staff.Shift(started=NOW), staff.Shift(started=NOW, fatigue=0.9)
    assert staff.mood_scale(worn, -0.5) < staff.mood_scale(fresh, 0.0) < staff.mood_scale(fresh, 0.6)
    assert staff.mood_scale(worn, -1.0) >= 0.3


def test_the_end_of_shift_memory_names_what_happened_and_the_log_row_says_if_anything_did():
    s = staff.Shift(started=NOW, rough="the cat is at the vet", wrong=2, spills=1, gripes=1, grudge="Rico", fatigue=0.8, served=30)
    text, importance, row = staff.end_of_shift(s, "b1", "2026-10-23")
    assert "rough night" in text and "2 wrong pours" in text and "Rico left you with the rush" in text and importance == 4
    assert row["textured"] and row["wrong"] == 2 and row["worn"] and row["day"] == "2026-10-23"
    text, importance, row = staff.end_of_shift(staff.Shift(started=NOW, served=12), "b1", "2026-10-24")
    assert "ordinary shift" in text and importance == 2 and not row["textured"]


def test_the_scorecard_bands_on_how_many_shifts_had_anything_in_them():
    row = lambda t: {"textured": t, "wrong": int(t), "spills": 0, "rough": False, "gripes": 0, "peeves": 0}  # noqa: E731
    assert staff.report([row(True)] * 2)["band"] == "none"
    assert staff.report([row(True)] * 3 + [row(False)] * 3)["band"] == "green"
    assert staff.report([row(True)] * 1 + [row(False)] * 3)["band"] == "amber"
    r = staff.report([row(False)] * 5)
    assert r["band"] == "red" and r["rate"] == 0 and r["shifts"] == 5


# ---------------------------------------------------------------- in the director


def test_a_shift_starts_with_a_mood_and_ends_with_a_memory_and_a_log_row():
    d = _bar()
    d.staff.clear()
    d.rng = random.Random(3)
    _run(d.bartender_on(d.people["b1"]))
    assert "b1" in d.staff and -1 <= d.people["b1"].mood <= 1
    d.staff["b1"].wrong, d.staff["b1"].served = 1, 9
    _run(d.end_shift(d.people["b1"]))
    assert "b1" not in d.staff and d.staff_log[-1]["wrong"] == 1 and d.staff_log[-1]["pid"] == "b1"
    assert d.memories and d.memories[-1][0] == "b1" and "wrong pour" in d.memories[-1][1]
    _run(d.end_shift(d.people["b1"]))  # nothing left to end
    assert len(d.staff_log) == 1


def test_a_wrong_pour_is_caught_and_the_guest_still_gets_what_they_ordered(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 1.0)
    monkeypatch.setattr(staff, "roll_mistake", lambda rng: "wrong_pour")
    charged = []

    async def charge(p, drink, bt, t, buyer=None):
        charged.append(drink)

    d.charge = charge
    t = _order(order_drink="Skoloft", ordered=True)
    mood = d.people["b1"].mood
    _run(d.finish_order(t))
    assert charged == ["Skoloft"]
    sh = d.staff["b1"]
    assert sh.wrong == 1 and sh.served == 1 and d.people["b1"].mood < mood
    assert ("b2", "b1", 0, 1) in d.deltas  # the coworker covers
    assert any(m[0] == "p0" and "wrong beer" in m[1] for m in d.memories)
    assert any("instead of the Skoloft" in text for text in d.posts)


def test_a_spill_costs_the_bartender_a_little_mood_and_makes_no_wrong_order(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 1.0)
    monkeypatch.setattr(staff, "roll_mistake", lambda rng: "spill")
    _run(d.bartender_moment(d.people["p0"], "Skoloft", "b1", _order()))
    sh = d.staff["b1"]
    assert sh.spills == 1 and sh.wrong == 0 and d.people["b1"].mood < 0


def test_a_guest_who_trips_the_peeve_sours_the_bartender_a_little(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 0.0)
    d.rng = random.Random(1)
    t = _order(waited=5.0)
    _run(d.bartender_moment(d.people["p0"], "Skoloft", "b1", t))
    assert d.staff["b1"].peeves == 1 and d.people["b1"].mood < 0
    quick = _order(waited=0.0)
    _run(d.bartender_moment(d.people["p0"], "Skoloft", "b1", quick))
    assert d.staff["b1"].peeves == 1


def test_a_favourite_regular_cheers_the_bartender_up(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 0.0)
    d.social.rels[pair_key("b1", "p0")] = RelState(familiarity=80, affinity=70)
    _run(d.bartender_moment(d.people["p0"], "Skoloft", "b1", _order()))
    assert d.people["b1"].mood > 0


def test_time_on_the_bar_wears_bartenders_down_and_a_long_line_sours_them(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 0.0)
    for i in range(12):
        d.people[f"x{i}"] = PersonState(id=f"x{i}", name="X", short="X", display="X", role="patron", pronouns="", color="",
                                        persona={}, present=True)
    d.queue = [object()] * 5
    _run(d.staff_step(30))
    assert d.staff["b1"].fatigue > 0 and d.people["b1"].mood < 0


def test_idle_spills_happen_and_show_in_the_room(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "mistake_chance", lambda *a: 1.0)
    for i in range(4):
        d.people[f"x{i}"] = PersonState(id=f"x{i}", name="X", short="X", display="X", role="patron", pronouns="", color="",
                                        persona={}, present=True)
    _run(d.staff_step(60))
    assert d.staff["b1"].spills == 1 and d.staff["b2"].spills == 1


def _friction(d, queue=True):
    d.threads[1] = _order(guest="p0", bt="b1")
    d.threads[2] = ThreadState(id=2, channel="bar", kind="chat", started=NOW, members=["p1", "b2"], ever=dict.fromkeys(["p1", "b2"]), max_turns=9)
    d.people["p0"].present = d.people["p1"].present = True
    d.queue = [object()] if queue else []


def test_one_bartender_pouring_into_a_line_while_the_other_chats_builds_a_grievance(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "friction_chance", lambda *a: 1.0)
    _friction(d)
    _run(d.staff_friction(NOW, 5))
    sh = d.staff["b1"]
    assert sh.gripe == "b2" and sh.grudge == "B2" and sh.gripes == 1 and ("b1", "b2", 0, -1) in d.deltas
    assert not d.staff["b2"].gripe


def test_no_grievance_without_a_line_or_when_both_are_busy_the_same_way(monkeypatch):
    d = _bar()
    monkeypatch.setattr(staff, "friction_chance", lambda *a: 1.0)
    _friction(d, queue=False)
    _run(d.staff_friction(NOW, 5))
    assert not d.staff["b1"].gripe and not d.staff["b2"].gripe
    d.queue = [object()]
    d.threads[2].kind = "order"
    _run(d.staff_friction(NOW, 5))
    assert not d.staff["b1"].gripe and not d.staff["b2"].gripe


def test_tired_bartenders_linger_and_join_chats_less():
    d = _bar()
    t = ThreadState(id=1, channel="bar", kind="order", started=NOW, members=["p0", "b1"], ever={}, max_turns=3)
    fresh = d.linger_chance(t)
    d.staff["b1"].fatigue = 1.0
    d.people["b1"].mood = -0.6
    assert d.linger_chance(t) < fresh


# ---------------------------------------------------------------- the scene and the mock


def _scene(d, t, pid):
    d.persona_text.update({k: "" for k in d.people})
    return build_turn(d, t, d.people[pid], False)


def test_a_bartenders_scene_carries_how_the_shift_is_going():
    d = _bar()
    d.staff["b1"].fatigue, d.staff["b1"].rough = 0.9, "the cat is at the vet"
    d.people["p0"].present = True
    t = _order()
    req = _scene(d, t, "b1")
    assert "rough night" in req.context and "worn out" in req.context
    assert req.rough and req.tired == "worn out"
    assert not _scene(d, t, "p0").rough


def test_the_peeve_and_a_favourite_reach_the_order_scene():
    d = _bar()
    d.people["p0"].present = True
    t = _order(waited=4.0)
    req = _scene(d, t, "b1")
    assert req.peeve and "pet peeves" in req.context and not req.favorite
    d.social.rels[pair_key("b1", "p0")] = RelState(familiarity=80, affinity=70)
    req = _scene(d, _order(waited=0.0), "b1")
    assert req.favorite and not req.peeve and "favorite regulars" in req.context


def test_a_gripe_is_aired_once_answered_once_and_forgiven():
    d = _bar()
    d.staff["b1"].gripe, d.staff["b1"].grudge = "b2", "B2"
    t = ThreadState(id=7, channel="staff", kind="staff", started=NOW, members=["b1", "b2"], ever=dict.fromkeys(["b1", "b2"]), max_turns=6)
    aired = _scene(d, t, "b1")
    assert "annoyed that B2 left you" in aired.context and aired.gripe == "B2" and aired.grumble
    assert d.staff["b1"].gripe == "" and d.staff["b2"].owed == "B"
    answer = _scene(d, t, "b2")
    assert "B is annoyed" in answer.context and answer.gripe == "B" and not answer.grumble
    assert d.staff["b2"].made_up and not d.staff["b2"].owed
    plain = _scene(d, t, "b1")
    assert "between orders" in plain.context and not plain.gripe


def test_the_mock_voices_each_bartender_state():
    d = _bar()
    d.people["p0"].present = True
    mock = MockLLM()
    for flag in ({"peeve": True}, {"favorite": True}, {"rough": True}, {"tired": "tired"}):
        req = _scene(d, _order(), "b1")
        for k, v in flag.items():
            setattr(req, k, v)
        assert _run(mock.speak(req)).say
    req = _scene(d, _order(), "b1")
    req.kind, req.gripe, req.grumble = "staff", "B2", True
    assert "B2" in _run(mock.speak(req)).say
    req.grumble = False
    assert _run(mock.speak(req)).say

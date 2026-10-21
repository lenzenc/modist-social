import random
from datetime import datetime, timedelta

import yaml

from app.agents.prompts import persona_prompt, world_prompt
from app.seed.loader import HERE
from app.sim.clock import HOURS, SimClock, is_open, open_close
from app.sim.schedule import ROSTER, arrival_rate, on_shift
from app.sim.social import relation_label
from app.sim.state import PersonState, RelState, display_name, short_name


def test_clock_accelerates_pauses_and_changes_speed():
    c = SimClock(start=datetime(2026, 10, 19, 15, 0), speed=60)
    t0 = c.now()
    c.pause()
    frozen = c.now()
    assert c.now() == frozen  # no drift while paused
    assert frozen - t0 < timedelta(seconds=5)
    c.resume()
    c.set_speed(120)
    assert c.speed == 120


def test_every_open_half_hour_has_exactly_two_bartenders():
    base = datetime(2026, 10, 19)  # a Monday
    for day in range(7):
        d = base + timedelta(days=day)
        o, c = open_close(d)
        t = o
        while t < c:
            pair = on_shift(t)
            assert pair is not None and len(set(pair)) == 2, f"gap at {t}"
            assert is_open(t)
            t += timedelta(minutes=30)
    # Nobody is scheduled outside opening hours.
    for wd, shifts in ROSTER.items():
        assert shifts[0][0] == HOURS[wd][0] and shifts[-1][1] == HOURS[wd][1]


def test_all_five_bartenders_work_and_shifts_are_pairs():
    working = {b for shifts in ROSTER.values() for _, _, pair in shifts for b in pair}
    assert working == {"b1", "b2", "b3", "b4", "b5"}


def test_friday_evening_beats_tuesday_afternoon():
    patrons = yaml.safe_load((HERE / "patrons.yaml").read_text())
    assert len(patrons) == 40

    def total(t):
        return sum(arrival_rate(p["freq"], p["days"], p["window"], t) for p in patrons)

    fri_eve = total(datetime(2026, 10, 23, 18, 0))
    tue_aft = total(datetime(2026, 10, 20, 15, 30))
    assert fri_eve > 2 * tue_aft


def test_seed_integrity():
    patrons = yaml.safe_load((HERE / "patrons.yaml").read_text())
    bars = yaml.safe_load((HERE / "bartenders.yaml").read_text())
    rels = yaml.safe_load((HERE / "relationships.yaml").read_text())
    ids = {p["id"] for p in patrons + bars}
    assert len(bars) == 5 and len(ids) == 45
    assert all(r["a"] in ids and r["b"] in ids and r["a"] != r["b"] for r in rels)
    shorts = [short_name(p["name"]) for p in patrons + bars]
    assert len(shorts) == len(set(shorts)), "first names must be unique (the transcript uses them)"


def _person(i="p03"):
    p = yaml.safe_load((HERE / "patrons.yaml").read_text())
    row = next(r for r in p if r["id"] == i)
    return PersonState(
        id=row["id"], name=row["name"], short=short_name(row["name"]), display=display_name(row["name"]),
        role="patron", pronouns=row["pronouns"], color="#fff", persona=row,
    )


def test_cacheable_prefix_is_byte_stable():
    assert world_prompt("Minneapolis, MN") == world_prompt("Minneapolis, MN")
    p = _person()
    assert persona_prompt(p) == persona_prompt(p)
    assert "{city}" not in world_prompt("Minneapolis, MN")
    # Both blocks together must clear the 512-token minimum for Haiku 5.5 caching (~4 chars/token).
    assert len(world_prompt("Minneapolis, MN")) / 4 > 512


def test_relation_labels():
    assert relation_label(RelState()) == "you have never met"
    assert "friends" in relation_label(RelState(familiarity=60))
    assert "rub you the wrong way" in relation_label(RelState(familiarity=40, affinity=-40))


def test_arrival_rate_never_negative_and_seeded_rng_is_stable():
    r = random.Random(1)
    for _ in range(100):
        t = datetime(2026, 10, 19) + timedelta(minutes=r.randint(0, 7 * 24 * 60))
        assert arrival_rate(3, [4, 5], [17, 21], t) >= 0


def _director():
    from app.sim.director import Director

    d = Director(llm=None)
    for i in range(3):
        d.people[f"p{i}"] = PersonState(id=f"p{i}", name=f"P{i} X", short=f"P{i}", display=f"P{i} X", role="patron",
                                        pronouns="they/them", color="#000", persona={"talk": 0.5})
    d.people["b1"] = PersonState(id="b1", name="B One", short="B", display="B One", role="bartender",
                                 pronouns="they/them", color="#000", persona={}, present=True, location="bar")
    return d


def test_full_bar_is_never_chosen_and_has_no_free_stool():
    from app.sim.state import BAR_STOOLS

    d = _director()
    p = d.people["p0"]
    for i in range(BAR_STOOLS):
        q = PersonState(id=f"x{i}", name="X", short="X", display="X", role="patron", pronouns="", color="",
                        persona={}, present=True, stool=i)
        d.people[q.id] = q
    assert d.free_stool() is None
    assert all(d.choose_area(p) != "bar" for _ in range(100))


def test_stools_are_unique_and_prefer_neighbours():
    d = _director()
    d.people["p1"].present, d.people["p1"].stool = True, 5
    assert d.free_stool(near=[5]) in (4, 6)
    assert d.stool_neighbors(d.people["p0"], ["p1"]) is False  # p0 is standing
    d.people["p0"].stool = 7
    assert d.stool_neighbors(d.people["p0"], ["p1"]) is True
    d.people["p0"].stool = 12
    assert d.stool_neighbors(d.people["p0"], ["p1"]) is False


def test_menu_matches_the_supplied_board():
    from app.sim import menu

    assert len(menu.names()) == 52 and len(set(menu.names())) == 52
    assert menu.match("a pint of fallforge please") == "Fallforge"
    assert menu.match("Pina Colada Slushy") == "Piña Colada Slushy"
    assert menu.match("Can I get the Dreamyard?") == "Dreamyard"
    assert menu.match("Pineapple Dreamyard, please") == "Pineapple Dreamyard"  # longest name wins
    assert menu.match("Hazy Daze") is None and menu.match("") is None


def test_everyone_usual_drink_is_on_the_menu_and_world_lists_the_board():
    from app.sim import menu

    for f in ("patrons", "bartenders"):
        for r in yaml.safe_load((HERE / f"{f}.yaml").read_text()):
            if r["id"] == "b4":
                continue  # "whatever is newest on tap, lately X"
            assert menu.match(r["drink"]), (r["id"], r["drink"])
    world = world_prompt("Minneapolis, MN")
    assert all(n in world for n in menu.names())
    assert world == world_prompt("Minneapolis, MN")  # byte-stable for caching


def test_next_open_and_launch_time():
    from app.sim.clock import launch_time, next_open

    assert next_open(datetime(2026, 10, 19, 14, 0)) == datetime(2026, 10, 19, 15, 0)
    assert next_open(datetime(2026, 10, 19, 23, 30)) == datetime(2026, 10, 20, 15, 0)
    assert next_open(datetime(2026, 10, 24, 0, 30)) == datetime(2026, 10, 24, 11, 0)  # Saturday, just after Friday midnight
    assert next_open(datetime(2026, 10, 25, 21, 30)) == datetime(2026, 10, 26, 15, 0)
    # Closed overnight: skip to ten minutes before opening. Close to opening or open: keep the saved time.
    assert launch_time(datetime(2026, 10, 20, 0, 13)) == datetime(2026, 10, 20, 14, 50)
    assert launch_time(datetime(2026, 10, 19, 14, 40)) == datetime(2026, 10, 19, 14, 40)
    assert launch_time(datetime(2026, 10, 19, 19, 0)) == datetime(2026, 10, 19, 19, 0)


def test_ordering_is_a_channel_but_not_a_place_to_hang_out():
    from app.sim.state import CHANNEL_DESC, CHANNELS, LOC_DESC, LOCATIONS

    assert "ordering" in CHANNELS and "ordering" not in LOCATIONS
    assert all(c in CHANNEL_DESC for c in CHANNELS)
    assert "ordering" in LOC_DESC and all(loc in LOC_DESC for loc in LOCATIONS)


def test_clock_cap_and_skip():
    c = SimClock(start=datetime(2026, 10, 19, 15, 0), speed=240)
    assert c.effective == 240
    c.set_cap(40)
    assert c.effective == 40 and c.speed == 240
    c.set_cap(None)
    assert c.effective == 240
    c.skip_to(datetime(2026, 10, 20, 14, 50))
    assert datetime(2026, 10, 20, 14, 50) <= c.now() < datetime(2026, 10, 20, 15, 0)
    c.skip_to(datetime(2026, 10, 19, 1, 0))  # never backwards
    assert c.now() >= datetime(2026, 10, 20, 14, 50)


def test_governor_holds_speed_to_what_the_model_can_afford():
    d = _director()
    d.latency = 1.5
    d.govern()
    assert d.clock.cap == 40  # 60 sim seconds per 1.5 real seconds
    d.latency = 0.01
    d.govern()
    assert d.clock.cap is None
    d.latency = 30
    d.govern()
    assert d.clock.cap == 5  # clamped


def test_crowd_control_is_clamped_and_reported():
    d = _director()
    d.control("crowd", crowd=2.5)
    assert d.crowd == 2.5 and d.clock_event()["crowd_level"] == 2.5
    d.control("crowd", crowd=9)
    assert d.crowd == 3.0


def test_overnight_skip_only_when_closed_empty_and_idle():
    import asyncio

    d = _director()
    d.clock = SimClock(start=datetime(2026, 10, 22, 23, 20), speed=1)  # Thursday, closed since 11pm
    d.opened_day = d.closed_day = "2026-10-22"
    asyncio.run(d.tick())
    assert d.clock.now() >= datetime(2026, 10, 23, 13, 50)  # Friday opens at 2pm
    d.clock = SimClock(start=datetime(2026, 10, 22, 23, 20), speed=1)
    d.people["p0"].present = True
    asyncio.run(d.tick())
    assert d.clock.now() < datetime(2026, 10, 23, 0, 0)


def _patrons_yaml():
    return yaml.safe_load((HERE / "patrons.yaml").read_text())


NOW = datetime(2026, 10, 19, 16)


def _god_people():
    people = _patrons_yaml()
    people = people["patrons"] if isinstance(people, dict) else people
    return [{"id": p["id"], "short": short_name(p["name"]), "persona": p} for p in people]


def _god(text="The stock market crashed today", reach=3, div=2, stances=None, now=NOW):
    from app.sim import god

    a = {"reach": reach, "divisiveness": div, "sides": ["for it", "against it"], "source": "llm", "reason": "", "stances": stances or {}}
    return god.build(text, a, now)


def test_god_heuristic_scores_the_examples():
    from app.sim import god

    people = _god_people()

    def score(text):
        a = god.heuristic(text, people)
        return a["reach"], a["divisiveness"]

    regular_game = score("The Twins won a regular season game")
    politician_remark = score("A politician said something odd on the radio")
    championship = score("The local team won the championship")
    crash = score("The stock market crashed today")
    war = score("The US is going to war")
    trans = score("Fierce fight over trans athletes in school sports")
    assert regular_game == (1, 1) and politician_remark[0] == 1
    assert championship == (5, 2) and crash == (5, 2)
    assert war == (5, 5) and trans[1] == 5 and trans[0] >= 4

    def heat(reach_div):
        return god.heat(_god(reach=reach_div[0], div=reach_div[1]), NOW)

    assert heat(regular_game) < heat(championship) < heat(war)
    assert heat(politician_remark) < heat(crash)


def test_god_stances_split_with_divisiveness():
    from app.sim import god

    people = _god_people()
    event = "Something that reaches everyone"
    calm = god.heuristic_stances(event, 5, 1, people)
    assert calm == god.heuristic_stances(event, 5, 1, people)  # stable
    split = god.heuristic_stances(event, 5, 5, people)

    def share(stances, key):
        return sum(v == key for v in stances.values()) / len(stances)

    assert share(split, "pushback") > share(calm, "pushback") + 0.15
    assert share(calm, "feels") > share(split, "feels") - 0.05 and share(calm, "feels") > 0.45
    assert share(split, "shrug") < share(calm, "shrug")
    assert set(calm.values()) | set(split.values()) <= set(god.STANCE_KEYS)
    contrarian = [p for p in people if "devil's advocate" in str(p["persona"].get("politics", "")).lower()]
    assert contrarian and all(god.stance(_god(event, 5, 3), p["id"], p["persona"]) in god.STANCE_KEYS for p in contrarian)


def test_low_reach_events_only_matter_to_those_with_a_stake():
    from app.sim import god

    people = _god_people()
    stances = god.heuristic_stances("The Twins won a regular season game", 1, 1, people)
    fans = [p for p in people if "twins" in " ".join(p["persona"].get("interests", [])).lower()]
    rest = [p for p in people if p not in fans]
    assert fans

    def shrug(group):
        return sum(stances[p["id"]] == "shrug" for p in group) / len(group)

    assert shrug(fans) < 0.3 and shrug(rest) > 0.65


def test_assessed_stances_win_over_the_hash_and_gaps_fall_back():
    from app.sim import god

    g = _god(reach=4, div=4, stances={"p01": "pushback"})
    persona = {"talk": 0.5}
    assert god.stance(g, "p01", persona) == "pushback"
    assert god.stance(g, "p02", persona) in god.STANCE_KEYS  # not in the assessment: stable fallback
    assert god.stance(g, "p02", persona) == god.stance(g, "p02", persona)


def test_assess_uses_the_model_and_falls_back_when_it_cannot():
    import asyncio

    from app.sim import god

    people = _god_people()
    ids = [p["id"] for p in people]

    class Good:
        async def classify(self, event, roster):
            assert ids[0] in roster
            return {"reach": 9, "divisiveness": 4, "sides": ["pro", "anti"], "reason": "big", "people": [
                {"id": ids[0], "stance": "feels"}, {"id": ids[1], "stance": "bogus"}, {"id": "nobody", "stance": "shrug"}]}

    class Broken:
        async def classify(self, event, roster):
            return {"reach": 3}

    class Offline:
        async def classify(self, event, roster):
            return None

    a = asyncio.run(god.assess(Good(), "Something happened", people))
    assert (a["reach"], a["divisiveness"], a["sides"], a["source"]) == (5, 4, ["pro", "anti"], "llm")  # reach clamped
    assert a["stances"] == {ids[0]: "feels"}
    for llm in (Broken(), Offline(), None):
        b = asyncio.run(god.assess(llm, "Something happened", people))
        assert b["source"] == "heuristic" and set(b["stances"]) == set(ids)


def test_build_applies_sliders_and_reflows_heuristic_stances():
    from app.sim import god

    people = _god_people()
    a = god.heuristic("The Twins won a regular season game", people)
    same = god.build("t", a, NOW, people=people)
    assert same["stances"] == a["stances"] and same["half_life_h"] == god.HALF_LIFE[a["reach"]]
    bigger = god.build("t", a, NOW, reach=5, div=5, people=people)
    assert (bigger["reach"], bigger["divisiveness"]) == (5, 5) and bigger["stances"] != a["stances"]
    assert bigger["half_life_h"] == god.HALF_LIFE[5]
    assert god.build("t", a, NOW, reach=99, div=-3, people=people)["reach"] == 5


def test_god_buzz_fades_and_dies():
    from app.sim import god

    g = _god(reach=3, div=3)  # half-life 8 sim hours
    assert god.fade(g, NOW) == 1.0 and god.fade(g, None) == 1.0
    assert abs(god.fade(g, NOW + timedelta(hours=8)) - 0.5) < 1e-9
    assert god.chance(g, NOW) == god.CHANCE[3]
    assert god.heat(g, NOW + timedelta(hours=8)) < god.heat(g, NOW)
    assert god.alive(g, NOW) and not god.alive(g, NOW + timedelta(days=3))
    # A big story outlasts a small one.
    small, big = _god(reach=1, div=1), _god(reach=5, div=5)
    later = NOW + timedelta(hours=12)
    assert not god.alive(small, later) and god.alive(big, later)


def test_hot_events_stretch_chats_and_bleed_only_when_hot():
    from app.sim import god

    cold, hot = _god(reach=1, div=1), _god(reach=5, div=5)
    assert god.bleed(cold, NOW) == 0 and god.stretch(cold, NOW) == 0
    assert god.bleed(hot, NOW) > 0.5 and god.stretch(hot, NOW) == 8
    assert god.bleed(hot, NOW + timedelta(days=30)) == 0


def test_legacy_buzz_state_still_loads():
    from app.sim import god

    old = god.normalize({"text": "The big game", "buzz": 0.35}, NOW)
    assert old["text"] == "The big game" and old["reach"] == 2 and old["divisiveness"] == 2
    assert god.stance(old, "p1", {"talk": 0.5}) in god.STANCE_KEYS and god.alive(old, NOW)
    assert god.normalize(None, NOW) is None
    fresh = _god()
    assert god.normalize(fresh, NOW) is fresh


def _scene_for(d, t, p):
    from app.agents.agent import build_turn

    d.persona_text[p.id] = ""
    return build_turn(d, t, p, False)


def _chat(on_event, tid=1, lines=None, turns=0):
    from app.sim.state import ThreadState

    return ThreadState(id=tid, channel="inside-tables", kind="chat", started=NOW, members=["p0", "p1"],
                       ever={"p0": None, "p1": None}, max_turns=8, on_event=on_event, lines=lines or [], turns=turns)


def _scene_director():
    d = _director()
    d.clock = SimClock(start=NOW)
    for pid in ("p0", "p1"):
        d.people[pid].present = True
        d.people[pid].persona["job"] = "welder"
    return d


def test_god_event_shapes_the_scene_only_while_on():
    d = _scene_director()
    p = d.people["p0"]
    assert "Big news" not in _scene_for(d, _chat(True), p).context

    d.god = _god("The stock market crashed today", reach=4, div=2)
    on = _scene_for(d, _chat(True), p)
    assert "The stock market crashed today" in on.context and "How you feel about it" in on.context
    assert "Only bring it up" not in on.context
    assert on.event and on.stance in ("feels", "pushback", "mixed", "shrug") and on.heat > 0

    off_topic = _scene_for(d, _chat(False), p)
    assert "Only bring it up if someone else does" in off_topic.context
    assert off_topic.event == ""

    d.god = None
    assert "Big news" not in _scene_for(d, _chat(True), p).context


def test_scene_tone_follows_how_hot_and_divisive_the_event_is():
    d = _scene_director()
    p = d.people["p0"]
    d.god = _god("The Twins won a game", reach=1, div=1)
    assert "light chatter" in _scene_for(d, _chat(True), p).context
    d.god = _god("The US declared war", reach=5, div=5)
    assert "argue hard" in _scene_for(d, _chat(True), p).context
    d.god = _god("The local team won the title", reach=5, div=2)
    assert "buzzing" in _scene_for(d, _chat(True), p).context
    bt = d.people["b1"]
    d.god = _god("The US declared war", reach=5, div=5)
    assert "stay neutral" in _scene_for(d, _chat(True), bt).context


def test_a_hot_event_pulls_flagging_chats_onto_it():
    d = _scene_director()
    p = d.people["p0"]
    lines = [("speech", "p0", "ok"), ("speech", "p1", "yeah")]  # short lines: the talk is flagging

    def switched(god):
        d.god = god
        out = 0
        for tid in range(1, 41):
            t = _chat(False, tid=tid, lines=list(lines), turns=2)
            _scene_for(d, t, p)
            out += t.on_event
            if t.on_event:
                assert t.max_turns > 8 or god["reach"] + god["divisiveness"] < 6
        return out

    assert switched(_god("The US declared war", reach=5, div=5)) > 10
    assert switched(_god("The Twins won a game", reach=1, div=1)) == 0
    assert switched(_god("The US declared war", reach=5, div=5, now=NOW - timedelta(days=60))) == 0  # long forgotten


def test_new_chats_follow_reach_and_who_cares():
    d = _scene_director()
    d.god = _god(reach=3, div=3, stances={"p0": "feels", "p1": "shrug", "p2": "shrug"})

    class Rng:
        def random(self):
            return 0.4

    d.rng = Rng()
    caring, indifferent = _chat(False), _chat(False)
    indifferent.members = ["p1", "p2"]
    d.roll_event(caring)
    d.roll_event(indifferent)
    assert caring.on_event and caring.max_turns > 8  # 0.4 < 0.5; hot enough to stretch
    assert not indifferent.on_event  # 0.4 > 0.5 * 0.4


def _fight(d, stances, div=5):
    d.clock = SimClock(start=NOW)
    for pid in ("p0", "p1"):
        d.people[pid].present = True
    d.god = _god("The US declared war", reach=5, div=div, stances=stances)
    posts, deltas, gone = [], [], []

    async def post(channel, text, speaker=None, kind="speech", thread=None):
        posts.append(text)

    async def apply_delta(a, b, fam, aff, note):
        deltas.append((a, b, aff))

    async def move(p, loc):
        gone.append(("move", p.id))
        return True

    async def depart(p):
        gone.append(("depart", p.id))

    d.post, d.social.apply_delta, d.move, d.depart = post, apply_delta, move, depart
    return posts, deltas, gone


def test_opposing_sides_escalate_until_someone_steps_in_then_someone_leaves():
    import asyncio

    d = _scene_director()
    posts, deltas, gone = _fight(d, {"p0": "feels", "p1": "pushback"})
    t = _chat(True)
    d.threads[t.id] = t
    for i in range(200):
        asyncio.run(d.escalate(t, d.people["p0" if i % 2 == 0 else "p1"]))
        if gone:
            break
    assert any("keep it friendly" in x for x in posts) and t.stepped_in
    assert gone and deltas and all(aff < 0 for _, _, aff in deltas)
    assert any("walks off" in x or "cool off" in x for x in posts)
    assert len(t.members) == 1


def test_same_side_and_mild_disagreements_never_boil_over():
    import asyncio

    d = _scene_director()
    posts, deltas, gone = _fight(d, {"p0": "feels", "p1": "feels"})
    t = _chat(True)
    for i in range(100):
        asyncio.run(d.escalate(t, d.people["p0"]))
    assert t.tension == 0 and not posts and not gone

    d = _scene_director()
    posts, deltas, gone = _fight(d, {"p0": "feels", "p1": "pushback"}, div=2)  # friendly rivalry
    t = _chat(True)
    for i in range(100):
        asyncio.run(d.escalate(t, d.people["p0"]))
    assert t.tension > 1 and not posts and not gone

    t = _chat(False)  # not about the event
    asyncio.run(d.escalate(t, d.people["p0"]))
    assert t.tension == 0


def test_the_buzz_dies_down_on_its_own(monkeypatch):
    import asyncio

    d = _scene_director()
    d.god = _god("The Twins won a game", reach=1, div=1)
    cleared = []

    async def clear():
        cleared.append(1)
        d.god = None

    monkeypatch.setattr(d, "clear_god", clear)
    asyncio.run(d.social_step(NOW + timedelta(hours=1), 1.0))
    assert not cleared and d.god
    asyncio.run(d.social_step(NOW + timedelta(days=2), 1.0))
    assert cleared and d.god is None


def test_god_set_and_clear_round_trip(monkeypatch):
    import asyncio

    from app.sim import director as dmod

    saved = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

        async def execute(self, stmt):
            saved.clear()

    async def fake_set_state(s, key, value):
        saved[key] = value

    posts = []

    async def fake_post(channel, text, **kw):
        posts.append(text)

    class Llm:
        calls = 0

        async def classify(self, event, roster):
            Llm.calls += 1
            return {"reach": 4, "divisiveness": 3, "sides": ["elated", "gutted"], "reason": "a title game",
                    "people": [{"id": "p0", "stance": "pushback"}]}

    d = _director()
    d.llm = Llm()
    monkeypatch.setattr(dmod, "Session", FakeSession)
    monkeypatch.setattr(dmod, "set_state", fake_set_state)
    monkeypatch.setattr(d, "post", fake_post)

    a = asyncio.run(d.assess_god("  Local team   won the title "))
    assert a["reach"] == 4 and Llm.calls == 1
    asyncio.run(d.set_god("  Local team   won the title "))
    assert Llm.calls == 1  # the reading is reused
    assert d.god["text"] == "Local team won the title" and (d.god["reach"], d.god["divisiveness"]) == (4, 3)
    assert d.god["stances"] == {"p0": "pushback"}
    assert saved["god"] == d.god
    view = d.clock_event()["god"]
    assert view["text"] == "Local team won the title" and view["sides"] == ["elated", "gutted"] and view["heat"] > 0.5

    asyncio.run(d.set_god("Local team won the title", reach=2, divisiveness=5))  # the user's sliders win
    assert (d.god["reach"], d.god["divisiveness"]) == (2, 5) and Llm.calls == 1
    asyncio.run(d.clear_god())
    assert d.god is None and "god" not in saved and d.clock_event()["god"] is None
    assert len(posts) == 3

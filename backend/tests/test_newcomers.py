import asyncio
import random
from datetime import datetime, timedelta

import yaml

from app.agents.prompts import persona_prompt
from app.seed.loader import HERE, color_for
from app.sim import human, menu, newcomers
from app.sim.clock import SimClock
from app.sim.state import PersonState, RelState, display_name, short_name

NOW = datetime(2026, 10, 22, 18, 0)  # a Thursday evening


def _seeded():
    rows = yaml.safe_load((HERE / "patrons.yaml").read_text()) + yaml.safe_load((HERE / "bartenders.yaml").read_text())
    return {short_name(r["name"]) for r in rows}, {display_name(r["name"]) for r in rows}


# ---------------------------------------------------------------- the data


def test_name_and_pool_data_is_clean():
    n, p = newcomers.names(), newcomers.pools()
    firsts = [f["n"] for f in n["first"]]
    assert len(firsts) == len(set(firsts)) >= 150 and len(n["last"]) == len(set(n["last"])) >= 150
    assert {f["p"] for f in n["first"]} == {"she/her", "he/him", "they/them"}
    seeded_shorts, _ = _seeded()
    assert not {f.lower() for f in firsts} & {s.lower() for s in seeded_shorts}
    for key in ("jobs", "traits", "politics", "interests", "quirks", "voices", "lives", "takes", "avoid", "tics"):
        assert len(p[key]) == len(set(p[key])) >= 14 and all(isinstance(x, str) and x for x in p[key]), key


def test_a_full_roster_of_names_never_collides():
    rng = random.Random(7)
    shorts, displays = _seeded()
    shorts, displays = set(shorts), set(displays)
    for _ in range(110):
        name, pronouns = newcomers.pick_name(rng, shorts, displays)
        assert pronouns in ("she/her", "he/him", "they/them")
        s, d = short_name(name), display_name(name)
        assert s.lower() not in {x.lower() for x in shorts} and d.lower() not in {x.lower() for x in displays}
        shorts.add(s)
        displays.add(d)
    assert len(shorts) == 45 + 110


def test_pick_name_gives_up_cleanly_when_the_pool_is_spent():
    everyone = {f["n"] for f in newcomers.names()["first"]}
    assert newcomers.pick_name(random.Random(1), everyone, set()) is None


def test_colors_are_distinct_hex():
    colors = [color_for(i) for i in range(150)]
    assert len(set(colors)) == 150 and all(len(c) == 7 and c.startswith("#") for c in colors)


# ---------------------------------------------------------------- the skeleton and the person


def test_skeleton_stays_in_range_and_talk_agrees_with_extraversion():
    for seed in range(300):
        s = newcomers.skeleton(random.Random(seed), NOW)
        assert 21 <= s["age"] <= 72 and set(s["big5"]) == set("ocean") and all(1 <= v <= 5 for v in s["big5"].values())
        e, talk = s["big5"]["e"], s["talk"]
        assert (talk < 0.35) if e <= 2 else (0.35 <= talk <= 0.65) if e == 3 else (talk > 0.65)
        assert s["style"] in human.STYLE_TEXT and s["beer"] in human.BEER_TEXT
        assert 1 <= len(s["reasons"]) <= 3 and set(s["reasons"]) <= set(human.REASON_TEXT)
        assert 1 <= len(s["days"]) <= 3 and all(0 <= d <= 6 for d in s["days"])
        lo, hi = s["window"]
        assert 15 <= lo < hi <= 23 and s["pay"] in ("card", "tab") and s["walkin"] is True and s["joined"] == NOW.isoformat()


def _check_persona(p):
    for key in ("job", "politics", "drink", "quirk", "voice", "life"):
        assert isinstance(p[key], str) and p[key], key
    for key in ("traits", "interests", "takes", "tics"):
        assert isinstance(p[key], list) and p[key] and all(isinstance(x, str) and x for x in p[key]), key
    assert isinstance(p["avoid"], list) and menu.match(p["drink"]) == p["drink"]
    person = PersonState(id="n001", name="Ada Quill", short="Ada", display="Ada Quill", role="patron",
                         pronouns="she/her", color="#000", persona=p)
    text = persona_prompt(person)
    assert "YOU ARE Ada Quill" in text and p["takes"][0] in text and "Your life right now" in text


def test_template_personas_are_complete_and_render():
    for seed in range(60):
        rng = random.Random(seed)
        _check_persona(newcomers.fill_template(rng, newcomers.skeleton(rng, NOW)))


def test_validate_repairs_whatever_the_model_sends():
    rng = random.Random(3)
    skel = newcomers.skeleton(rng, NOW)
    good = {"job": "  bus   mechanic ", "traits": ["calm", "wry"], "politics": "pragmatic", "drink": "a lager of some kind",
            "interests": ["kayaking", "chess"], "quirk": "hums", "voice": "slow", "life": "Just moved here.",
            "takes": ["lagers rule"], "avoid": [], "tics": ["says 'anyway'"]}
    out = newcomers.validate(good, skel, random.Random(1))
    assert out["job"] == "bus mechanic" and out["traits"] == ["calm", "wry"] and out["avoid"] == []
    assert out["age"] == skel["age"] and out["big5"] == skel["big5"] and out["walkin"] is True
    _check_persona(out)  # an off-menu drink was replaced by a real one
    for junk in (None, "nope", [], {"job": 5, "traits": "x", "drink": None, "takes": [1, 2], "avoid": "no", "tics": {}},
                 {"job": "x" * 5000, "traits": ["a"] * 50}):
        out = newcomers.validate(junk, skel, random.Random(2))
        _check_persona(out)
        assert len(out["job"]) <= newcomers.MAX_FIELD and len(out["traits"]) <= 4


def test_brief_gives_the_model_the_skeleton_in_words():
    skel = newcomers.skeleton(random.Random(5), NOW)
    text = newcomers.brief("Ada Quill", "she/her", skel, NOW, "Minneapolis, MN", ["welder", "nurse"])
    assert "Ada Quill (she/her)" in text and f"age {skel['age']}" in text and "Thursday" in text
    assert "nurse; welder" in text and "for the first time" in text
    assert not any(ch.isdigit() for ch in human.trait_words({"big5": skel["big5"]}))


# ---------------------------------------------------------------- joining the world


class _FakeSession:
    rows: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, row):
        _FakeSession.rows.append(row)

    async def commit(self):
        pass


def _director(monkeypatch):
    from app.sim import director as dmod
    from tests.test_sim import _director as base

    _FakeSession.rows = []
    monkeypatch.setattr(dmod, "Session", _FakeSession)
    events = []
    monkeypatch.setattr(dmod.bus, "publish", events.append)
    d = base()
    d.clock = SimClock(start=NOW)
    return d, events


def _persona(**extra):
    rng = random.Random(9)
    return newcomers.fill_template(rng, newcomers.skeleton(rng, NOW)) | extra


def test_add_person_registers_everywhere_and_tells_the_ui(monkeypatch):
    d, events = _director(monkeypatch)
    p = asyncio.run(d.add_person("Ada Quill", "she/her", _persona()))
    assert p.id == "n001" and d.people["n001"] is p and "YOU ARE Ada Quill" in d.persona_text["n001"]
    row = _FakeSession.rows[0]
    assert (row.id, row.role, row.name, row.color) == ("n001", "patron", "Ada Quill", p.color) and row.persona == p.persona
    view = events[-1]["person"]
    assert events[-1]["type"] == "person" and view["id"] == "n001" and view["walk_in"] is True and view["visits"] == 0
    q = asyncio.run(d.add_person("Bo Lund", "he/him", _persona()))
    assert q.id == "n002" and q.color != p.color


def test_add_person_refuses_a_name_someone_already_has(monkeypatch):
    d, _ = _director(monkeypatch)
    asyncio.run(d.add_person("Ada Quill", "she/her", _persona()))
    for clash in ("Ada Nowak", "Zed Quill".replace("Zed", "Ada"), "ada quill", "P0 Smith"):
        try:
            asyncio.run(d.add_person(clash, "she/her", _persona()))
        except ValueError:
            continue
        raise AssertionError(f"{clash} should have been refused")
    assert len(_FakeSession.rows) == 1


def test_first_visit_is_only_for_walk_ins_on_their_first_visit(monkeypatch):
    d, _ = _director(monkeypatch)

    async def noop(*a, **k):
        return None

    d.post, d.settle, d.pick_bartender = noop, noop, lambda p: None
    new = asyncio.run(d.add_person("Ada Quill", "she/her", _persona()))
    regular = d.people["p0"]
    regular.persona.update({"stay": 60})
    for who, expect in ((new, True), (regular, False)):
        asyncio.run(d.arrive(who))
        assert who.first_visit is expect and d.visits[who.id]["n"] == 1
    assert "your first time at this taproom" in human.right_now(new, NOW)
    assert "first time" not in human.right_now(regular, NOW)
    new.present = False
    asyncio.run(d.arrive(new))
    assert new.first_visit is False and d.visits[new.id]["n"] == 2

    from app.agents.agent import _register_note

    new.first_visit = True
    assert "new here: welcome them and offer a taster" in _register_note(NOW, new, d.visits[new.id])


# ---------------------------------------------------------------- the walk-in stream


class _Always(random.Random):
    def random(self):
        return 0.0


def _roll(d, monkeypatch, **cfg):
    from app.sim import director as dmod

    for k, v in cfg.items():
        monkeypatch.setattr(dmod.settings, k, v)
    spawned = []
    d.spawn = lambda coro: (spawned.append(1), coro.close())
    d.rng = _Always()
    d.walk_ins(NOW, 5.0)
    return bool(spawned), d


def test_walk_ins_respect_the_switch_the_cap_the_budget_and_a_generation_in_flight(monkeypatch):
    d, _ = _director(monkeypatch)
    assert _roll(d, monkeypatch, newcomers_enabled=True, max_patrons=150)[0] is True
    assert d.generating is True  # held until the newcomer is made, so two are never made at once
    assert _roll(d, monkeypatch)[0] is False
    d.generating = False
    assert _roll(d, monkeypatch, newcomers_enabled=False)[0] is False
    assert _roll(d, monkeypatch, newcomers_enabled=True, max_patrons=3)[0] is False  # p0, p1, p2 fill a cap of 3
    d.check_budget = lambda: True
    assert _roll(d, monkeypatch, max_patrons=150)[0] is False


def test_walk_in_rate_is_a_trickle_that_peaks_on_busy_evenings():
    from app.sim.clock import is_open, open_close
    from app.sim.director import NEWCOMER_DAYS, NEWCOMER_SCALE, NEWCOMER_WINDOW
    from app.sim.schedule import arrival_rate

    def rate(t, per_week=8.0):
        return arrival_rate(per_week / NEWCOMER_SCALE, NEWCOMER_DAYS, NEWCOMER_WINDOW, t)

    total, t = 0.0, datetime(2026, 10, 19)
    while t < datetime(2026, 10, 26):
        if is_open(t) and t < open_close(t)[1] - timedelta(minutes=30):
            total += rate(t) / 4  # per 15 minutes
        t += timedelta(minutes=15)
    assert 7 < total < 9.5  # about eight new faces a week
    assert rate(datetime(2026, 10, 24, 18)) > rate(datetime(2026, 10, 19, 18))  # Saturday beats Monday


class _Llm:
    def __init__(self, reply):
        self.reply, self.briefs = reply, []

    async def persona(self, brief):
        self.briefs.append(brief)
        return self.reply


def _welcome(d, monkeypatch, plus_one=False):
    from app.sim import director as dmod

    arrived, friends = [], []

    async def arrive(p):
        arrived.append(p.id)

    async def befriend(host, guest):
        friends.append((host.id, guest.id))

    d.arrive, d.befriend = arrive, befriend
    monkeypatch.setattr(dmod, "is_open", lambda t: True)
    d.rng = random.Random(4)
    monkeypatch.setattr(dmod, "PLUS_ONE_CHANCE", 2.0 if plus_one else 0.0)
    d.generating = True
    asyncio.run(d.welcome_newcomer())
    return arrived, friends


def test_welcome_newcomer_makes_a_valid_person_from_the_model_reply(monkeypatch):
    d, _ = _director(monkeypatch)
    d.llm = _Llm({"job": "bus mechanic", "traits": ["calm", "wry"], "politics": "pragmatic", "drink": "nonsense",
                  "interests": ["kayaking", "chess"], "quirk": "hums", "voice": "slow", "life": "Just moved here.",
                  "takes": ["lagers rule"], "avoid": [], "tics": ["says anyway"]})
    arrived, _ = _welcome(d, monkeypatch)
    new = d.people[arrived[0]]
    assert arrived == ["n001"] and new.persona["job"] == "bus mechanic" and new.persona["walkin"] is True
    assert menu.match(new.persona["drink"]) == new.persona["drink"] and d.generating is False
    assert new.short in d.llm.briefs[0] and "bus mechanic" not in d.llm.briefs[0]


def test_welcome_newcomer_falls_back_to_the_template_when_there_is_no_model_reply(monkeypatch):
    for llm in (_Llm(None), None):
        d, _ = _director(monkeypatch)
        d.llm = llm
        arrived, _ = _welcome(d, monkeypatch)
        _check_persona(d.people[arrived[0]].persona)
        assert d.generating is False


def test_welcome_newcomer_resets_the_lock_even_when_it_fails_and_can_arrive_with_a_friend(monkeypatch):
    d, _ = _director(monkeypatch)
    d.llm = _Llm(None)
    for q in d.patrons():
        q.present = True
    arrived, friends = _welcome(d, monkeypatch, plus_one=True)
    assert friends == [(friends[0][0], arrived[0])] and friends[0][0] in {"p0", "p1", "p2"}

    d2, _ = _director(monkeypatch)
    d2.llm = _Llm(None)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    d2.add_person = boom
    try:
        _welcome(d2, monkeypatch)
    except RuntimeError:
        pass
    assert d2.generating is False


def test_befriend_makes_them_acquaintances_with_memories(monkeypatch):
    d, _ = _director(monkeypatch)
    deltas, mems, met, posts = [], [], [], []

    async def apply_delta(a, b, fam, aff, note):
        deltas.append((fam, aff, note))

    async def add_memory(pid, ts, text, about, importance=5, kind="event"):
        mems.append((pid, text))

    async def mark_met(a, b, ts):
        met.append((a, b))

    async def post(channel, text, **kw):
        posts.append(text)

    d.social.apply_delta, d.social.add_memory, d.social.mark_met, d.post = apply_delta, add_memory, mark_met, post
    asyncio.run(d.befriend(d.people["p0"], d.people["p1"]))
    assert sum(f for f, _, _ in deltas) == 40 and deltas[0][2] == "P0 brought P1 along"
    assert [p for p, _ in mems] == ["p0", "p1"] and met == [("p0", "p1")] and posts == ["P0 brought P1 along."]


# ---------------------------------------------------------------- scale


def test_the_model_hears_about_everyone_present_and_the_most_frequent_visitors_only(monkeypatch):
    from app.sim.director import GOD_ROSTER

    d, _ = _director(monkeypatch)
    for i in range(100):
        d.people[f"n{i:03d}"] = PersonState(id=f"n{i:03d}", name=f"N{i} X", short=f"N{i}", display=f"N{i} X", role="patron",
                                            pronouns="they/them", color="#000", persona={"freq": i % 5 + 0.1})
    d.people["n099"].present = d.people["n001"].present = True
    ids = [p["id"] for p in d.god_people()]
    assert len(ids) == GOD_ROSTER and {"n099", "n001", "b1"} <= set(ids)
    assert ids.index("n099") < ids.index("n002")  # people in the room come first
    freqs = [d.people[i].persona.get("freq", 2) for i in ids if not d.people[i].present]
    assert freqs == sorted(freqs, reverse=True)


def test_stances_still_exist_for_people_the_model_never_heard_of():
    from app.sim import god

    g = {"text": "Big news", "reach": 4, "divisiveness": 3, "sides": ["a", "b"], "stances": {"p0": "feels"},
         "reason": "", "half_life_h": 24, "set_at": NOW.isoformat()}
    assert god.stance(g, "p0", {}) == "feels"
    assert god.stance(g, "n042", {}) == god.stance(g, "n042", {}) in god.STANCE_KEYS


def test_the_agent_builds_a_missing_persona_instead_of_crashing(monkeypatch):
    from app.agents.agent import build_turn
    from tests.test_sim import _chat

    d, _ = _director(monkeypatch)
    p = asyncio.run(d.add_person("Ada Quill", "she/her", _persona()))
    d.people["p0"].present = p.present = True
    d.people["p0"].persona["job"] = "welder"
    del d.persona_text[p.id]
    t = _chat(False)
    t.members = ["p0", p.id]
    assert "YOU ARE Ada Quill" in build_turn(d, t, p, False).persona
    assert p.id in d.persona_text


def test_relationship_state_defaults_for_a_stranger_pair():
    assert RelState().familiarity == 0

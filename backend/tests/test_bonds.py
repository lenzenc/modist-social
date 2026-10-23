import asyncio
import random
from datetime import datetime, timedelta

import yaml

from app.agents.memory import bond_step, summarize_thread
from app.llm.mock import MockLLM
from app.seed.loader import HERE
from app.sim import bonds
from app.sim.clock import SimClock
from app.sim.social import relation_label
from app.sim.state import MemoryRec, PersonState, RelState, ThreadState

NOW = datetime(2026, 10, 21, 20, 0)


def _p(pid="p0", age=30, role="patron", **persona):
    return PersonState(id=pid, name=f"{pid.upper()} X", short=pid.upper(), display=f"{pid.upper()} X", role=role,
                       pronouns="they/them", color="#000", persona={"age": age, **persona})


def _rel(bond, fam=50, aff=40, since=NOW - timedelta(days=5), **kw):
    return RelState(kind="friends", familiarity=fam, affinity=aff, bond=bond, bond_since=since, **kw)


class _Rng:
    def __init__(self, v):
        self.v = v

    def random(self):
        return self.v

    def uniform(self, lo, hi):
        return lo


# ---------------------------------------------------------------- starting points


def test_every_seeded_relationship_maps_to_a_bond():
    rows = yaml.safe_load((HERE / "relationships.yaml").read_text())
    got = {r["kind"]: bonds.from_seed(r["kind"], r["familiarity"], r["affinity"]) for r in rows}
    assert all(b in bonds.BONDS for b in got.values())
    assert got["close friends"] == "close_friends" and got["old friends"] == "close_friends"
    assert got["adversaries"] == got["friendly rivals"] == "rivals"
    assert got["ex-partners"] == "ex" and got["mentor"] == "mentor"
    assert bonds.from_seed("anything", 0, 0) == "stranger"
    assert bonds.from_seed("coworkers", 20, 5) == "acquaintance"


def test_attached_reads_the_persona_prose():
    assert bonds.attached({"life": "His wife wants the kitchen done before Thanksgiving."})
    assert not bonds.attached({"life": "A widow of a homebrewer, trying not to dwell on her husband's death."})
    assert not bonds.attached({"life": "Divorce finalized last spring."})
    assert not bonds.attached({})


# ---------------------------------------------------------------- moves


def test_acquaintances_become_friends_at_the_threshold_and_not_below():
    a, b = _p("p0"), _p("p1")
    assert bonds.step(_rel("acquaintance", 44, 40), a, b, "none", "", 2, NOW, _Rng(0.9)) is None
    assert bonds.step(_rel("acquaintance", 45, 29), a, b, "none", "", 2, NOW, _Rng(0.9)) is None
    assert bonds.step(_rel("acquaintance", 45, 30), a, b, "none", "", 2, NOW, _Rng(0.9)).new == "friends"


def test_close_friendship_needs_a_week():
    a, b = _p("p0"), _p("p1")
    young = _rel("friends", 80, 60, met_at=NOW - timedelta(days=3))
    old = _rel("friends", 80, 60, met_at=NOW - timedelta(days=9))
    assert bonds.step(young, a, b, "none", "", 2, NOW, _Rng(0.9)) is None
    assert bonds.step(old, a, b, "none", "", 2, NOW, _Rng(0.9)).new == "close_friends"


def test_a_fight_between_friends_is_a_falling_out_that_remembers_what_they_were():
    a, b = _p("p0"), _p("p1")
    ch = bonds.step(_rel("close_friends", 80, 60), a, b, "fight", "p0", -5, NOW, _Rng(0.9))
    assert ch.new == "falling_out" and ch.until and bonds.FALLOUT_DAYS[0] <= (ch.until - NOW).days <= bonds.FALLOUT_DAYS[1]
    assert bonds.step(_rel("close_friends", 80, 60), a, b, "fight", "p0", -2, NOW, _Rng(0.9)) is None  # a mild spat


def test_apology_makes_up_to_the_prior_bond():
    a, b = _p("p0"), _p("p1")
    rel = _rel("falling_out", prior="couple")
    assert bonds.step(rel, a, b, "apology", "p0", 3, NOW, _Rng(0.9)).new == "couple"
    assert bonds.step(rel, a, b, "none", "", 1, NOW, _Rng(0.9)) is None


def test_falling_out_that_never_heals_decays_by_what_it_was():
    rel = _rel("falling_out", since=NOW - timedelta(days=10), bond_until=NOW - timedelta(days=1), prior="couple")
    assert bonds.offscreen(rel, NOW, _Rng(0.9)).new == "ex"
    rel = _rel("falling_out", aff=10, since=NOW - timedelta(days=10), bond_until=NOW - timedelta(days=1), prior="friends")
    assert bonds.offscreen(rel, NOW, _Rng(0.9)).new == "acquaintance"
    rel = _rel("falling_out", aff=-40, since=NOW - timedelta(days=10), bond_until=NOW - timedelta(days=1), prior="friends")
    assert bonds.offscreen(rel, NOW, _Rng(0.9)).new == "rivals"
    fresh = _rel("falling_out", since=NOW - timedelta(days=1), bond_until=NOW + timedelta(days=6), prior="friends")
    assert bonds.offscreen(fresh, NOW, _Rng(0.0)) is None  # too soon to reconcile
    mid = _rel("falling_out", since=NOW - timedelta(days=4), bond_until=NOW + timedelta(days=6), prior="friends")
    assert bonds.offscreen(mid, NOW, _Rng(0.0)).new == "friends"


def test_rivals_form_from_bad_blood_and_can_bury_it():
    a, b = _p("p0"), _p("p1")
    assert bonds.step(_rel("acquaintance", 30, -25), a, b, "none", "", -3, NOW, _Rng(0.9)).new == "rivals"
    assert bonds.step(_rel("acquaintance", 29, -25), a, b, "none", "", -3, NOW, _Rng(0.9)) is None
    assert bonds.step(_rel("rivals", 40, 15), a, b, "none", "", 2, NOW, _Rng(0.9)).new == "acquaintance"


def test_a_crush_needs_adult_patrons_close_in_age_and_a_lucky_flirt():
    rel = _rel("friends", 50, 40)
    a, b = _p("p0", 30), _p("p1", 34)
    ch = bonds.step(rel, a, b, "flirt", "p0", 2, NOW, _Rng(0.0))
    assert ch.new == "crush" and ch.by == "p0"
    assert bonds.step(rel, a, b, "flirt", "p0", 2, NOW, _Rng(0.9)) is None  # unlucky
    assert bonds.step(rel, a, _p("p1", 55), "flirt", "p0", 2, NOW, _Rng(0.0)) is None  # too far apart
    assert bonds.step(rel, _p("p0", 19), _p("p1", 20), "flirt", "p0", 2, NOW, _Rng(0.0)) is None  # too young
    bartender = _p("b1", 30, role="bartender")
    assert bonds.step(_rel("friends", 50, 40), a, bartender, "flirt", "p0", 2, NOW, _Rng(0.0)) is None


def test_attached_people_catch_feelings_far_less_often():
    rel = _rel("friends", 50, 40)
    free, taken = _p("p0", 30), _p("p0", 30, life="His wife is on a cruise without him.")
    other = _p("p1", 32)
    trials = 2000

    def crushes(a):
        rng = random.Random(7)
        return sum(1 for _ in range(trials) if bonds.step(rel, a, other, "flirt", "p0", 2, NOW, rng))

    assert crushes(free) > 3 * crushes(taken) > 0


def test_a_crush_turns_into_a_couple_when_the_other_flirts_back():
    a, b = _p("p0"), _p("p1")
    rel = _rel("crush", 40, 40, crush_by="p0")
    assert bonds.step(rel, a, b, "flirt", "p0", 2, NOW, _Rng(0.9)) is None  # the crusher flirting again changes nothing
    assert bonds.step(rel, a, b, "flirt", "p1", 2, NOW, _Rng(0.9)).new == "couple"
    deep = _rel("crush", 60, 55, crush_by="p0")
    assert bonds.step(deep, a, b, "confided", "p1", 3, NOW, _Rng(0.9)).new == "couple"


def test_a_crush_fades_and_exes_move_on():
    old = _rel("crush", since=NOW - timedelta(days=22), prior="friends", crush_by="p0")
    assert bonds.offscreen(old, NOW, _Rng(0.9)).new == "friends"
    assert bonds.offscreen(_rel("crush", since=NOW - timedelta(days=5)), NOW, _Rng(0.9)) is None
    assert bonds.offscreen(_rel("ex", since=NOW - timedelta(days=31)), NOW, _Rng(0.9)).new == "acquaintance"


def test_advice_from_someone_much_older_makes_a_mentor():
    young, old = _p("p0", 24), _p("p1", 58)
    ch = bonds.step(_rel("friends", 50, 40), young, old, "advice", "p1", 2, NOW, _Rng(0.9))
    assert ch.new == "mentor" and ch.by == "p1"
    assert bonds.step(_rel("friends", 50, 40), _p("p0", 40), _p("p1", 45), "advice", "p1", 2, NOW, _Rng(0.9)) is None


def test_staff_get_friendlier_but_never_fall_out_or_pair_off():
    guest, bt = _p("p0"), _p("b1", role="bartender")
    assert bonds.step(_rel("friends", 50, -5), guest, bt, "fight", "p0", -6, NOW, _Rng(0.0)) is None
    assert bonds.step(_rel("acquaintance", 45, 30), guest, bt, "none", "", 2, NOW, _Rng(0.9)).new == "friends"


def test_a_pair_changes_at_most_once_a_day():
    a, b = _p("p0"), _p("p1")
    just = _rel("acquaintance", 60, 60, since=NOW - timedelta(hours=3))
    assert bonds.step(just, a, b, "none", "", 2, NOW, _Rng(0.9)) is None
    assert bonds.step(_rel("acquaintance", 60, 60, since=NOW - timedelta(days=2)), a, b, "none", "", 2, NOW, _Rng(0.9)).new == "friends"


# ---------------------------------------------------------------- behaviour


def test_who_avoids_whom():
    assert bonds.avoids(_rel("falling_out"), NOW)
    assert bonds.avoids(_rel("ex", since=NOW - timedelta(days=2)), NOW)
    assert not bonds.avoids(_rel("ex", since=NOW - timedelta(days=20)), NOW)
    assert not bonds.avoids(_rel("rivals", aff=-60), NOW)  # rivals seek each other out
    assert bonds.avoids(_rel("acquaintance", aff=-35), NOW)
    assert not bonds.avoids(_rel("friends", aff=40), NOW)


def test_join_and_follow_ordering():
    w = {b: bonds.join_weight(_rel(b)) for b in bonds.BONDS}
    assert w["couple"] > w["close_friends"] > w["friends"] > w["ex"]
    assert bonds.join_weight(_rel("acquaintance")) == 1.0
    f = {b: bonds.follow_chance(_rel(b), "unwind") for b in ("couple", "close_friends", "friends", "rivals", "ex", "falling_out")}
    assert f["couple"] > f["close_friends"] > f["friends"] > f["rivals"] > f["ex"] > f["falling_out"] == 0.0
    assert bonds.follow_chance(_rel("friends"), "catch_up") > bonds.follow_chance(_rel("friends"), "unwind")
    assert bonds.follow_chance(_rel("close_friends"), "unwind", good_news=True) > f["close_friends"]
    assert bonds.follow_chance(_rel("couple"), "catch_up", good_news=True) <= 0.95


def test_date_night_is_for_couples_only():
    assert bonds.date_night(_rel("couple"), _Rng(0.0))
    assert not bonds.date_night(_rel("couple"), _Rng(0.9))
    assert not bonds.date_night(_rel("friends"), _Rng(0.0))


def test_scene_hints_and_the_crush_target_is_kept_in_the_dark():
    crush = _rel("crush", crush_by="p0")
    assert "crush on Ann" in bonds.scene_hint(crush, "p0", "Ann", False, NOW, _Rng(0.9))
    assert "wrong" in bonds.scene_hint(crush, "p0", "Ann", True, NOW, _Rng(0.9))
    assert bonds.scene_hint(crush, "p1", "Bob", False, NOW, _Rng(0.9)) == ""
    fo = _rel("falling_out", since=datetime(2026, 10, 18))
    assert "fallen out since Sunday" in bonds.scene_hint(fo, "p0", "Ann", False, NOW, _Rng(0.9))
    assert "clear the air" in bonds.scene_hint(fo, "p0", "Ann", False, NOW, _Rng(0.0))
    assert bonds.scene_hint(_rel("friends"), "p0", "Ann", False, NOW, _Rng(0.0)) == ""
    assert "looks up to you" in bonds.scene_hint(_rel("mentor", mentor_id="p0"), "p0", "Ann", False, NOW, _Rng(0.9))
    assert "look up to Ann" in bonds.scene_hint(_rel("mentor", mentor_id="p1"), "p0", "Ann", False, NOW, _Rng(0.9))


def test_prompt_labels_follow_the_bond():
    assert "falling-out on Sunday" in relation_label(_rel("falling_out", since=datetime(2026, 10, 18)))
    assert relation_label(_rel("couple", since=datetime(2026, 10, 1))).startswith("together since Oct 1")
    assert relation_label(RelState(kind="friends", familiarity=60, bond="friends")) == "friends"


# ---------------------------------------------------------------- the scorecard


def test_drama_bands():
    assert bonds.drama(3, 10, 7)["band"] == "none"  # too little to judge
    assert bonds.drama(0, 60, 7)["band"] == "red"  # nothing ever changes
    assert bonds.drama(0, 60, 1)["band"] == "amber"
    assert bonds.drama(30, 100, 7)["band"] == "red"  # a soap opera
    assert bonds.drama(4, 100, 7)["band"] == "green"


# ---------------------------------------------------------------- wiring


class _World:
    """A Director whose social layer records bond changes and memories instead of writing to the database."""

    def __init__(self, a=None, b=None, rel=None):
        from tests.test_sim import _director

        self.d = _director()
        self.d.clock = SimClock(start=NOW)
        self.d.people["p0"].persona.update({"age": 30, **(a or {})})
        self.d.people["p1"].persona.update({"age": 32, **(b or {})})
        self.d.rng = _Rng(0.0)
        self.changes, self.mems = [], []
        if rel:
            self.d.social.rels[("p0", "p1")] = rel
        s = self.d.social

        async def set_bond(a, b, ch, now):
            r = s.rels.setdefault(("p0", "p1"), RelState())
            old = r.bond or "stranger"
            self.changes.append((old, ch.new))
            r.bond, r.bond_since, r.bond_until = ch.new, now, ch.until
            return old

        async def add_memory(pid, ts, text, about, importance=5, kind="event"):
            self.mems.append((pid, text, importance, kind))
            return MemoryRec(ts, text, about, importance, kind)

        s.set_bond, s.add_memory = set_bond, add_memory


def test_a_fight_becomes_a_falling_out_with_memories_and_a_nudge_to_make_up():
    w = _World(rel=_rel("close_friends", 80, 60))
    asyncio.run(bond_step(w.d, "p0", "p1", "fight", "p0", -5, "snapped about the bill"))
    assert w.changes == [("close_friends", "falling_out")]
    by_person = {p: [t for q, t, _, k in w.mems if q == p and k == "event"] for p in ("p0", "p1")}
    assert "falling-out" in by_person["p0"][0] and "snapped about the bill" in by_person["p1"][0]
    assert [(p, k) for p, _, _, k in w.mems if k == "followup"] == [("p0", "followup"), ("p1", "followup")]
    assert all(imp >= 8 for _, _, imp, k in w.mems if k == "event")


def test_only_the_one_with_the_crush_remembers_it():
    w = _World(rel=_rel("friends", 50, 40))
    asyncio.run(bond_step(w.d, "p0", "p1", "flirt", "p1", 2))
    assert w.changes == [("friends", "crush")]
    assert [p for p, *_ in w.mems] == ["p1"]


def test_the_room_only_forms_so_much_romance_in_a_day():
    w = _World(rel=_rel("friends", 50, 40))
    asyncio.run(bond_step(w.d, "p0", "p1", "flirt", "p0", 2))
    assert w.d.romance_ok(NOW) is False
    w.d.social.rels[("p0", "p1")] = _rel("friends", 50, 40)
    w.changes.clear()
    asyncio.run(bond_step(w.d, "p0", "p1", "flirt", "p0", 2))
    assert w.changes == []  # capped
    assert w.d.romance_ok(NOW + timedelta(days=1))


def test_mock_summaries_carry_valid_moments_and_are_repeatable():
    llm = MockLLM()
    roster = "Ann | Bob: acquaintances\nBob | Ann: acquaintances"
    seen = set()
    for i in range(200):
        out = asyncio.run(llm.summarize(f"Ann: hi {i}\nBob: hey", roster))
        for r in out["relationships"]:
            assert r["moment"] in bonds.MOMENTS
            assert (r["by"] == "") == (r["moment"] == "none")
            seen.add(r["moment"])
    assert seen == set(bonds.MOMENTS)
    assert asyncio.run(llm.summarize("Ann: hi\nBob: hey", roster)) == asyncio.run(llm.summarize("Ann: hi\nBob: hey", roster))


def test_summary_moment_reaches_the_bond_step():
    w = _World(rel=_rel("close_friends", 80, 60))
    deltas = []

    async def apply_delta(a, b, fam, aff, note):
        deltas.append((a, b))

    w.d.social.apply_delta = apply_delta

    class Llm:
        async def summarize(_, transcript, roster):
            return {"memories": [], "relationships": [
                {"a": "P0", "b": "P1", "familiarity_delta": 1, "affinity_delta": -6, "note": "", "moment": "fight", "by": "P0"}]}

    w.d.llm = Llm()
    t = ThreadState(id=1, channel="bar", kind="chat", started=NOW, members=[], ever={"p0": None, "p1": None}, max_turns=8,
                    lines=[("speech", s, "x") for s in ("p0", "p1", "p0", "p1")])
    asyncio.run(summarize_thread(w.d, t))
    assert deltas == [("p0", "p1")] and w.changes == [("close_friends", "falling_out")]

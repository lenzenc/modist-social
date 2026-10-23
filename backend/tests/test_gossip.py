import asyncio
import random
from datetime import datetime, timedelta

from app.agents import memory
from app.llm.mock import MockLLM, _distort
from app.llm.types import TurnRequest
from app.sim import gossip
from app.sim.state import MemoryRec

NOW = datetime(2026, 10, 21, 20, 0)


def _rec(text="P2 is behind on rent.", about=("p2",), id=1, **kw):
    return MemoryRec(NOW, text, list(about), 5, "event", id, **kw)


# ---------------------------------------------------------------- passing it on


def test_a_retelling_loses_accuracy_and_more_so_when_the_teller_is_drunk():
    parent = _rec(id=7, accuracy=100, confidence=90)
    sober = [gossip.retell(parent, "P2 is way behind on rent.", "fairly", 0.0, 60, random.Random(i)) for i in range(50)]
    drunk = [gossip.retell(parent, "P2 is way behind on rent.", "fairly", 0.8, 60, random.Random(i)) for i in range(50)]
    assert all(r["hops"] == 1 and r["origin_id"] == 7 for r in sober)
    assert all(r["accuracy"] < 100 for r in sober)
    assert sum(r["accuracy"] for r in drunk) < sum(r["accuracy"] for r in sober)


def test_a_faithful_retelling_of_a_shaky_source_is_still_doubted():
    shaky = _rec(id=7, confidence=30, accuracy=60, origin_id=3, hops=2)
    got = gossip.retell(shaky, shaky.text, "certain", 0.0, 60, random.Random(0))
    assert got["origin_id"] == 3 and got["hops"] == 3
    assert got["confidence"] < 90 and got["accuracy"] < 60  # farther from the truth every hop


def test_low_credibility_tellers_are_believed_less():
    parent = _rec(id=7)
    hi = gossip.retell(parent, parent.text, "fairly", 0.0, 90, random.Random(0))["confidence"]
    lo = gossip.retell(parent, parent.text, "fairly", 0.0, 10, random.Random(0))["confidence"]
    assert lo < hi


def test_find_parent_needs_a_shared_subject_and_prefers_what_the_teller_had_in_mind():
    a = _rec("P2 is behind on rent.", id=1)
    b = _rec("P2 is moving across town.", id=2)
    other = _rec("P1 got a speeding ticket.", about=("p1",), id=3)
    assert gossip.find_parent([a, b, other], [2], {"p2"}, "P2 is behind on rent.") is b
    assert gossip.find_parent([a, b, other], [], {"p2"}, "P2 is behind on rent.") is a
    assert gossip.find_parent([other], [3], {"p2"}, "P2 is behind on rent.") is None  # a fresh claim
    assert gossip.find_parent([_rec(id=None)], [], {"p2"}, "anything") is None


def test_fresh_claims_are_mostly_right_but_drunks_and_unreliable_tellers_get_more_wrong():
    def wrong(buzz, cred):
        return sum(gossip.verdict(gossip.fresh_claim(buzz, cred, random.Random(i))) == "false" for i in range(400))

    assert 0 < wrong(0.0, 60) < 120
    assert wrong(0.8, 60) > wrong(0.0, 60)
    assert wrong(0.0, 10) > wrong(0.0, 60)


def test_verdict_bands():
    assert [gossip.verdict(a) for a in (100, 70, 69, 40, 39, 0)] == ["true", "true", "garbled", "garbled", "false", "false"]


def test_a_listener_who_knows_better_pushes_back():
    mine = _rec(id=5, origin_id=9, accuracy=100, confidence=85)
    assert gossip.correction([mine], 9, 55) is mine
    assert gossip.correction([mine], 9, 80) is None  # close enough
    assert gossip.correction([mine], 4, 10) is None  # a different rumor
    assert gossip.correction([_rec(id=6, origin_id=9, accuracy=100, confidence=30)], 9, 10) is None  # unsure of their own


def test_credibility_is_clamped():
    creds = {}
    assert gossip.get_cred(creds, "p0") == gossip.CRED_START
    gossip.bump_cred(creds, "p0", -500)
    gossip.bump_cred(creds, "p1", 500)
    assert creds == {"p0": 0, "p1": 100}


# ---------------------------------------------------------------- what the model sees


def test_the_label_says_where_it_came_from_and_never_how_true_it_is():
    names = {"p0": "Dana", "p2": "Rick"}
    rec = _rec("Rick is quitting.", id=4, source_id="p0", confidence=40, accuracy=12, origin_id=4)
    text = gossip.label(rec, names, set())
    assert text == "heard from Dana, not sure"
    assert "12" not in text and "accura" not in text
    assert gossip.label(rec, names, {"p2"}) == "heard from Dana, not sure, Rick is right here"
    assert gossip.label(_rec(), names, set()) == ""  # first-hand
    assert gossip.hazy(rec) and not gossip.hazy(_rec())


def test_the_confrontation_gets_harsher_the_less_true_it_was():
    rng = random.Random(0)
    false, garbled, true = (gossip.confrontation(k, rng) for k in ("false", "garbled", "true"))
    assert false.fight and not garbled.fight and not true.fight
    assert false.aff <= -5 and false.cred < 0 < true.cred
    assert false.aff < garbled.aff <= true.aff < 0 or false.aff < true.aff < 0
    for kind in ("false", "garbled", "true"):
        assert set(gossip.texts(kind, "Dana", "Rick", "Rick is quitting.")) == {"subject", "teller", "listener"}


def test_the_scorecard_counts_chains_with_consequences():
    rows = [{"id": i, "source_id": "p0", "origin_id": o, "hops": h, "accuracy": a}
            for i, (o, h, a) in enumerate([(1, 0, 90), (1, 1, 70), (1, 2, 50), (2, 0, 100), (3, 0, 20)])]
    log = [{"origin": 1, "verdict": "false", "kind": "confront"}]
    got = gossip.spread(rows, log)
    assert got["chains"] == 3 and got["max_hops"] == 2 and got["rumors"] == 5
    assert got["rate"] == 33 and got["band"] == "green" and got["caught_out"] == 1
    assert gossip.spread(rows[:2], [])["band"] == "none"  # too little to judge
    assert gossip.spread(rows, [])["band"] == "red"  # nothing ever lands


# ---------------------------------------------------------------- the mock


def test_the_mock_repeats_a_rumor_with_a_twist_and_the_summary_parses_it_back():
    llm = MockLLM()
    req = TurnRequest(person_id="p0", person_name="Ann", world="", persona="", context="", last_line="hi", rumor=("Rick", ""))
    said = {asyncio.run(llm.speak(req)).say for _ in range(60)}
    heard = next(s for s in said if "I heard about Rick?" in s)
    out = asyncio.run(llm.summarize(f"Ann: {heard}\nBob: oh?\nCy: no way", "Ann | Bob: x\nBob | Ann: x\nCy | Ann: x"))
    got = [m for m in out["memories"] if m["heard_from"]]
    assert {m["person"] for m in got} == {"Bob", "Cy"}
    assert all(m["heard_from"] == "Ann" and m["about"] == ["Rick"] and m["sure"] in ("certain", "fairly", "doubtful") for m in got)
    assert all(not m["heard_from"] for m in out["memories"] if m not in got)
    assert _distort("Rick is thinking about quitting.", random.Random(0)) != "Rick is thinking about quitting."


# ---------------------------------------------------------------- wiring


class _World:
    """A Director whose social layer keeps memories and relationship changes in RAM instead of Postgres."""

    def __init__(self):
        from app.sim.clock import SimClock
        from tests.test_sim import _director

        self.d = _director()
        self.d.clock = SimClock(start=NOW)
        self.d.rng = random.Random(3)
        self.deltas, self.fights, self.seq = [], [], 100
        s = self.d.social

        async def add_memory(pid, ts, text, about, importance=5, kind="event", *, source_id="", parent_id=None,
                             origin_id=None, hops=0, confidence=100, accuracy=100):
            self.seq += 1
            rec = MemoryRec(ts, text, about, importance, kind, self.seq, source_id, parent_id, origin_id, hops, confidence, accuracy)
            s.memories.setdefault(pid, []).append(rec)
            return rec

        async def set_provenance(rec, **fields):
            for k, v in fields.items():
                setattr(rec, k, v)

        async def apply_delta(a, b, fam, aff, note):
            self.deltas.append((a, b, aff))

        async def bond_step(d, a, b, moment, by, aff, note=""):
            self.fights.append((a, b, moment, by))

        s.add_memory, s.set_provenance, s.apply_delta = add_memory, set_provenance, apply_delta
        self.real_bond_step, memory.bond_step = memory.bond_step, bond_step

    def close(self):
        memory.bond_step = self.real_bond_step

    def thread(self, told=None):
        from app.sim.state import ThreadState

        return ThreadState(id=1, channel="bar", kind="chat", started=NOW, members=[], max_turns=8,
                           ever={"p0": None, "p1": None, "p2": None}, told=told or {})


def test_a_retold_rumor_is_linked_to_the_tellers_memory_and_gets_a_root():
    w = _World()
    try:
        w.d.social.memories["p0"] = [_rec("P2 is behind on rent.", id=1, confidence=90)]
        m = {"heard_from": "P0", "sure": "fairly"}
        prov = asyncio.run(memory.trace_rumor(w.d, w.thread({"p0": [1]}), "p1", ["p0", "p1"], ["p2"], "P2 is way behind on rent.", m))
        assert prov["source_id"] == "p0" and prov["parent_id"] == 1 and prov["hops"] == 1 and prov["origin_id"] == 1
        assert prov["accuracy"] < 100
        assert w.d.social.memories["p0"][0].origin_id == 1  # the teller's own memory became the root
    finally:
        w.close()


def test_a_claim_with_no_trail_starts_a_chain_and_first_hand_memories_are_untouched():
    w = _World()
    try:
        t = w.thread()
        prov = asyncio.run(memory.trace_rumor(w.d, t, "p1", ["p0", "p1"], ["p2"], "P2 is moving.", {"heard_from": "P0", "sure": "certain"}))
        assert prov["hops"] == 0 and prov["source_id"] == "p0" and "parent_id" not in prov
        assert asyncio.run(memory.trace_rumor(w.d, t, "p1", ["p0", "p1"], ["p2"], "I saw P2.", {"heard_from": "", "sure": "fairly"})) == {}
        assert asyncio.run(memory.trace_rumor(w.d, t, "p1", ["p0", "p1"], ["p2"], "x", {"heard_from": "P1", "sure": "fairly"})) == {}  # self
        assert asyncio.run(memory.trace_rumor(w.d, t, "p1", ["p0", "p1"], [], "x", {"heard_from": "P0", "sure": "fairly"})) == {}  # nobody
    finally:
        w.close()


def test_what_a_drunk_person_confesses_is_true_and_enters_the_grapevine():
    w = _World()
    try:
        w.d.people["p0"].overshared_with = {"p1"}
        prov = asyncio.run(memory.trace_rumor(w.d, w.thread(), "p1", ["p0", "p1"], ["p0"], "P0 cheated on a test.", {"heard_from": "P0", "sure": "certain"}))
        assert prov["accuracy"] == 100 and prov["confidence"] == 90
    finally:
        w.close()


def test_a_listener_who_knows_better_corrects_the_teller():
    w = _World()
    try:
        w.d.social.memories["p0"] = [_rec("P2 is behind on rent.", id=1, accuracy=20, confidence=90, origin_id=1)]
        w.d.social.memories["p1"] = [_rec("P2 is fine on rent.", id=9, accuracy=100, confidence=90, origin_id=1)]
        prov = asyncio.run(memory.trace_rumor(w.d, w.thread({"p0": [1]}), "p1", ["p0", "p1"], ["p2"], "P2 is behind on rent.",
                                              {"heard_from": "P0", "sure": "certain"}))
        assert prov["confidence"] <= 25
        assert gossip.get_cred(w.d.gossip_cred, "p0") == gossip.CRED_START - 3
        assert w.d.gossip_log[-1]["kind"] == "correct"
    finally:
        w.close()


def test_a_false_rumor_reaching_its_subject_costs_the_teller():
    w = _World()
    try:
        t = w.thread()
        rec = MemoryRec(NOW, "P2 is quitting.", ["p2"], 5, "event", 50, "p0", None, 50, 0, 80, 10)
        w.d.social.memories["p1"] = [rec]
        before = w.d.people["p0"].mood
        asyncio.run(memory.settle_rumor(w.d, rec, ["p0", "p1", "p2"], set()))
        assert any(a == "p2" and b == "p0" and aff <= -5 for a, b, aff in w.deltas)
        assert gossip.get_cred(w.d.gossip_cred, "p0") == gossip.CRED_START - 15
        assert w.d.people["p0"].mood < before
        assert w.fights == [("p2", "p0", "fight", "p2")]
        assert any("untrue" in r.text for r in w.d.social.memories["p2"])  # the subject remembers being talked about
        assert any("wasn't true" in r.text for r in w.d.social.memories["p1"] if r is not rec)  # the listener hears it was wrong
        assert rec.confidence <= 20
        assert w.d.gossip_log[-1] == {"day": NOW.date().isoformat(), "origin": 50, "teller": "p0", "subject": "p2",
                                      "verdict": "false", "kind": "confront"}
        # Two listeners hearing the same claim don't double the reckoning.
        n = len(w.deltas)
        asyncio.run(memory.settle_rumor(w.d, rec, ["p0", "p1", "p2"], {("p0", "p2")}))
        assert len(w.deltas) == n
    finally:
        w.close()


def test_a_true_rumor_still_stings_but_raises_the_tellers_standing():
    w = _World()
    try:
        rec = MemoryRec(NOW, "P2 is quitting.", ["p2"], 5, "event", 50, "p0", None, 50, 0, 80, 95)
        asyncio.run(memory.settle_rumor(w.d, rec, ["p0", "p1", "p2"], set()))
        assert gossip.get_cred(w.d.gossip_cred, "p0") == gossip.CRED_START + 5
        assert w.fights == [] and all(aff < 0 for *_, aff in w.deltas)
    finally:
        w.close()


def test_a_rumor_about_someone_who_isnt_there_just_roots_a_chain():
    w = _World()
    try:
        rec = MemoryRec(NOW, "P9 is quitting.", ["p9"], 5, "event", 60, "p0", None, None, 0, 80, 50)
        asyncio.run(memory.settle_rumor(w.d, rec, ["p0", "p1"], set()))
        assert rec.origin_id == 60 and w.deltas == [] and w.d.gossip_log == []
    finally:
        w.close()


def test_the_scene_shows_provenance_and_never_the_truth():
    from tests.test_sim import _chat, _scene_director, _scene_for

    d = _scene_director()
    d.people["p2"].present = True
    d.people["p2"].persona["job"] = "welder"
    rec = MemoryRec(NOW - timedelta(days=1), "P2 is quitting.", ["p2"], 9, "event", 4, "p1", None, 4, 1, 40, 17)
    d.social.memories["p0"] = [rec]
    t = _chat(False, lines=[("speech", "p1", "hi")])
    ctx = _scene_for(d, t, d.people["p0"]).context
    assert "heard from P1, not sure" in ctx
    assert "17" not in ctx and gossip.HAZY_HINT in ctx
    assert t.told == {"p0": [4]}

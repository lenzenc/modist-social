import asyncio
import random
from datetime import timedelta

from app.agents.agent import sanitize
from app.config import settings
from app.llm.mock import MockLLM
from app.llm.types import TurnRequest, Utterance
from app.sim import beats, human
from app.sim.clock import SimClock
from app.sim.social import pair_key
from app.sim.state import PersonState, RelState
from tests.test_drunk import _p, _posting, _run
from tests.test_sim import NOW, _chat, _director, _scene_director, _scene_for


# ---------------------------------------------------------------- pure rules


def test_smokers_follow_the_persona_and_are_stable():
    assert beats.smoker(_p(persona={"quirk": "sneaks a cigarette between rounds"}))
    assert not beats.smoker(_p(persona={"quirk": "a non-smoker who hates the smell"}))
    a = _p()
    assert beats.smoker(a) == beats.smoker(a)
    share = sum(beats.smoker(_p(id=f"x{i}")) for i in range(500)) / 500
    assert 0.05 < share < 0.2


def test_idle_beats_need_something_to_react_to():
    rng = random.Random(1)
    p = _p(reason="unwind", battery=1.0)
    kinds = {beats.roll_idle(rng, p, game_live=False, friends_in_area=False, jukebox_ok=False) for _ in range(300)}
    assert not kinds & {"tv", "laugh_across", "jukebox"} and kinds
    kinds = {beats.roll_idle(rng, p, game_live=True, friends_in_area=True, jukebox_ok=True) for _ in range(300)}
    assert {"tv", "laugh_across", "jukebox"} <= kinds


def test_music_fans_pick_the_jukebox_more_and_songs_fit_taste():
    rng = random.Random(2)
    fan = _p(persona={"interests": ["live music", "country"]})
    plain = _p(persona={"interests": ["gardening"]})
    n = lambda q: sum(beats.roll_idle(rng, q, game_live=False, friends_in_area=False, jukebox_ok=True) == "jukebox" for _ in range(600))
    assert n(fan) > n(plain)
    country = sum(dict((t, v) for t, _, v in beats.JUKEBOX)[beats.pick_song(rng, fan.persona)[0]] == "country" for _ in range(300))
    assert country > 100


def test_idle_text_fills_in_names_and_pronouns():
    p = _p(pronouns="she/her")
    for kind in beats.IDLE:
        text = beats.idle_text(random.Random(3), kind, p, "Twins")
        assert "{" not in text and p.short in text
    assert "her" in beats.idle_text(random.Random(0), "coaster", p) or "coaster" in beats.idle_text(random.Random(0), "coaster", p)


def test_lulls_follow_short_lines_and_are_bounded():
    assert beats.lull_chance(True, False, 0) > beats.lull_chance(False, False, 0)
    assert beats.lull_chance(True, True, 5) == beats.LULL_MAX


def test_chat_beats_are_rare_and_tv_only_with_a_game():
    rng = random.Random(4)
    p = _p(battery=1.0)
    got = [beats.chat_beat(rng, p, False) for _ in range(1000)]
    assert 40 < sum(bool(g) for g in got) < 200
    assert not any("TV" in g for g in got)
    assert any("TV" in beats.chat_beat(rng, p, True) for _ in range(1000))


def test_clean_beat_is_a_bare_clause():
    p = _p()
    assert beats.clean_beat('*Pat glances at the TV.*', p) == "glances at the TV"
    assert beats.clean_beat('"checks the time."', p) == "checks the time"
    assert len(beats.clean_beat("x" * 300, p)) == 80


def test_quiet_share_bands():
    assert beats.quiet_share(1, 5)["band"] == "none"
    assert beats.quiet_share(20, 100)["band"] == "green"
    assert beats.quiet_share(7, 100)["band"] == "amber"
    assert beats.quiet_share(0, 100)["band"] == "red"
    assert beats.quiet_share(500, 100)["band"] == "red"


def test_only_smokers_draw_the_smoke_need():
    rng = random.Random(5)
    plain = {human.pick_need(rng, 120, NOW, True)[0] for _ in range(400)}
    smoke = [human.pick_need(rng, 120, NOW, True, smoker=True)[0] for _ in range(400)]
    assert "smoke" not in plain and smoke.count("smoke") > 100


# ---------------------------------------------------------------- the model's part


def test_sanitize_cleans_the_beat():
    u = sanitize(Utterance(say="", beat="Pat glances at the TV."), _p())
    assert u.beat == "glances at the TV" and u.say == ""


def test_scene_tells_the_room_about_lulls_and_calls():
    d = _scene_director()
    p = d.people["p0"]
    t = _chat(False, lines=[("speech", "p1", "Hm.")], turns=2)
    t.lull, t.cut = True, {"p0"}
    req = _scene_for(d, t, p)
    assert req.lull and req.cut and "went quiet" in req.context and "break off" in req.context
    assert not t.lull  # told once
    assert not _scene_for(d, t, p).lull


def test_scene_renders_actions_in_the_transcript_and_the_jukebox():
    d = _scene_director()
    d.now_playing = ("Float On", "Modest Mouse", NOW + timedelta(minutes=3))
    t = _chat(False, lines=[("action", "p1", "P1 checks the time."), ("speech", "p1", "Anyway.")])
    ctx = _scene_for(d, t, d.people["p0"]).context
    assert "(P1 checks the time.)" in ctx and "Float On" in ctx
    d.now_playing = ("Float On", "Modest Mouse", NOW - timedelta(minutes=1))
    assert "Float On" not in _scene_for(d, t, d.people["p0"]).context


def test_mock_breaks_off_for_a_call_and_beats_cover_the_roster():
    req = TurnRequest(person_id="p0", person_name="Pat", world="", persona="", context="", last_line="Hi", cut=True)
    u = _run(MockLLM().speak(req))
    assert u.say.endswith("—") and u.action == "excuse"
    got = _run(MockLLM().beats("Ann | welder | x | y | z | bar\nBo | nurse | x | y | z | patio", "room"))
    assert set(got) == {"Ann", "Bo"} and all(len(v) == 2 for v in got.values())


# ---------------------------------------------------------------- the director


def _turn_director(utt):
    d = _scene_director()
    d.clock = SimClock(start=NOW)
    posts = []

    async def post(channel, text, speaker=None, kind="speech", thread=None, thought=None):
        posts.append((kind, speaker, text))
        if thread:
            thread.lines.append((kind, speaker or "", text))

    class LLM:
        async def speak(self, req):
            return utt

    d.post, d.llm = post, LLM()
    d.persona_text.update({k: "" for k in d.people})
    return d, posts


def test_a_gesture_alone_is_a_turn():
    d, posts = _turn_director(Utterance(say="", beat="shrugs and sips"))
    t = _chat(False, lines=[("speech", "p1", "So.")], turns=1)
    d.threads[t.id] = t
    _run(d.take_turn(t, d.people["p0"]))
    assert posts == [("action", "p0", "P0 shrugs and sips.")] and t.turns == 2 and t.failures == 0


def test_beat_comes_before_the_line_and_never_in_an_order():
    d, posts = _turn_director(Utterance(say="Fair point.", beat="nods"))
    t = _chat(False, lines=[("speech", "p1", "So.")], turns=1)
    d.threads[t.id] = t
    _run(d.take_turn(t, d.people["p0"]))
    assert [k for k, _, _ in posts] == ["action", "speech"]
    d2, posts2 = _turn_director(Utterance(say="", beat="nods"))
    o = _chat(False, turns=1)
    o.kind = "order"
    d2.threads[o.id] = o
    _run(d2.take_turn(o, d2.people["p0"]))
    assert posts2 == [] and o.failures == 1


def test_a_call_breaks_off_mid_sentence_and_steps_away():
    d, posts = _turn_director(Utterance(say="Sorry, I have to take—", action="excuse"))
    t = _chat(False, lines=[("speech", "p1", "So.")], turns=1)
    d.threads[t.id] = t
    p = d.people["p0"]
    p.need = "call"
    t.cut.add("p0")
    _run(d.take_turn(t, p))
    assert "p0" not in t.members and not t.cut
    assert p.need == "" and p.free_since > NOW
    assert any("mid-sentence" in x for _, _, x in posts)


def test_a_lull_posts_a_quiet_line_and_tells_the_next_speaker():
    d, posts = _turn_director(Utterance(say="Yeah."))
    t = _chat(False, lines=[("speech", "p1", "Hm."), ("speech", "p0", "Yeah.")], turns=3)
    d.threads[t.id] = t
    t.max_turns = 12

    async def sleep(secs):
        pass

    d.clock.sleep = sleep
    d.rng = random.Random(0)
    old = beats.LULL_BASE, beats.LULL_MAX
    beats.LULL_BASE = beats.LULL_MAX = 1.0
    try:
        _run(d.quiet_step(t, d.people["p0"]))
    finally:
        beats.LULL_BASE, beats.LULL_MAX = old
    assert t.lull and t.lulls == 1 and any(k == "action" and s is None for k, s, _ in posts)


def test_smokers_step_out_and_wave_at_friends():
    d = _scene_director()
    posts = _posting(d)
    p = d.people["p0"]
    p.need, p.need_at, p.location = "smoke", NOW, "patio"
    _run(d.step_out(p, NOW))
    assert p.need == "" and p.free_since > NOW and "smoke" in posts[0]
    d.social.rels[pair_key("p1", "p2")] = RelState(familiarity=80)
    d.people["p1"].present = True
    d.people["p2"].present = True
    d.rng = random.Random(0)
    d.rng.random = lambda: 0.0
    _run(d.wave_hello(d.people["p2"], NOW))
    assert d.wave_boost("p1", "p2", NOW) > 1.0 and d.wave_boost("p1", "p2", NOW + timedelta(hours=1)) == 1.0


def test_the_beats_call_is_capped_and_can_be_switched_off(monkeypatch):
    d = _scene_director()
    _posting(d)
    d.people["p2"].present = True
    for q in ("p0", "p1", "p2"):
        d.people[q].persona.update(quirk="x", interests=["y"])
    calls = []

    class LLM:
        async def beats(self, roster, room):
            calls.append(roster)
            return {"P0": ["checks the time", " P0 turns the coaster."], "Nobody": ["x"], "B": ["wipes the bar"]}

    d.llm = LLM()

    async def go():
        d.maybe_refresh_beats(NOW)
        await asyncio.gather(*d.tasks)
        d.maybe_refresh_beats(NOW + timedelta(minutes=10))  # inside the hourly cap
        await asyncio.gather(*d.tasks)

    _run(go())
    assert len(calls) == 1 and "P0 |" in calls[0]
    assert d.beat_pool["p0"] == ["checks the time", "turns the coaster"] and "b1" not in d.beat_pool
    monkeypatch.setattr(settings, "llm_beats", False)
    d.beat_calls.clear()
    d.beat_pool.clear()
    _run(go())
    assert len(calls) == 1

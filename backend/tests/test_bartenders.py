import asyncio
import random
from datetime import timedelta

from app.sim.state import PersonState, ThreadState
from tests.test_groups import _pool, _stub
from tests.test_newcomers import NOW, _director


def _second_bartender(d):
    d.people["b2"] = PersonState(id="b2", name="B Two", short="B2", display="B Two", role="bartender",
                                 pronouns="they/them", color="#000", persona={}, present=True, location="bar")
    return d.people["b2"]


def _put(d, tid, kind, members):
    t = ThreadState(id=tid, channel="bar", kind=kind, started=NOW, members=list(members), ever=dict.fromkeys(members), max_turns=9)
    d.threads[tid] = t
    return t


def test_a_bartender_in_any_conversation_is_not_free(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    b2 = _second_bartender(d)
    assert {b.id for b in d.free_bartenders()} == {"b1", "b2"}
    for kind in ("order", "chat"):
        t = _put(d, 1, kind, ["g0", "b1"])
        assert [b.id for b in d.free_bartenders()] == ["b2"]
        assert d.pick_bartender(g[1]) is b2
        t.closing = True
        assert len(d.free_bartenders()) == 2  # a conversation that is ending no longer holds them
        del d.threads[1]


def test_a_second_bartender_only_joins_a_chat_if_free(monkeypatch):
    d, _ = _director(monkeypatch)
    _pool(d, 3)
    b2 = _second_bartender(d)
    _put(d, 1, "order", ["g1", "b2"])
    t = _put(d, 2, "chat", ["g0", "b1"])
    d.rng = random.Random(0)
    for _ in range(50):
        asyncio.run(d.maybe_second_bartender(t))
    assert b2.id not in t.members


def test_a_guest_waits_in_line_when_every_bartender_is_busy_then_gets_served(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    posts, chats = _stub(d, monkeypatch)
    for p in g:
        p.present = True
    busy = _put(d, 1, "order", ["g0", "b1"])
    asyncio.run(d.request_order(g[1]))
    assert chats == [] and g[1].waiting and [w.pid for w in d.queue] == ["g1"]
    assert any("waits for a bartender" in t for _, t in posts)
    asyncio.run(d.serve_queue(NOW + timedelta(seconds=30)))
    assert g[1].waiting and not chats  # still nobody free, and an order is never interrupted
    asyncio.run(d.serve_queue(NOW + timedelta(minutes=5)))
    assert g[1].waiting and busy.members == ["g0", "b1"]
    del d.threads[1]
    asyncio.run(d.serve_queue(NOW + timedelta(minutes=5)))
    assert not g[1].waiting and not d.queue and chats == [("ordering", "order", ["g1", "b1"])]


def test_after_two_minutes_an_order_pulls_a_bartender_out_of_a_chat(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 3)
    posts, chats = _stub(d, monkeypatch)
    for p in g:
        p.present = True
    chat = _put(d, 1, "chat", ["g0", "g2", "b1"])
    d.clock.now = lambda: NOW
    asyncio.run(d.request_order(g[1]))
    assert g[1].waiting
    asyncio.run(d.serve_queue(NOW + timedelta(minutes=1)))
    assert g[1].waiting and "b1" in chat.members
    asyncio.run(d.serve_queue(NOW + timedelta(minutes=2)))
    assert not g[1].waiting and "b1" not in chat.members
    assert chats == [("ordering", "order", ["g1", "b1"])]
    assert any("excuses themselves to serve" in t for _, t in posts)


def test_a_delayed_first_drink_is_not_a_repeat_round(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    _stub(d, monkeypatch)
    g[0].present = g[1].present = True
    g[1].drinks = 1
    _put(d, 1, "order", ["g0", "b1"])
    asyncio.run(d.request_order(g[1]))
    assert d.queue[0].again is True
    d.queue.clear()
    g[1].waiting, g[1].drinks = False, 0
    asyncio.run(d.request_order(g[1]))
    assert d.queue[0].again is False


def test_leaving_the_line_and_going_off_shift(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    _stub(d, monkeypatch)
    g[0].present = True
    t = _put(d, 1, "chat", ["g0", "b1"])
    d.bartender_off(d.people["b1"])
    assert "b1" not in t.members and t.closing
    g[0].waiting = True
    d.queue.append(__import__("app.sim.state", fromlist=["Waiting"]).Waiting("g0", NOW, False))

    async def noop(*a, **k):
        return None

    d.close_tab = noop
    asyncio.run(d.depart(g[0]))
    assert not d.queue and not g[0].waiting

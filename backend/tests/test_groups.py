import asyncio
import random
from collections import Counter
from datetime import timedelta

from app.sim import director as dmod
from app.sim import groups
from app.sim.state import MAX_GROUP, TABLE_PAIRS, TABLES, PersonState, ThreadState
from tests.test_newcomers import NOW, _director


# ---------------------------------------------------------------- the pure rolls


def test_party_sizes_are_mostly_two_to_four_with_eights_not_rare():
    rng = random.Random(1)
    sizes = Counter(groups.pick_size(rng) for _ in range(5000))
    assert set(sizes) <= set(range(2, groups.MAX_PARTY + 1))
    assert sum(sizes[n] for n in (2, 3, 4)) / 5000 > 0.6
    assert sizes[8] / 5000 > 0.05


def test_split_keeps_every_chunk_within_a_table_and_covers_everyone():
    for n in range(1, groups.MAX_PARTY + 1):
        members = [f"m{i}" for i in range(n)]
        chunks = groups.split(members)
        assert all(1 <= len(c) <= MAX_GROUP for c in chunks)
        assert [m for c in chunks for m in c] == members
        assert len(chunks) == groups.tables_needed(n)
    assert [len(c) for c in groups.split(list("abcde"))] == [3, 2]


def test_table_pairs_point_at_real_tables():
    rows = {"inside-tables": 7, "patio": 3}
    for area, pairs in TABLE_PAIRS.items():
        assert {i for pr in pairs for i in pr} == set(range(TABLES[area]))
        assert all(b == a + 1 and a // rows[area] == b // rows[area] for a, b in pairs)  # neighbours in one row


# ---------------------------------------------------------------- tables


def _pool(d, n):
    for i in range(n):
        d.people[f"g{i}"] = PersonState(id=f"g{i}", name=f"G{i} X", short=f"G{i}", display=f"G{i} X", role="patron",
                                        pronouns="they/them", color="#000", persona={"talk": 0.1 * i + 0.1})
    return [d.people[f"g{i}"] for i in range(n)]


def test_a_big_party_takes_two_empty_adjacent_tables_and_never_the_bar(monkeypatch):
    d, _ = _director(monkeypatch)
    for seed in range(40):
        d.rng = random.Random(seed)
        area, tables = d.claim_party_tables(7)
        assert area in TABLES
        assert tuple(tables) in TABLE_PAIRS[area]
        area, tables = d.claim_party_tables(3)
        assert area in TABLES and len(tables) == 1


def test_a_party_falls_back_to_the_other_area_and_then_to_standing(monkeypatch):
    d, _ = _director(monkeypatch)
    d.rng = random.Random(3)
    for i in range(TABLES["inside-tables"]):
        d.parties[i + 1] = dmod.PartyState(id=i + 1, members=[], leader="", area="inside-tables", tables=[i])
    assert d.claim_party_tables(4)[0] == "patio"
    for i in range(TABLES["patio"]):
        d.parties[100 + i] = dmod.PartyState(id=100 + i, members=[], leader="", area="patio", tables=[i])
    assert d.claim_party_tables(4)[1] == []


def test_strangers_are_not_given_a_table_a_party_holds(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    d.parties[1] = dmod.PartyState(id=1, members=["g0"], leader="g0", area="inside-tables", tables=[0, 1])
    g[0].party = 1
    seen = {d.pick_table("inside-tables", [g[1].id]) for _ in range(200)}
    assert seen and not (seen & {0, 1})
    g[1].party = 1  # a member of the party may use them
    assert {d.pick_table("inside-tables", [g[1].id]) for _ in range(200)} & {0, 1}


def test_a_party_gives_its_tables_back_when_the_last_member_leaves(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 2)
    d.parties[1] = dmod.PartyState(id=1, members=["g0", "g1"], leader="g0", area="patio", tables=[0])
    for p in g:
        p.party, p.present = 1, True
    g[0].present = False
    d.leave_party(g[0])
    assert 1 in d.parties
    g[1].present = False
    d.leave_party(g[1])
    assert not d.parties


# ---------------------------------------------------------------- arriving


def _stub(d, monkeypatch):
    posts, chats = [], []

    async def post(channel, text, **kw):
        posts.append((channel, text))

    async def noop(*a, **k):
        return None

    async def open_thread(channel, kind, members, max_turns, **kw):
        t = ThreadState(id=len(chats) + 1, channel=channel, kind=kind, started=NOW, members=list(members),
                        ever=dict.fromkeys(members), max_turns=max_turns)
        for m in members:
            d.people[m].thread_id = t.id
        d.threads[t.id] = t
        chats.append((channel, kind, list(members)))
        return t

    d.post, d.open_thread = post, open_thread
    d.social.apply_delta = d.social.mark_met = d.social.add_memory = noop
    d.publish_relationships = lambda ids: None
    d.publish_presence = lambda: None
    monkeypatch.setattr(dmod, "is_open", lambda t: True)
    return posts, chats


def test_a_party_walks_in_together_and_sits_together(monkeypatch):
    d, _ = _director(monkeypatch)
    d.clock.set_speed(1)
    members = _pool(d, 6)
    posts, chats = _stub(d, monkeypatch)
    d.rng = random.Random(5)
    asyncio.run(d.arrive_group(members))
    assert len([p for p in posts if p[0] == "door"]) == 1
    area = members[0].spot
    assert area in TABLES and all(m.spot == area and m.party is not None for m in members)
    pt = d.parties[members[0].party]
    assert tuple(sorted(pt.tables)) in TABLE_PAIRS[area]
    # the leader went to the bar; everyone else is already sitting, in chats of at most a table
    leader = pt.leader
    assert {m.table for m in members if m.id != leader} == set(pt.tables)
    assert d.people[leader].location == "ordering"
    chat = [c for c in chats if c[1] == "chat"]
    assert chat and all(2 <= len(c[2]) <= MAX_GROUP and leader not in c[2] for c in chat)
    ends = [m.leave_at for m in members]
    assert max(ends) - min(ends) <= timedelta(minutes=21)


def test_the_leaders_order_pays_for_the_whole_first_round(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 3)
    charged = []

    async def charge(p, drink, bartender_id, t):
        charged.append(p.id)
        p.drinks += 1

    d.charge = charge
    for p in g:
        p.present = True
    t = ThreadState(id=1, channel="ordering", kind="order", started=NOW, members=["g0", "b1"],
                    ever={"g0": None, "b1": None}, max_turns=3, order_drink="Some Lager", party=["g1", "g2"])
    asyncio.run(d.finish_order(t))
    assert charged == ["g0", "g1", "g2"]


def test_an_order_that_never_settles_still_gets_the_party_a_next_round(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 3)
    for p in g:
        p.present = True
    t = ThreadState(id=1, channel="ordering", kind="order", started=NOW, members=["g0", "b1"],
                    ever={"g0": None, "b1": None}, max_turns=3, party=["g1", "g2"])
    asyncio.run(d.finish_order(t))
    assert g[1].next_drink_at is not None and g[2].next_drink_at is not None


# ---------------------------------------------------------------- building


def _fake_newcomers(d, made):
    async def make():
        n = len(d.people)
        p = PersonState(id=f"n{n}", name=f"N{n} Y", short=f"N{n}", display=f"N{n} Y", role="patron",
                        pronouns="they/them", color="#000", persona={})
        d.people[p.id] = p
        made.append(p.id)
        return p

    d.make_newcomer = make


def test_an_all_new_party_is_made_from_scratch_and_respects_the_patron_cap(monkeypatch):
    d, _ = _director(monkeypatch)
    made = []
    _fake_newcomers(d, made)
    monkeypatch.setattr(dmod.settings, "max_patrons", len(d.patrons()) + 3)
    out = asyncio.run(d.build_group(8, "new"))
    assert len(out) == 3 == len(made)


def test_a_regulars_party_is_built_around_friends_and_falls_back_to_mixed(monkeypatch):
    d, _ = _director(monkeypatch)
    g = _pool(d, 6)
    made = []
    _fake_newcomers(d, made)
    d.rng = random.Random(2)
    out = asyncio.run(d.build_group(4, "regulars"))  # nobody knows anybody: not enough friends, so new faces fill in
    assert len(out) == 4 and made
    d.social.rel = lambda a, b: type("R", (), {"familiarity": 60, "affinity": 20})()
    made.clear()
    out = asyncio.run(d.build_group(4, "regulars"))
    assert len(out) == 4 and not made


def test_welcome_group_resets_the_lock_even_when_it_fails(monkeypatch):
    d, _ = _director(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("model down")

    d.build_group = boom
    d.generating = True
    try:
        asyncio.run(d.welcome_group())
    except RuntimeError:
        pass
    assert d.generating is False


def test_the_leader_rejoins_their_own_table_after_ordering(monkeypatch):
    d, _ = _director(monkeypatch)
    d.clock.set_speed(1)
    members = _pool(d, 3)
    posts, chats = _stub(d, monkeypatch)
    d.rng = random.Random(8)
    asyncio.run(d.arrive_group(members))
    pt = d.parties[members[0].party]
    leader = d.people[pt.leader]
    others = [m for m in members if m is not leader]
    assert len(chats) == 2 and [c[1] for c in chats] == ["order", "chat"]  # the bar run, and the table already talking
    chat = d.threads[2]

    async def join(t, p):
        t.members.append(p.id)
        p.thread_id = t.id

    d.join_thread = join
    leader.thread_id = None  # the order is done
    asyncio.run(d.settle(leader))
    assert leader.location == pt.area and leader.table == others[0].table
    assert leader.id in chat.members

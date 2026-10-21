import random
from datetime import datetime

from app.sim import seating
from app.sim.state import BAR_STOOLS, TABLE_SEATS, TABLES

JULY = datetime(2026, 7, 22, 17, 0)  # a clear Wednesday; trivia is 7-9pm, so 5pm is clear of it
JAN = datetime(2026, 1, 14, 17, 0)
CAP = {"bar": BAR_STOOLS, **{a: n * TABLE_SEATS for a, n in TABLES.items()}}


def w(party, now=JULY, lean=1.0, knows=False, fan=False, free=None):
    return seating.area_weights(party, lean, knows, fan, now, free or dict(CAP), CAP)


def test_solo_favours_the_bar_and_groups_favour_tables():
    assert w(1)["bar"] > w(3)["bar"]
    assert w(3)["inside-tables"] > w(3)["bar"]
    assert w(1)["bar"] > w(1)["patio"]


def test_patio_is_far_weaker_in_january_than_july():
    assert w(2, JAN)["patio"] < w(2, JULY)["patio"] / 5


def test_full_bar_has_no_weight_but_full_tables_keep_a_floor():
    free = dict(CAP, bar=0, **{"inside-tables": 0})
    out = w(1, free=free)
    assert out["bar"] == 0
    assert out["inside-tables"] > 0


def test_bartender_friend_and_game_fan_pull_toward_the_bar():
    assert w(1, knows=True)["bar"] > w(1)["bar"]
    game_day = next(datetime(2026, 7, 1, 19, 30).replace(day=d) for d in range(1, 29)
                    if seating.environment.live(seating.environment.game_on(datetime(2026, 7, d, 19, 30)), datetime(2026, 7, d, 19, 30)))
    assert w(1, game_day, fan=True)["bar"] > w(1, game_day)["bar"]


def _shares(now, n=2000):
    rng = random.Random(7)
    counts = dict.fromkeys(seating.AREAS, 0)
    for _ in range(n):
        party = rng.choices([1, 2, 3], [0.35, 0.4, 0.25])[0]
        counts[seating.pick_area(rng, w(party, now, lean=1.0))] += 1
    return {a: c / n for a, c in counts.items()}


def test_summer_split_is_bar_minority_with_a_real_patio():
    s = _shares(JULY)
    assert 0.25 <= s["bar"] <= 0.40
    assert 0.15 <= s["patio"] <= 0.30
    assert s["inside-tables"] > s["bar"]


def test_winter_patio_is_rare():
    assert _shares(JAN)["patio"] < 0.10


def test_settle_sends_a_refill_back_to_their_spot_not_the_bar():
    import asyncio

    from tests.test_sim import _director

    d = _director()
    p = d.people["p0"]
    p.present, p.location, p.spot, p.drinks = True, "ordering", "patio", 2
    gone = []

    async def move(q, loc):
        gone.append(loc)
        return True

    d.move = move
    for _ in range(20):
        gone.clear()
        p.location = "ordering"
        asyncio.run(d.settle(p))
        assert gone == ["patio"]

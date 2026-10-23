import random
from datetime import datetime

import yaml

from app.seed.loader import HERE
from app.sim import menu, sales

SUN_2PM = datetime(2026, 10, 18, 14, 0)
SUN_630PM = datetime(2026, 10, 18, 18, 30)
MON_4PM = datetime(2026, 10, 19, 16, 0)
THU_4PM = datetime(2026, 10, 22, 16, 0)


def test_happy_hour_window():
    assert sales.happy_hour(SUN_2PM) and sales.happy_hour(MON_4PM)
    assert not sales.happy_hour(SUN_630PM)
    assert not sales.happy_hour(THU_4PM)
    assert not sales.happy_hour(datetime(2026, 10, 19, 10, 0))  # closed


def test_specials_are_stable_per_day_and_on_the_menu():
    a, b = sales.specials(MON_4PM), sales.specials(datetime(2026, 10, 19, 21, 0))
    assert a == b and len(a) == sales.SPECIALS_PER_DAY and set(a) <= set(menu.names())
    assert sales.specials(MON_4PM) != sales.specials(datetime(2026, 10, 20, 16, 0))


def test_specials_are_a_mainstay_beer_and_two_other_beers():
    for day in range(20):
        a = sales.specials(datetime(2026, 10, 1 + day, 16, 0))
        assert len(a) == 3 and set(a) <= set(menu.beers())
        assert sum(menu.is_mainstay(n) for n in a) >= 1 and any(n in menu.beers(mainstay=True) for n in a)
    # the mainstay is a beer, never a seltzer or THC drink, even though those are mainstays too
    assert not any(menu.kind(n) != "beer" for d in range(20) for n in sales.specials(datetime(2026, 10, 1 + d, 16, 0)))


def test_specials_cope_with_a_board_short_of_beers():
    keep = [d for d in menu.default_board() if d["kind"] == "beer"][:2] + [d for d in menu.default_board() if d["kind"] != "beer"]
    menu.set_board(keep)
    try:
        assert sorted(sales.specials(MON_4PM)) == sorted(menu.beers())
        menu.set_board([d for d in keep if d["kind"] != "beer" or not d["mainstay"]])
        assert len(sales.specials(MON_4PM)) == min(3, len(menu.beers()))
    finally:
        menu.set_board(menu.default_board())


def test_price_is_half_only_for_todays_specials_in_happy_hour():
    special = sales.specials(MON_4PM)[0]
    other = next(n for n in menu.names() if n not in sales.specials(MON_4PM))
    assert sales.price(special, MON_4PM) == (800, 400, True)
    assert sales.price(other, MON_4PM) == (800, 800, False)
    assert sales.price(special, THU_4PM)[1] == 800
    assert sales.price(special, datetime(2026, 10, 19, 18, 0))[1] == 800


def test_tips_are_the_allowed_percentages():
    r = random.Random(7)
    for habit in ("low", "standard", "generous", "unknown"):
        assert {sales.pick_tip(habit, r) for _ in range(400)} <= set(sales.TIPS)
    assert 0 in {sales.pick_tip("low", r) for _ in range(200)}
    assert 0 not in {sales.pick_tip("generous", r) for _ in range(200)}
    assert sales.tip_cents(800, 18) == 144 and sales.tip_cents(400, 25) == 100 and sales.tip_cents(1200, 0) == 0
    assert sales.tip_cents(1050, 18) == 189


def test_card_is_stable_per_person():
    assert sales.card_for("p01") == sales.card_for("p01")
    brand, last4 = sales.card_for("p02")
    assert brand and len(last4) == 4 and last4.isdigit()


def test_patrons_have_valid_payment_habits():
    rows = yaml.safe_load((HERE / "patrons.yaml").read_text())
    assert all(r["pay"] in ("tab", "card") and r["tipper"] in sales.TIP_WEIGHTS for r in rows)
    tabs = sum(r["pay"] == "tab" for r in rows)
    assert 10 <= tabs <= 25


def test_drink_goal_is_mostly_one_to_three():
    r = random.Random(3)
    goals = [sales.pick_goal(r, 90) for _ in range(2000)]
    assert min(goals) >= 1 and max(goals) <= 6
    assert sum(g <= 3 for g in goals) / len(goals) > 0.8
    assert 1.8 < sum(goals) / len(goals) < 2.8


def test_day_end_keeps_a_late_tab_on_its_night():
    assert sales.day_end(datetime(2026, 10, 23, 21, 15)) == datetime(2026, 10, 23, 23, 59, 59)


def test_wants_round_gating():
    from datetime import timedelta

    from tests.test_sim import _director

    d = _director()
    p = d.people["p0"]
    now = MON_4PM
    p.present, p.drink_goal, p.drinks = True, 3, 1
    p.leave_at, p.next_drink_at = now + timedelta(hours=2), now - timedelta(minutes=1)
    assert d.wants_round(p, now)
    p.next_drink_at = now + timedelta(minutes=5)
    assert not d.wants_round(p, now)
    p.next_drink_at = now - timedelta(minutes=1)
    p.drinks = 3
    assert not d.wants_round(p, now)
    p.drinks, p.wants_leave = 1, True
    assert not d.wants_round(p, now)
    p.wants_leave, p.leave_at = False, now + timedelta(minutes=5)
    assert not d.wants_round(p, now)  # about to leave
    p.leave_at = now + timedelta(hours=2)
    assert not d.wants_round(p, datetime(2026, 10, 19, 21, 55))  # inside the final 10 minutes before close

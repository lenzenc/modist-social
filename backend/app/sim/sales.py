"""Pricing, happy hour, tips and card details. Pure functions so the register math is easy to test."""
import hashlib
import random
from datetime import date, datetime, time

from app.sim import menu
from app.sim.clock import is_open

PRICE_CENTS = 800
HAPPY_PRICE_CENTS = 400
HAPPY_DAYS = {6, 0, 1, 2}  # Sun, Mon, Tue, Wed
HAPPY_END_HOUR = 18
SPECIALS_PER_DAY = 4

TIPS = (0, 18, 20, 25)
TIP_WEIGHTS = {
    "low": (40, 45, 15, 0),
    "standard": (5, 35, 45, 15),
    "generous": (0, 0, 35, 65),
}
CARD_BRANDS = ("Visa", "Visa", "Mastercard", "Mastercard", "Amex", "Discover")
GOAL_WEIGHTS = {1: 30, 2: 35, 3: 22, 4: 9, 5: 4}


def happy_hour(t: datetime) -> bool:
    return t.weekday() in HAPPY_DAYS and is_open(t) and t.hour < HAPPY_END_HOUR


def specials(day: date | datetime) -> list[str]:
    """The half-price selection for a day: random but fixed per date, so a restart changes nothing."""
    d = day.date() if isinstance(day, datetime) else day
    return sorted(random.Random(f"specials:{d.isoformat()}").sample(menu.names(), SPECIALS_PER_DAY))


def price(drink: str, t: datetime) -> tuple[int, int, bool]:
    """(list price, price charged, happy-hour price applied?) in cents."""
    if happy_hour(t) and drink in specials(t):
        return PRICE_CENTS, HAPPY_PRICE_CENTS, True
    return PRICE_CENTS, PRICE_CENTS, False


def pick_tip(tipper: str, rng: random.Random) -> int:
    return rng.choices(TIPS, TIP_WEIGHTS.get(tipper, TIP_WEIGHTS["standard"]))[0]


def tip_cents(subtotal: int, pct: int) -> int:
    return (subtotal * pct + 50) // 100


def card_for(person_id: str) -> tuple[str, str]:
    h = hashlib.sha256(person_id.encode()).digest()
    return CARD_BRANDS[h[0] % len(CARD_BRANDS)], f"{int.from_bytes(h[1:3], 'big') % 10000:04d}"


def day_end(t: datetime) -> datetime:
    """Last moment of t's calendar day; a tab closed just after midnight still belongs to the night it was opened."""
    return datetime.combine(t.date(), time(23, 59, 59))


def pick_goal(rng: random.Random, stay_min: float) -> int:
    """How many drinks a guest wants this visit: usually 1-3, occasionally more, and longer stays drink more."""
    goal = rng.choices(list(GOAL_WEIGHTS), list(GOAL_WEIGHTS.values()))[0]
    if stay_min >= 120 and rng.random() < 0.35:
        goal += 1
    elif stay_min <= 60 and goal > 2 and rng.random() < 0.5:
        goal -= 1
    return goal


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"

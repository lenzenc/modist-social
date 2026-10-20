from datetime import datetime

from app.sim.clock import open_close

# Real patrons visit less than the regulars would to keep a room lively, so scale up visit frequency.
ARRIVAL_BOOST = 2.2

# weekday -> [(start_hour, end_hour, (bartender, bartender))]. Five bartenders, always in twos.
ROSTER: dict[int, list[tuple[int, int, tuple[str, str]]]] = {
    0: [(15, 22, ("b1", "b4"))],
    1: [(15, 22, ("b2", "b3"))],
    2: [(15, 22, ("b5", "b1"))],
    3: [(15, 23, ("b4", "b3"))],
    4: [(14, 19, ("b2", "b5")), (19, 24, ("b1", "b3"))],
    5: [(11, 18, ("b4", "b5")), (18, 24, ("b2", "b1"))],
    6: [(11, 21, ("b3", "b2"))],
}


def on_shift(t: datetime) -> tuple[str, str] | None:
    hour = t.hour + t.minute / 60
    for start, end, pair in ROSTER[t.weekday()]:
        if start <= hour < end:
            return pair
    return None


def arrival_rate(freq: float, days: list[int], window: list[float], t: datetime) -> float:
    """Expected arrivals per hour for one person at time t (before the one-visit-a-day cap)."""
    npd = len(days)
    day_weight = 1.0 if t.weekday() in days else 0.25
    visits_today = freq * ARRIVAL_BOOST * day_weight / (npd + 0.25 * (7 - npd))
    lo, hi = window
    width = max(hi - lo, 1.0)
    hour = t.hour + t.minute / 60
    hour_weight = 1.0 if lo <= hour < hi + 1 else 0.15
    return visits_today / width * hour_weight


def closing_time(t: datetime) -> datetime:
    return open_close(t)[1]

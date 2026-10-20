import asyncio
import time
from datetime import datetime, timedelta

# Monday 19 Oct 2026, ten minutes before the first opening.
DEFAULT_START = datetime(2026, 10, 19, 14, 50)

# (open hour, close hour) by weekday, Monday=0. Close 24 means midnight.
HOURS = {
    0: (15, 22),
    1: (15, 22),
    2: (15, 22),
    3: (15, 23),
    4: (14, 24),
    5: (11, 24),
    6: (11, 21),
}


def open_close(day: datetime) -> tuple[datetime, datetime]:
    o, c = HOURS[day.weekday()]
    midnight = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(hours=o), midnight + timedelta(hours=c)


def is_open(t: datetime) -> bool:
    o, c = open_close(t)
    return o <= t < c


def next_open(t: datetime) -> datetime:
    """The next opening time: later today if the bar hasn't opened yet, otherwise tomorrow's."""
    o, _ = open_close(t)
    return o if t < o else open_close(t + timedelta(days=1))[0]


def launch_time(saved: datetime) -> datetime:
    """Where the clock should start on launch: a closed bar skips ahead to 10 minutes before the next opening."""
    if is_open(saved):
        return saved
    opening = next_open(saved)
    return saved if opening - saved <= timedelta(minutes=30) else opening - timedelta(minutes=10)


class SimClock:
    """Accelerated, pausable clock. `speed` is sim minutes per real minute."""

    def __init__(self, start: datetime = DEFAULT_START, speed: float = 15.0, paused: bool = False):
        self._base_sim = start
        self._base_real = time.monotonic()
        self.speed = speed
        self.cap: float | None = None  # pace governor: the model can't keep up with more than this
        self.paused = paused

    @property
    def effective(self) -> float:
        return self.speed if self.cap is None else min(self.speed, self.cap)

    def now(self) -> datetime:
        if self.paused:
            return self._base_sim
        elapsed = time.monotonic() - self._base_real
        return self._base_sim + timedelta(seconds=elapsed * self.effective)

    def _rebase(self) -> None:
        self._base_sim = self.now()
        self._base_real = time.monotonic()

    def pause(self) -> None:
        if not self.paused:
            self._rebase()
            self.paused = True

    def resume(self) -> None:
        if self.paused:
            self.paused = False
            self._base_real = time.monotonic()

    def set_speed(self, speed: float) -> None:
        self._rebase()
        self.speed = max(0.5, min(speed, 240.0))

    def set_cap(self, cap: float | None) -> None:
        self._rebase()
        self.cap = cap

    def skip_to(self, target: datetime) -> None:
        """Jump forward to target (never backwards)."""
        self._base_sim = max(target, self.now())
        self._base_real = time.monotonic()

    async def sleep_until(self, target: datetime) -> None:
        """Sleep until sim time reaches target, respecting pause and speed changes."""
        while self.now() < target:
            await asyncio.sleep(0.2)

    async def sleep(self, sim_seconds: float) -> None:
        await self.sleep_until(self.now() + timedelta(seconds=sim_seconds))

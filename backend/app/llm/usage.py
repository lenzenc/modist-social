from datetime import date

from app.config import settings


class Usage:
    """Token and dollar accounting, with a per-real-day budget guard."""

    def __init__(self) -> None:
        self.input = 0
        self.output = 0
        self.cache_read = 0
        self.cache_write = 0
        self.searches = 0
        self.calls = 0
        self.errors = 0
        self.today = date.today()
        self.spent_today = 0.0
        self.spent_total = 0.0
        self.budget = settings.daily_budget_usd

    def _roll(self) -> None:
        if date.today() != self.today:
            self.today = date.today()
            self.spent_today = 0.0

    def record(self, usage, searches: int = 0) -> float:
        """Add one response's `usage` block; returns the call's cost in USD."""
        self._roll()
        i = getattr(usage, "input_tokens", 0) or 0
        o = getattr(usage, "output_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cost = (
            i * settings.price_input
            + o * settings.price_output
            + cr * settings.price_cache_read
            + cw * settings.price_cache_write
        ) / 1_000_000 + searches * settings.price_web_search
        self.input += i
        self.output += o
        self.cache_read += cr
        self.cache_write += cw
        self.searches += searches
        self.calls += 1
        self.spent_today += cost
        self.spent_total += cost
        return cost

    def over_budget(self) -> bool:
        self._roll()
        return self.spent_today >= self.budget

    def snapshot(self) -> dict:
        self._roll()
        cacheable = self.input + self.cache_read + self.cache_write
        return {
            "calls": self.calls,
            "errors": self.errors,
            "input_tokens": self.input,
            "output_tokens": self.output,
            "cache_read_tokens": self.cache_read,
            "cache_write_tokens": self.cache_write,
            "cache_hit_pct": round(100 * self.cache_read / cacheable, 1) if cacheable else 0.0,
            "web_searches": self.searches,
            "spent_today": round(self.spent_today, 4),
            "spent_total": round(self.spent_total, 4),
            "budget": self.budget,
        }


usage = Usage()

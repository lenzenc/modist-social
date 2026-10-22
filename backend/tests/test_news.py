import asyncio
from datetime import datetime, timedelta

from app.llm.mock import MockLLM
from tests.test_newcomers import NOW, _director


def _desk(d, monkeypatch, lines, recent=()):
    seen = []

    async def news(city, date_text, rec):
        seen.append(rec)
        return lines

    async def recent_news(day):
        return list(recent)

    async def noop(*a, **k):
        return None

    d.llm = type("L", (), {"news": staticmethod(news)})()
    d.recent_news, d.post = recent_news, noop
    return seen


def test_news_desk_passes_recent_headlines_and_drops_repeats(monkeypatch):
    d, _ = _director(monkeypatch)
    seen = _desk(d, monkeypatch, ["Old one", "Fresh one"], recent=["Old one"])
    asyncio.run(d.news_desk("2026-10-20"))
    assert seen == [["Old one"]] and d.news == ["Fresh one"] and d.news_for == "2026-10-20"


def test_an_empty_fetch_is_retried_an_hour_later_until_evening(monkeypatch):
    d, _ = _director(monkeypatch)
    _desk(d, monkeypatch, [])
    d.clock.now = lambda: datetime(2026, 10, 20, 11, 0)
    d.news_day = "2026-10-20"
    asyncio.run(d.news_desk("2026-10-20"))
    assert d.news_day == "" and d.news_retry_at == datetime(2026, 10, 20, 12, 0)
    d.clock.now = lambda: datetime(2026, 10, 20, 20, 30)
    asyncio.run(d.news_desk("2026-10-20"))
    assert d.news_retry_at == datetime(2026, 10, 20, 12, 0)  # evening: no new retry scheduled


def test_mock_news_avoids_recent_headlines():
    from app.llm import mock

    recent = mock._NEWS[:6]
    for _ in range(20):
        assert not set(asyncio.run(MockLLM().news("x", "y", recent))) & set(recent)

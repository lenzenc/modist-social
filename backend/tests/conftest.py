import asyncio

import pytest

from app.db.models import engine, init_db


async def _prepare() -> None:
    await init_db()
    await engine.dispose()  # connections must not outlive this event loop


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Some tests write through the real session, so make sure the tables (and later-added columns) exist."""
    asyncio.run(_prepare())

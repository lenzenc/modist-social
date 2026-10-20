from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "person"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))  # patron | bartender
    pronouns: Mapped[str] = mapped_column(String(16))
    color: Mapped[str] = mapped_column(String(8))
    persona: Mapped[dict] = mapped_column(JSON)


class Relationship(Base):
    __tablename__ = "relationship"

    # a_id < b_id always, see relationships.pair_key
    a_id: Mapped[str] = mapped_column(ForeignKey("person.id"), primary_key=True)
    b_id: Mapped[str] = mapped_column(ForeignKey("person.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="stranger")
    familiarity: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    affinity: Mapped[int] = mapped_column(Integer, default=0)  # -100..100
    notes: Mapped[str] = mapped_column(Text, default="")
    met_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Memory(Base):
    __tablename__ = "memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), index=True)
    sim_ts: Mapped[datetime] = mapped_column(DateTime)
    text: Mapped[str] = mapped_column(Text)
    about: Mapped[list] = mapped_column(JSON, default=list)  # person ids
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1..10
    kind: Mapped[str] = mapped_column(String(16), default="event")  # event | reflection | followup | done


class Thread(Base):
    __tablename__ = "thread"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="chat")  # chat | order | staff
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    root_text: Mapped[str] = mapped_column(Text, default="")
    participants: Mapped[list] = mapped_column(JSON, default=list)  # every person id who joined


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int | None] = mapped_column(ForeignKey("thread.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    speaker_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="speech")  # speech | system
    text: Mapped[str] = mapped_column(Text)
    sim_ts: Mapped[datetime] = mapped_column(DateTime)
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)  # the speaker's private thought, never shown in chat


class Payment(Base):
    """One credit-card transaction: a single drink (per_drink) or a whole tab. Amounts are cents."""

    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), index=True)
    bartender_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # per_drink | tab
    status: Mapped[str] = mapped_column(String(8), default="open", index=True)  # open | closed
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    tip_pct: Mapped[int] = mapped_column(Integer, default=0)
    tip: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    card_brand: Mapped[str] = mapped_column(String(16))
    card_last4: Mapped[str] = mapped_column(String(4))


class SaleItem(Base):
    """One drink poured and what it cost, tied to the payment that settles it."""

    __tablename__ = "sale_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payment.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), index=True)
    bartender_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drink: Mapped[str] = mapped_column(String(96), index=True)
    list_price: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)
    happy_hour: Mapped[bool] = mapped_column(Boolean, default=False)
    sim_ts: Mapped[datetime] = mapped_column(DateTime, index=True)


class NewsItem(Base):
    __tablename__ = "news_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sim_day: Mapped[str] = mapped_column(String(10), index=True)
    text: Mapped[str] = mapped_column(Text)


class SimState(Base):
    __tablename__ = "sim_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


# create_all never alters an existing table, so columns added after first launch are added here (idempotent).
_COLUMNS = (
    "ALTER TABLE memory ADD COLUMN IF NOT EXISTS importance INTEGER NOT NULL DEFAULT 5",
    "ALTER TABLE memory ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'event'",
    "ALTER TABLE relationship ADD COLUMN IF NOT EXISTS met_at TIMESTAMP NULL",
    "ALTER TABLE message ADD COLUMN IF NOT EXISTS thought TEXT NULL",
    "UPDATE thread SET channel = 'inside-tables' WHERE channel = 'high-tops'",
    "UPDATE message SET channel = 'inside-tables' WHERE channel = 'high-tops'",
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _COLUMNS:
            await conn.execute(text(stmt))


async def get_state(session: AsyncSession, key: str, default: dict | None = None) -> dict | None:
    row = await session.get(SimState, key)
    return row.value if row else default


async def set_state(session: AsyncSession, key: str, value: dict) -> None:
    row = await session.get(SimState, key)
    if row:
        row.value = value
    else:
        session.add(SimState(key=key, value=value))

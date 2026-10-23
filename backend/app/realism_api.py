"""Read-only realism reporting: grades a sim day or week of speech with sim.realism.score."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.models import LifeEvent, Message, Person, Session, Thread, get_state
from app.sim import life, realism
from app.sim.state import display_name

router = APIRouter(prefix="/api/realism")

PRIOR_DAYS = 3  # earlier days compared against when judging topic variety


def _bounds(period: str, day: date) -> tuple[date, date]:
    if period == "day":
        return day, day + timedelta(days=1)
    if period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    raise HTTPException(400, "period must be day or week")


def _day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD") from None


def _topics(lines: list[tuple[int | None, str, str]], threads: dict[int, dict]) -> Counter:
    by: dict[int, list[str]] = defaultdict(list)
    for tid, _, text in lines:
        if tid is not None and threads.get(tid, {}).get("kind") == "chat":
            by[tid].append(text)
    return Counter(realism.topic_of(" ".join(ts)) for ts in by.values())


@router.get("/summary")
async def summary(period: str = "day", date: str = ""):
    async with Session() as s:
        saved = await get_state(s, "clock", {}) or {}
        day = _day(date) if date else (datetime.fromisoformat(saved["sim_now"]).date() if saved.get("sim_now") else datetime.now().date())
        start, end = _bounds(period, day)
        lo = datetime.combine(start - timedelta(days=PRIOR_DAYS), time.min)
        rows = (await s.execute(
            select(Message.thread_id, Message.speaker_id, Message.text, Message.sim_ts, Thread.kind)
            .join(Thread, Thread.id == Message.thread_id)
            .where(Message.kind == "speech", Message.speaker_id.is_not(None),
                   Message.sim_ts >= lo, Message.sim_ts < datetime.combine(end, time.min))
            .order_by(Message.id)
        )).all()
        names = {pid: display_name(n) for pid, n in (await s.execute(select(Person.id, Person.name))).all()}
        events: dict[str, list[life.LifeEventRec]] = defaultdict(list)
        for r in (await s.scalars(select(LifeEvent).where(
            LifeEvent.started_at < datetime.combine(end, time.min), LifeEvent.ends_at > datetime.combine(start, time.min)
        ))).all():
            events[r.person_id].append(life.LifeEventRec(
                kind=r.kind, text=r.text, started_at=r.started_at, ends_at=r.ends_at, cat=r.cat, keys=list(r.keys or []),
                resolved=r.resolved, id=r.id))

    threads = {tid: {"kind": kind} for tid, _, _, _, kind in rows}
    by_day: dict[date, list[tuple[int | None, str, str]]] = defaultdict(list)
    for tid, sid, text, ts, _ in rows:
        by_day[ts.date()].append((tid, sid, text))
    topic_days = {d: _topics(ls, threads) for d, ls in by_day.items()}

    def grade(days: list[date]) -> dict:
        lines = [l for d in days for l in by_day.get(d, [])]
        prior = [topic_days[d] for d in topic_days if days[0] - timedelta(days=PRIOR_DAYS) <= d < days[0]]
        return realism.score(lines, threads, prior, names)

    days = [start + timedelta(days=i) for i in range((end - start).days)]
    result = grade(days)
    series = []
    for d in days:
        g = grade([d])
        series.append({"key": d.isoformat(), "label": d.strftime("%a %-d"), "overall": g["overall"], **g["metrics"]})
    in_range = [(d, sid, text) for d in days for _, sid, text in by_day.get(d, [])]
    return {
        "range": {"start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(), "period": period},
        **result, "series": series, "life": life.continuity(in_range, events, names),
    }


@router.get("/days")
async def days():
    async with Session() as s:
        first = (await s.execute(select(Message.sim_ts).order_by(Message.id).limit(1))).scalar()
        last = (await s.execute(select(Message.sim_ts).order_by(Message.id.desc()).limit(1))).scalar()
    return {"first": first.date().isoformat() if first else None, "last": last.date().isoformat() if last else None}

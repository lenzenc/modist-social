"""Read-only realism reporting: grades a sim day or week of speech with sim.realism.score."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.models import BondChange, LifeEvent, Memory, Message, Person, SaleItem, Session, Thread, get_state
from app.sim import beats, bonds, drunk, dynamics, gossip, life, occasions, realism, staff, taste
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
        drunk_log = [h for h in (await get_state(s, "drunk_log", []) or []) if start.isoformat() <= h["day"] < end.isoformat()]
        gossip_log = [e for e in (await get_state(s, "gossip_log", []) or []) if start.isoformat() <= e["day"] < end.isoformat()]
        taste_log = [e for e in (await get_state(s, "taste_log", []) or []) if start.isoformat() <= e["day"] < end.isoformat()]
        group_log = [e for e in (await get_state(s, "group_log", []) or []) if start.isoformat() <= e["day"] < end.isoformat()]
        staff_log = [e for e in (await get_state(s, "staff_log", []) or []) if start.isoformat() <= e["day"] < end.isoformat()]
        calendar_log = [e for e in (await get_state(s, "calendar_log", []) or []) if start.isoformat() <= e["day"] < end.isoformat()]
        history = await get_state(s, "history", []) or []
        sold = (await s.execute(select(SaleItem.person_id, SaleItem.drink).where(
            SaleItem.sim_ts >= datetime.combine(start, time.min), SaleItem.sim_ts < datetime.combine(end, time.min),
            SaleItem.buyer_id.is_(None)).order_by(SaleItem.id))).all()
        heard = (await s.scalars(select(Memory).where(
            Memory.source_id.is_not(None), Memory.sim_ts >= datetime.combine(start, time.min),
            Memory.sim_ts < datetime.combine(end, time.min)))).all()
        rumor_rows = [{"id": m.id, "source_id": m.source_id, "origin_id": m.origin_id, "hops": m.hops, "accuracy": m.accuracy}
                      for m in heard]
        top = sorted({r["origin_id"] for r in rumor_rows if r["origin_id"] is not None},
                     key=lambda o: -max(r["hops"] for r in rumor_rows if r["origin_id"] == o))[:3]
        trails = (await s.scalars(select(Memory).where(Memory.origin_id.in_(top)).order_by(Memory.id))).all() if top else []
        acted = (await s.scalars(select(Message.speaker_id).where(
            Message.kind == "action", Message.sim_ts >= datetime.combine(start, time.min),
            Message.sim_ts < datetime.combine(end, time.min)))).all()
        moves = (await s.scalars(select(BondChange).where(
            BondChange.sim_ts >= datetime.combine(start, time.min), BondChange.sim_ts < datetime.combine(end, time.min)
        ).order_by(BondChange.id.desc()))).all()
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
    patron_days = len({(d, sid) for d, sid, _ in in_range if not sid.startswith("b")})
    listed = [{"a": names.get(c.a_id, c.a_id), "b": names.get(c.b_id, c.b_id), "from": c.from_bond, "to": c.to_bond,
               "why": c.why, "day": c.sim_ts.date().isoformat()} for c in moves[:30]]
    return {
        "bonds": {"changes": len(moves), "patron_days": patron_days, "list": listed, **bonds.drama(len(moves), patron_days, len(days))},
        "range": {"start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(), "period": period},
        **result, "series": series, "life": life.continuity(in_range, events, names),
        "drunk": drunk.consequences(drunk_log),
        "staff": staff.report(staff_log),
        "rhythm": {**occasions.report(calendar_log, history, in_range, end - timedelta(days=1)), "list": list(reversed(history))[:10]},
        "taste": taste.habits(taste_log, [(pid, drink) for pid, drink in sold]),
        "groups": dynamics.report(group_log, [l for d in days for l in by_day.get(d, [])], threads, patron_days),
        "quiet": beats.quiet_share(len(acted), len(in_range), sum(1 for a in acted if a is None)),
        "gossip": {**gossip.spread(rumor_rows, gossip_log), "trails": _trails(top, trails, names)},
    }


def _trails(top: list[int], rows: list[Memory], names: dict[str, str]) -> list[dict]:
    """The longest rumor chains, each as the versions of it that were told in order."""
    out = []
    for origin in top:
        versions = [{
            "who": names.get(m.person_id, m.person_id), "from": names.get(m.source_id, "") if m.source_id else "",
            "text": m.text, "hops": m.hops, "confidence": m.confidence, "accuracy": m.accuracy,
            "about": [names.get(i, i) for i in (m.about or [])],
        } for m in rows if m.origin_id == origin]
        out.append({"origin": origin, "versions": sorted(versions, key=lambda v: v["hops"])})
    return out


@router.get("/days")
async def days():
    async with Session() as s:
        first = (await s.execute(select(Message.sim_ts).order_by(Message.id).limit(1))).scalar()
        last = (await s.execute(select(Message.sim_ts).order_by(Message.id.desc()).limit(1))).scalar()
    return {"first": first.date().isoformat() if first else None, "last": last.date().isoformat() if last else None}


@router.get("/history")
async def room_history():
    """The nights the room remembers, newest first."""
    async with Session() as s:
        rows = await get_state(s, "history", []) or []
    return list(reversed(rows))

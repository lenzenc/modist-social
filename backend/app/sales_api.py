"""Read-only sales reporting. Drinks count on the sim day they were poured; tips and card totals on the day the payment closed."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import Date, case, cast, exists, extract, func, select

from app.db.models import Payment, Person, SaleItem, Session, get_state
from app.sim.clock import HOURS
from app.sim.state import display_name

router = APIRouter(prefix="/api/sales")


def _bounds(period: str, day: date) -> tuple[datetime, datetime]:
    if period == "day":
        start = day
        end = day + timedelta(days=1)
    elif period == "week":
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=7)
    elif period == "month":
        start = day.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    else:
        raise HTTPException(400, "period must be day, week or month")
    return datetime.combine(start, time.min), datetime.combine(end, time.min)


def _day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD") from None


async def _names(s) -> dict[str, str]:
    return {pid: display_name(name) for pid, name in (await s.execute(select(Person.id, Person.name))).all()}


@router.get("/summary")
async def summary(period: str = "day", date: str = "", drink: str = "", person_id: str = ""):
    day = _day(date) if date else datetime.now().date()
    start, end = _bounds(period, day)

    item_where = [SaleItem.sim_ts >= start, SaleItem.sim_ts < end]
    if drink:
        item_where.append(SaleItem.drink == drink)
    if person_id:
        item_where.append(SaleItem.person_id == person_id)
    pay_where = [Payment.status == "closed", Payment.closed_at >= start, Payment.closed_at < end]
    if person_id:
        pay_where.append(Payment.person_id == person_id)

    async with Session() as s:
        names = await _names(s)
        saved = await get_state(s, "clock", {}) or {}
        t = (await s.execute(select(
            func.coalesce(func.sum(SaleItem.price), 0),
            func.count(SaleItem.id),
            func.coalesce(func.sum(case((SaleItem.happy_hour, 1), else_=0)), 0),
            func.coalesce(func.sum(SaleItem.list_price - SaleItem.price), 0),
            func.count(func.distinct(SaleItem.person_id)),
        ).where(*item_where))).one()
        pay = (await s.execute(select(
            func.coalesce(func.sum(Payment.tip), 0), func.coalesce(func.sum(Payment.total), 0), func.count(Payment.id),
        ).where(*pay_where))).one()

        # Series: by hour for a day, by calendar day otherwise.
        if period == "day":
            bucket = extract("hour", SaleItem.sim_ts)
            pbucket = extract("hour", Payment.closed_at)
        else:
            bucket = cast(SaleItem.sim_ts, Date)
            pbucket = cast(Payment.closed_at, Date)
        sold = {b: (sales, n) for b, sales, n in (await s.execute(
            select(bucket, func.sum(SaleItem.price), func.count(SaleItem.id)).where(*item_where).group_by(bucket)
        )).all()}
        tipped = dict((await s.execute(
            select(pbucket, func.sum(Payment.tip)).where(*pay_where).group_by(pbucket)
        )).all())

        by_drink = [{"drink": d, "qty": q, "hh_qty": int(h), "sales": int(v)} for d, q, h, v in (await s.execute(
            select(SaleItem.drink, func.count(SaleItem.id), func.sum(case((SaleItem.happy_hour, 1), else_=0)),
                   func.sum(SaleItem.price)).where(*item_where).group_by(SaleItem.drink)
            .order_by(func.count(SaleItem.id).desc(), SaleItem.drink)
        )).all()]

        person_rows = (await s.execute(
            select(SaleItem.person_id, func.count(SaleItem.id), func.sum(SaleItem.price))
            .where(*item_where).group_by(SaleItem.person_id)
        )).all()
        bought = {pid: int(n) for pid, n in (await s.execute(
            select(SaleItem.buyer_id, func.count(SaleItem.id)).where(*item_where, SaleItem.buyer_id.is_not(None))
            .group_by(SaleItem.buyer_id)
        )).all()}
        tips_by_person = {pid: (tip, tabs, cards) for pid, tip, tabs, cards in (await s.execute(
            select(Payment.person_id, func.sum(Payment.tip), func.sum(case((Payment.kind == "tab", 1), else_=0)),
                   func.sum(case((Payment.kind == "tab", 0), else_=1))).where(*pay_where).group_by(Payment.person_id)
        )).all()}
    by_person = []
    for pid, n, v in person_rows:
        tip, tabs, cards = tips_by_person.get(pid, (0, 0, 0))
        by_person.append({"id": pid, "name": names.get(pid, pid), "drinks": n, "sales": int(v), "tips": int(tip or 0),
                          "tabs": int(tabs or 0), "per_drink": int(cards or 0), "bought_for_others": bought.get(pid, 0)})
    by_person.sort(key=lambda r: (-r["sales"], r["name"]))

    series = []
    if period == "day":
        o, c = HOURS[start.weekday()]
        for h in range(o, min(c, 24)):
            v, n = sold.get(h, (0, 0))
            series.append({"key": f"{h:02d}", "label": _hour(h), "sales": int(v), "drinks": n, "tips": int(tipped.get(h, 0) or 0)})
    else:
        d = start
        while d < end:
            v, n = sold.get(d.date(), (0, 0))
            series.append({"key": d.date().isoformat(), "label": d.strftime("%a %-d"), "sales": int(v), "drinks": n,
                           "tips": int(tipped.get(d.date(), 0) or 0)})
            d += timedelta(days=1)

    sales_total, drinks = int(t[0]), t[1]
    return {
        "range": {"start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat(), "period": period},
        "totals": {
            "sales": sales_total, "tips": 0 if drink else int(pay[0]), "charged": 0 if drink else int(pay[1]),
            "drinks": drinks, "transactions": 0 if drink else pay[2], "guests": t[4],
            "avg_ticket": int(pay[1] / pay[2]) if pay[2] and not drink else 0,
            "happy_hour_drinks": int(t[2]), "discount": int(t[3]),
        },
        # Days run with the crowd turned up or down, so a busy night isn't mistaken for a normal one.
        "crowd": {d: v for d, v in (saved.get("crowd_days") or {}).items()
                  if start.date().isoformat() <= d < end.date().isoformat() and v != 1.0},
        "series": series, "by_drink": by_drink, "by_person": by_person,
    }


def _hour(h: int) -> str:
    return f"{h % 12 or 12}{'a' if h < 12 else 'p'}"


def _tx(p: Payment, items: list[SaleItem], names: dict[str, str]) -> dict:
    return {
        "id": p.id, "person_id": p.person_id, "name": names.get(p.person_id, p.person_id), "kind": p.kind,
        "status": p.status, "opened_at": p.opened_at.isoformat(), "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        "bartender": names.get(p.bartender_id or "", ""), "subtotal": p.subtotal, "tip_pct": p.tip_pct, "tip": p.tip,
        "total": p.total, "card": f"{p.card_brand} ••{p.card_last4}",
        "items": [{"drink": i.drink, "price": i.price, "list_price": i.list_price, "happy_hour": i.happy_hour,
                   "at": i.sim_ts.isoformat(), "for": names.get(i.person_id, i.person_id) if i.buyer_id else None}
                  for i in items],
    }


async def _payments(s, where: list, limit: int = 500) -> list[dict]:
    pays = (await s.scalars(select(Payment).where(*where).order_by(Payment.id.desc()).limit(limit))).all()
    items: dict[int, list[SaleItem]] = defaultdict(list)
    if pays:
        for i in (await s.scalars(
            select(SaleItem).where(SaleItem.payment_id.in_([p.id for p in pays])).order_by(SaleItem.id)
        )).all():
            items[i.payment_id].append(i)
    names = await _names(s)
    return [_tx(p, items[p.id], names) for p in pays]


@router.get("/transactions")
async def transactions(period: str = "day", date: str = "", person_id: str = "", drink: str = ""):
    day = _day(date) if date else datetime.now().date()
    start, end = _bounds(period, day)
    where = [Payment.status == "closed", Payment.closed_at >= start, Payment.closed_at < end]
    if person_id:
        where.append(Payment.person_id == person_id)
    if drink:
        where.append(exists().where(SaleItem.payment_id == Payment.id, SaleItem.drink == drink))
    async with Session() as s:
        return await _payments(s, where)


@router.get("/open-tabs")
async def open_tabs():
    async with Session() as s:
        return await _payments(s, [Payment.status == "open"])


@router.get("/days")
async def days():
    async with Session() as s:
        lo, hi = (await s.execute(select(func.min(SaleItem.sim_ts), func.max(SaleItem.sim_ts)))).one()
    return {"first": lo.date().isoformat() if lo else None, "last": hi.date().isoformat() if hi else None}

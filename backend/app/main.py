import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.bus import bus
from app.config import settings
from app.db.models import BondChange, Message, Session, Thread, init_db
from app.llm import make_llm
from app.llm.usage import usage
from app.realism_api import router as realism_router
from app.sales_api import router as sales_router
from app.seed.loader import seed_if_empty
from app.sim import god as godmode
from app.sim import drunk, life, occasions, staff, taste
from app.sim.director import Director
from app.sim.state import CHANNEL_DESC, CHANNELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

director: Director


async def _wait_for_db() -> None:
    for attempt in range(30):
        try:
            await init_db()
            return
        except Exception as e:  # DB container may still be starting
            log.info("waiting for database (%s)", type(e).__name__)
            await asyncio.sleep(1 + attempt * 0.2)
    raise RuntimeError("database never became ready")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global director
    await _wait_for_db()
    await seed_if_empty()
    director = Director(make_llm())
    await director.load()
    log.info("LLM mode: %s (%s)", settings.llm_mode, settings.model)
    if settings.llm_mode == "live" and not (
        settings.anthropic_api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE")
    ):
        director.halt("No ANTHROPIC_API_KEY found. Add it to .env (or set LLM_MODE=mock), then restart the backend.")
    runner = asyncio.create_task(director.run())
    yield
    runner.cancel()
    await director.stop()


app = FastAPI(title="Modist Social", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(sales_router)
app.include_router(realism_router)


def _person(p) -> dict:
    return director.person_view(p)


def _msg(m: Message) -> dict:
    return {
        "id": m.id, "thread_id": m.thread_id, "channel": m.channel, "speaker_id": m.speaker_id,
        "kind": m.kind, "text": m.text, "sim_ts": m.sim_ts.isoformat(),
    }


@app.get("/api/bootstrap")
async def bootstrap():
    return {
        "channels": [{"id": c, "desc": CHANNEL_DESC[c]} for c in CHANNELS],
        "people": [_person(p) for p in director.people.values()],
        "clock": director.clock_event(),
        "news": director.news,
        "stats": usage.snapshot(),
        "banner": director.banner,
        "llm_mode": settings.llm_mode,
        "city": settings.brewery_city,
    }


@app.get("/api/channels/{channel}/feed")
async def feed(channel: str, limit: int = 60):
    if channel not in CHANNELS:
        raise HTTPException(404)
    async with Session() as s:
        threads = (await s.scalars(
            select(Thread).where(Thread.channel == channel).order_by(Thread.id.desc()).limit(limit)
        )).all()
        ids = [t.id for t in threads]
        counts = dict((await s.execute(
            select(Message.thread_id, func.count()).where(Message.thread_id.in_(ids)).group_by(Message.thread_id)
        )).all()) if ids else {}
        last_rows = (await s.scalars(
            select(Message).where(Message.id.in_(
                select(func.max(Message.id)).where(Message.thread_id.in_(ids), Message.kind == "speech")
                .group_by(Message.thread_id)
            ))
        )).all() if ids else []
        last = {m.thread_id: {"speaker_id": m.speaker_id, "text": m.text} for m in last_rows}
        loose = (await s.scalars(
            select(Message).where(Message.channel == channel, Message.thread_id.is_(None))
            .order_by(Message.id.desc()).limit(100)
        )).all()
    live = director.threads
    return {
        "threads": [{
            "id": t.id, "channel": t.channel, "kind": t.kind, "started_at": t.started_at.isoformat(),
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "participants": t.participants, "count": counts.get(t.id, 0), "last": last.get(t.id),
            "root_text": director._root_text(live[t.id]) if t.id in live else _stored_root(t),
        } for t in reversed(threads)],
        "messages": [_msg(m) for m in reversed(loose)],
    }


def _stored_root(t: Thread) -> str:
    names = [director.people[i].short for i in t.participants if i in director.people]
    if not names:
        return "A conversation"
    if t.kind == "order":
        guest = next((director.people[i] for i in t.participants if i in director.people and not director.people[i].is_bartender), None)
        return f"{(guest or director.people[t.participants[0]]).short} steps up to the bar"
    if t.kind == "staff":
        return f"{' and '.join(names)} catch up behind the bar"
    head = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
    return f"{head} {'were' if len(names) > 1 else 'was'} chatting"


@app.get("/api/threads/{thread_id}/messages")
async def thread_messages(thread_id: int):
    async with Session() as s:
        rows = (await s.scalars(select(Message).where(Message.thread_id == thread_id).order_by(Message.id))).all()
    return [_msg(m) for m in rows]


@app.get("/api/people/{pid}")
async def person(pid: str):
    p = director.people.get(pid)
    if not p:
        raise HTTPException(404)
    social = director.social
    rels = []
    for (a, b), r in social.rels.items():
        if pid not in (a, b) or r.familiarity <= 0:
            continue
        o = director.people[b if a == pid else a]
        rels.append({
            "id": o.id, "name": o.display, "kind": r.kind, "familiarity": r.familiarity,
            "affinity": r.affinity, "notes": r.notes, "color": o.color,
            "bond": r.bond or "stranger", "bond_since": r.bond_since.isoformat() if r.bond_since else None,
        })
    rels.sort(key=lambda r: -r["familiarity"])
    mems = [{
        "sim_ts": m.sim_ts.isoformat(), "text": m.text, "importance": m.importance, "kind": m.kind,
        "about": [director.people[i].short for i in m.about if i in director.people],
        "source": director.people[m.source_id].short if m.source_id in director.people else None,
        "confidence": m.confidence if m.source_id else None, "accuracy": m.accuracy if m.source_id else None,
        "hops": m.hops if m.source_id else None,
    } for m in reversed(social.memories.get(pid, [])[-40:])]
    state = {
        "reason": p.reason, "mood": round(p.mood, 2), "buzz": round(p.buzz, 2), "battery": round(p.battery, 2),
        "need": p.need, "thought": p.thought, "drinks": p.drinks, "tier": drunk.tier(p.buzz), "cut_off": p.cut_off,
        "on_water": p.on_water_until is not None and director.clock.now() < p.on_water_until, "slops": p.slops,
        "cap": p.cap, "spent": p.spent,
    } if p.present and not p.is_bartender else None
    sh = director.staff.get(pid) if p.is_bartender and p.present else None
    shift_view = {
        "mood": round(p.mood, 2), "energy": staff.tired_word(sh), "rough": sh.rough, "served": sh.served,
        "wrong": sh.wrong, "spills": sh.spills, "pours": sh.pours, "poured": list(dict.fromkeys(sh.poured))[-3:],
        "feeling": staff.buzz_word(p.buzz), "peeve": staff.PEEVES.get(str(p.persona.get("peeve", "")), ""),
        "gripe": director.people[sh.gripe].short if sh.gripe in director.people else "",
    } if sh else None
    rec = director.taste_of(p) if not p.is_bartender else None
    day = director.clock.now().strftime("%Y-%m-%d")
    taste_view = {
        "favorites": taste.top(rec), "tired_of": taste.tired_of(rec, day), "budget": taste.budget(p.persona),
        "owes": {director.people[i].short: n for i, n in rec.owes.items() if n and i in director.people},
    } if rec else None
    async with Session() as s:
        changes = (await s.scalars(select(BondChange).where(or_(BondChange.a_id == pid, BondChange.b_id == pid))
                                   .order_by(BondChange.id.desc()).limit(5))).all()
    bond_changes = [{
        "with": director.people[c.b_id if c.a_id == pid else c.a_id].short, "from": c.from_bond, "to": c.to_bond,
        "why": c.why, "sim_ts": c.sim_ts.isoformat(),
    } for c in changes]
    return {**_person(p), "persona": p.persona, "relationships": rels[:30], "bond_changes": bond_changes, "memories": mems, "state": state, "shift": shift_view,
            "lately": director.lives.get(pid, ""), "birthday": None if p.is_bartender else list(occasions.birthday(pid, p.persona)),
            "moved": director.moved.get(pid), "visits": director.visits.get(pid, {}).get("n", 0), "taste": taste_view,
            "life": [{"text": e.text, "cat": e.cat, "started_at": e.started_at.isoformat(), "ends_at": e.ends_at.isoformat(),
                      "active": life.freshness(e, director.clock.now()) > 0}
                     for e in reversed(director.life.get(pid, [])[-5:])]}


@app.get("/api/realism/avoid/{pid}")
async def realism_avoid(pid: str):
    """The worn-out phrases the next prompt would tell this person to avoid (for checking the feedback loop)."""
    if pid not in director.people:
        raise HTTPException(404)
    return {"avoid": director.realism.avoid_for(pid), "opening": director.realism.avoid_for(pid, first_line=True),
            "tidy_share": round(director.realism.tidy_share(), 2), "feedback": settings.realism_feedback}


@app.get("/api/stats")
async def stats():
    return usage.snapshot()


class Control(BaseModel):
    action: str  # pause | resume | speed | crowd
    speed: float | None = None
    crowd: float | None = None
    extra_budget: float | None = None


@app.post("/api/sim/control")
async def control(body: Control):
    if body.action not in ("pause", "resume", "speed", "crowd"):
        raise HTTPException(400, "unknown action")
    director.control(body.action, body.speed, body.extra_budget, body.crowd)
    return director.clock_event()


class GodText(BaseModel):
    text: str


class God(GodText):
    reach: int | None = Field(default=None, ge=1, le=5)
    divisiveness: int | None = Field(default=None, ge=1, le=5)


@app.post("/api/sim/god/assess")
async def god_assess(body: GodText):
    """Score an event without setting it: reach, divisiveness and the two sides."""
    text = godmode.clean(body.text)
    if not text:
        raise HTTPException(400, "describe what happened")
    return godmode.public(await director.assess_god(text))


@app.post("/api/sim/god")
async def god_on(body: God):
    text = godmode.clean(body.text)
    if not text:
        raise HTTPException(400, "describe what happened")
    await director.set_god(text, body.reach, body.divisiveness)
    return director.clock_event()


@app.delete("/api/sim/god")
async def god_off():
    await director.clear_god()
    return director.clock_event()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    with bus.subscribe() as q:
        recv = asyncio.create_task(ws.receive_text())
        try:
            await ws.send_json(director.clock_event())
            await ws.send_json({"type": "presence", "people": director.presence()})
            while True:
                get = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({get, recv}, return_when=asyncio.FIRST_COMPLETED)
                if recv in done:
                    get.cancel()
                    try:
                        recv.result()
                    except Exception:
                        break
                    recv = asyncio.create_task(ws.receive_text())
                    continue
                await ws.send_json(get.result())
        except Exception:
            pass
        finally:
            recv.cancel()

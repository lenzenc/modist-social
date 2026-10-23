import asyncio
import logging
import math
import random
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update

from app.agents import agent as agent_mod
from app.agents.memory import apply_bond, reflect_day, wrap_up
from app.agents.prompts import persona_prompt, world_prompt
from app.bus import bus
from app.config import settings
from app.db.models import LifeEvent, Message, NewsItem, Payment, Person, SaleItem, Session, SimState, Thread, get_state, set_state
from app.llm.usage import usage
from app.seed.loader import color_for
from app.sim import beats, bonds, drunk, dynamics, environment, human, life, newcomers, realism, taste
from app.sim import god as godmode
from app.sim import groups, menu, sales, seating
from app.sim.clock import DEFAULT_START, SimClock, is_open, launch_time, open_close
from app.sim.schedule import ARRIVAL_BOOST, arrival_rate, on_shift
from app.sim.social import Social
from app.sim.state import (
    BAR_STOOLS, LOC_DESC, LOCATIONS, MAX_GROUP, MAX_GROUP_BAR, TABLES, TABLE_PAIRS, TABLE_SEATS, PartyState, PersonState, ThreadState, Waiting, display_name, short_name,
)

log = logging.getLogger("director")

LAST_CALL_MIN = 30
WAIT_BEFORE_INTERRUPT = timedelta(minutes=2)  # a guest in line this long gets a chatting bartender
TICK = 0.5  # real seconds
SOCIAL_EVERY = 2.0  # real seconds
LINE_BUDGET = 60.0  # sim seconds the pace governor lets one model call cost, at most
CROWD_LEVELS = (0.6, 1.0, 1.6, 2.5)
GOD_ROSTER = 70  # most people described to the model when it scores a God Mode event
NEWCOMER_DAYS = [2, 3, 4, 5, 6]  # when walk-ins are most likely to appear (Wed-Sun)
NEWCOMER_WINDOW = [16, 21]
# arrival_rate boosts visits for the regulars and counts a bit more than the window's hours; this brings the walk-in
# count back to the per-week figure in settings, over the hours the bar is open before last call.
NEWCOMER_SCALE = ARRIVAL_BOOST * 1.2
PLUS_ONE_CHANCE = 0.2  # a walk-in who comes in with someone already here


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _prob(per_minute: float, minutes: float) -> float:
    return 1 - (1 - min(per_minute, 0.99)) ** max(minutes, 0.0)


class Director:
    def __init__(self, llm) -> None:
        self.llm = llm
        self.clock = SimClock(speed=settings.sim_speed)
        self.social = Social()
        self.realism = realism.Realism()
        self.people: dict[str, PersonState] = {}
        self.threads: dict[int, ThreadState] = {}
        self.news: list[str] = []
        self.rng = random.Random()
        self.world_text = world_prompt(settings.brewery_city)
        self.persona_text: dict[str, str] = {}
        self.tasks: set[asyncio.Task] = set()
        self.shift: tuple[str, str] | None = None
        self.news_day = ""
        self.news_for = ""
        self.news_retry_at: datetime | None = None
        self.last_call_day = ""
        self.opened_day = ""
        self.closed_day = ""
        self.lookups: list[datetime] = []
        self.cooldown: dict[tuple[str, str], datetime] = {}
        self.visits: dict[str, dict] = {}  # pid -> {"n": visits so far, "last": ISO time of the latest}
        self.lives: dict[str, str] = {}  # pid -> how their life stands lately, from the nightly reflection
        self.life: dict[str, list[life.LifeEventRec]] = {}  # pid -> off-screen events, active or recent
        self.life_day = ""  # the last sim day events were rolled for
        self.romance: dict[str, int] = {}  # sim day -> crushes and couples formed that day
        self.hangovers: dict[str, dict] = {}  # pid -> how their last drunk night went: see drunk.record
        self.drunk_log: list[dict] = []  # every drunk visit lately, for the scorecard
        self.tastes: dict[str, taste.TasteRec] = {}  # pid -> what they like to drink: see sim.taste
        self.taste_log: list[dict] = []  # switches, suggestions, skipped rounds and rounds bought, for the scorecard
        self.gossip_cred: dict[str, int] = {}  # pid -> how far others can trust what they pass on: see sim.gossip
        self.gossip_log: list[dict] = []  # rumors that reached their subject or got corrected, for the scorecard
        self.group_log: list[dict] = []  # splits, interruptions, jokes, steers and outsiders, for the scorecard
        self.beat_pool: dict[str, list[str]] = {}  # pid -> model-written idle beats not yet used
        self.beat_calls: list[datetime] = []  # when the batched beats call last ran
        self.beat_busy = False
        self.now_playing: tuple[str, str, datetime] | None = None  # (title, artist, until) on the jukebox
        self.last_song: datetime | None = None
        self.waved: dict[tuple[str, str], datetime] = {}  # (waver, arrival) -> when, for a nudge toward a chat
        self.generating = False  # a newcomer is being made right now
        self.parties: dict[int, PartyState] = {}  # parties holding tables right now
        self._party_seq = 0
        self.queue: list[Waiting] = []  # guests waiting on a bartender, longest first
        self.naming: set[str] = set()  # names of newcomers being made right now
        self._env_prev: datetime | None = None
        self._env_flags: set[str] = set()
        self.budget_paused = False
        self.banner = ""
        self.crowd = 1.0  # arrival/chat multiplier chosen in the header
        self.crowd_days: dict[str, float] = {}  # busiest crowd setting used on each sim day
        self.god: dict | None = None  # God Mode event: see sim.god.build
        self._assessed: tuple[str, dict] | None = None  # the last event scored by assess_god, so setting it is free
        self.latency = 0.0  # moving average of model call time, real seconds
        self._last_cap = 0.0
        self._last_tick_sim: datetime | None = None
        self._last_social_sim: datetime | None = None
        self._last_social_real = 0.0
        self._last_clock_pub = 0.0
        self._last_stats_pub = 0.0
        self._last_save = 0.0

    # ---------------------------------------------------------------- setup

    async def load(self) -> None:
        async with Session() as s:
            for p in (await s.scalars(select(Person))).all():
                self.people[p.id] = PersonState(
                    id=p.id, name=p.name, short=short_name(p.name), display=display_name(p.name),
                    role=p.role, pronouns=p.pronouns, color=p.color, persona=p.persona,
                )
            saved = await get_state(s, "clock")
            saved_god = await get_state(s, "god")
            self.visits = await get_state(s, "visits", {}) or {}
            self.lives = await get_state(s, "lives", {}) or {}
            self.life_day = (await get_state(s, "life_day", {}) or {}).get("day", "")
            self.hangovers = await get_state(s, "hangovers", {}) or {}
            self.drunk_log = await get_state(s, "drunk_log", []) or []
            self.tastes = {pid: taste.TasteRec.load(raw) for pid, raw in (await get_state(s, "taste", {}) or {}).items()}
            self.taste_log = await get_state(s, "taste_log", []) or []
            self.gossip_cred = await get_state(s, "gossip_cred", {}) or {}
            self.gossip_log = await get_state(s, "gossip_log", []) or []
            self.group_log = await get_state(s, "group_log", []) or []
        for p in self.people.values():
            self.persona_text[p.id] = persona_prompt(p, self.lives.get(p.id, ""))
        await self.social.load()
        await self.warm_realism()
        if saved:
            was = datetime.fromisoformat(saved["sim_now"])
            start = launch_time(was)
            if start != was:
                log.info("bar is closed at %s; skipping ahead to %s", was, start)
            self.clock = SimClock(start=start, speed=saved.get("speed", settings.sim_speed))
            self.crowd = saved.get("crowd", 1.0)
            self.crowd_days = saved.get("crowd_days", {})
            await self.save_clock()
        self.god = godmode.normalize(saved_god, self.clock.now())
        await self.load_life()
        today = self.clock.now().strftime("%Y-%m-%d")
        async with Session() as s:
            # A crash or restart can strand threads mid-conversation; nobody is in the room after a restart.
            await s.execute(update(Thread).where(Thread.ended_at.is_(None)).values(ended_at=self.clock.now()))
            # Likewise nobody is still at the bar to close a tab, so settle any left open.
            for pay in (await s.scalars(select(Payment).where(Payment.status == "open"))).all():
                self._finalize(pay, self.people.get(pay.person_id), self.clock.now())
            await s.commit()
            rows = (await s.scalars(select(NewsItem).where(NewsItem.sim_day == today))).all()
        if rows:
            self.news, self.news_day, self.news_for = [r.text for r in rows], today, today
        log.info("loaded %d people, sim time %s", len(self.people), self.clock.now())

    async def load_life(self) -> None:
        """Events still on someone's mind, or waiting on a follow-on."""
        now = self.clock.now()
        async with Session() as s:
            rows = (await s.scalars(select(LifeEvent).where(LifeEvent.ends_at > now - timedelta(days=1)).order_by(LifeEvent.id))).all()
        for r in rows:
            self.life.setdefault(r.person_id, []).append(life.LifeEventRec(
                kind=r.kind, text=r.text, started_at=r.started_at, ends_at=r.ends_at, cat=r.cat, keys=list(r.keys or []),
                next_kind=r.next_kind, due_at=r.due_at, resolved=r.resolved, id=r.id,
            ))

    async def life_step(self, day: str) -> None:
        """Once a sim day: arcs reach their endings and new things happen to people, whether or not they come in."""
        now = self.clock.now()
        d = now.date()
        for p in self.patrons():
            mine = self.life.setdefault(p.id, [])
            rng = random.Random(f"{p.id}:{day}:arcs")
            fresh = life.due_followups(mine, p.persona, now, rng) + life.roll_day(p.id, p.persona, mine, d)
            for rec in fresh:
                await self.strain_bond(p, rec, rng)
            await self.save_life(p.id, mine, fresh)
            for rec in fresh:
                await self.social.add_memory(p.id, now, life.memory_text(rec), [], life.IMPORTANCE.get(rec.cat, 5))
                self.spawn(self.polish_event(p, rec))
        await self.bond_day(now, day)
        await self.morning_after(now, day)
        for p in self.patrons():
            taste.daily(self.taste_of(p), day)
        await self.save_clock()

    async def morning_after(self, now: datetime, day: str) -> None:
        """Whoever overdid it last night remembers it today, and may owe someone an apology."""
        names = {pid: q.short for pid, q in self.people.items()}
        for pid, h in list(self.hangovers.items()):
            if h["written"] or h["day"] >= day or pid not in self.people:
                continue
            h["written"] = True
            await self.social.add_memory(pid, now, drunk.regret_text(h), list(h["with"]), drunk.MEMORY_IMPORTANCE)
            for text, about in drunk.regret_followups(h, names):
                await self.social.add_memory(pid, now, text, about, 6, kind="followup")

    def romance_ok(self, now: datetime) -> bool:
        return self.romance.get(now.strftime("%Y-%m-%d"), 0) < bonds.ROMANCE_PER_DAY

    def romance_used(self, now: datetime) -> None:
        day = now.strftime("%Y-%m-%d")
        self.romance = {day: self.romance.get(day, 0) + 1}

    async def strain_bond(self, p: PersonState, rec, rng: random.Random) -> None:
        """A fight off-screen with someone close can be a fight with someone in this room."""
        if rec.kind != "argument_with_partner_or_friend":
            return
        close = [(q, r) for q in self.patrons() if q.id != p.id and (r := self.social.rel(p.id, q.id)).bond in ("couple", "close_friends")]
        if not close or rng.random() >= 0.6:
            return
        q, _ = rng.choice(close)
        rec.text = rec.text.replace("someone close", q.short)
        await self.apply_bond_change(p.id, q.id, bonds.Change("falling_out", "a fight", until=self.clock.now() + timedelta(days=rng.uniform(*bonds.FALLOUT_DAYS))))

    async def apply_bond_change(self, a: str, b: str, ch: bonds.Change) -> None:
        await apply_bond(self, a, b, ch)

    async def bond_day(self, now: datetime, day: str) -> None:
        """Once a sim day: bonds drift while nobody is watching, and couples sometimes make a night of it."""
        for (a, b), rel in list(self.social.rels.items()):
            if a not in self.people or b not in self.people or rel.bond in ("", "stranger", "acquaintance", "friends", "close_friends"):
                continue
            rng = random.Random(f"{a}:{b}:{day}:bond")
            if ch := bonds.offscreen(rel, now, rng):
                await apply_bond(self, a, b, ch)
            elif bonds.date_night(rel, rng):
                pa, pb = self.people[a], self.people[b]
                if all(not x.present and x.visited_day != day and x.pending_arrival is None for x in (pa, pb)):
                    when = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=17 + rng.randint(0, 2), minutes=rng.choice([0, 15, 30, 45]))
                    pa.pending_arrival = pb.pending_arrival = max(when, now)

    async def save_life(self, pid: str, mine: list, fresh: list) -> None:
        """Write new events, and any change to resolved ones, to the database."""
        async with Session() as s:
            for rec in mine:
                if rec.id is not None and (row := await s.get(LifeEvent, rec.id)):
                    row.resolved, row.ends_at = rec.resolved, rec.ends_at
            for rec in fresh:
                row = LifeEvent(person_id=pid, kind=rec.kind, cat=rec.cat, text=rec.text, keys=rec.keys,
                                started_at=rec.started_at, ends_at=rec.ends_at, next_kind=rec.next_kind, due_at=rec.due_at)
                s.add(row)
                await s.flush()
                rec.id = row.id
            await s.commit()
        mine.extend(fresh)
        del mine[:-12]  # a person's long-ago events stay in the database, not in memory

    async def polish_event(self, p: PersonState, rec) -> None:
        """Make a template event personal. The template stands if the model is unavailable or says nothing usable."""
        if self.check_budget():
            return
        c = p.persona
        who = f"{p.display}, {c.get('age')}, {c.get('job')}. Interests: {', '.join(c.get('interests', []))}. Life: {c.get('life', '')}"
        text = await self.llm.polish(who, rec.text)
        text = (text or "").strip().strip('"').strip().rstrip(".")
        if not life.usable(text, p):
            return
        rec.text = text
        if rec.id is not None:
            async with Session() as s:
                if row := await s.get(LifeEvent, rec.id):
                    row.text = text
                    await s.commit()

    async def warm_realism(self) -> None:
        """Seed the repetition tracker from stored speech so a restart does not forget what is worn out."""
        async with Session() as s:
            rows = (await s.execute(
                select(Message.id, Message.thread_id, Message.speaker_id, Message.text)
                .where(Message.kind == "speech", Message.thread_id.is_not(None), Message.speaker_id.is_not(None))
                .order_by(Message.id.desc()).limit(realism.Realism.ROOM)
            )).all()
            firsts = set()
            if rows:
                firsts = {mid for mid, in (await s.execute(
                    select(func.min(Message.id)).where(Message.kind == "speech", Message.thread_id.in_({r[1] for r in rows}))
                    .group_by(Message.thread_id)
                )).all()}
        self.realism.warm([(sid, text, mid in firsts) for mid, _, sid, text in reversed(rows)])

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("task failed", exc_info=task.exception())

    async def stop(self) -> None:
        for t in list(self.tasks):
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.save_clock()

    def resolve(self, name: str) -> str | None:
        n = name.strip().lower()
        for p in self.people.values():
            if n in (p.short.lower(), p.display.lower(), p.name.lower().replace('"', "")):
                return p.id
        return None

    # ---------------------------------------------------------------- publishing

    def patrons(self):
        return [p for p in self.people.values() if not p.is_bartender]

    def person_view(self, p: PersonState) -> dict:
        """What the API and the websocket tell the UI about one person."""
        return {
            "id": p.id, "name": p.name, "short": p.short, "display": p.display, "role": p.role,
            "pronouns": p.pronouns, "color": p.color, "job": p.persona.get("job", ""),
            "present": p.present, "location": p.location, "thread_id": p.thread_id, "seated": p.seated, "drink": p.drink,
            "stool": p.stool, "table": p.table, "party": p.party, "waiting": p.waiting,
            "visits": self.visits.get(p.id, {}).get("n", 0), "walk_in": bool(p.persona.get("walkin")),
        }

    async def add_person(self, name: str, pronouns: str, persona: dict) -> PersonState:
        """Bring a brand-new person into the world: saved first (everything else points at their row), then live."""
        short, display = short_name(name), display_name(name)
        if any(q.short.lower() == short.lower() or q.display.lower() == display.lower() for q in self.people.values()):
            raise ValueError(f"someone here is already called {short} or {display}")
        n = 1 + max((int(i[1:]) for i in self.people if i[0] == "n" and i[1:].isdigit()), default=0)
        pid, color = f"n{n:03d}", color_for(len(self.people))
        async with Session() as s:
            s.add(Person(id=pid, name=name, role="patron", pronouns=pronouns, color=color, persona=persona))
            await s.commit()
        p = PersonState(id=pid, name=name, short=short, display=display, role="patron", pronouns=pronouns,
                        color=color, persona=persona)
        self.people[pid] = p
        self.persona_text[pid] = persona_prompt(p, "")
        bus.publish({"type": "person", "person": self.person_view(p)})
        return p

    def presence(self) -> list[dict]:
        return [
            {"id": p.id, "location": p.location, "thread_id": p.thread_id, "seated": p.seated, "drink": p.drink,
             "stool": p.stool, "table": p.table, "party": p.party, "waiting": p.waiting, "tier": drunk.tier(p.buzz)}
            for p in self.people.values() if p.present
        ]

    def publish_presence(self) -> None:
        bus.publish({"type": "presence", "people": self.presence()})

    def publish_relationships(self, ids: list[str]) -> None:
        bus.publish({"type": "relationships", "people": ids})

    def clock_event(self) -> dict:
        now = self.clock.now()
        return {
            "type": "clock", "sim_now": now.isoformat(), "speed": self.clock.speed,
            "effective_speed": round(self.clock.effective, 1), "crowd_level": self.crowd,
            "god": self.god_view(),
            "paused": self.clock.paused, "open": is_open(now),
            "on_shift": [b for b in (self.shift or ())], "budget_paused": self.budget_paused,
            "crowd": sum(1 for p in self.patrons() if p.present),
        }

    def god_view(self) -> dict | None:
        g = self.god
        if not g:
            return None
        now = self.clock.now()
        return {
            "text": g["text"], "reach": g["reach"], "divisiveness": g["divisiveness"], "sides": g["sides"],
            "reason": g["reason"], "heat": round(godmode.heat(g, now), 3), "fade": round(godmode.fade(g, now), 3),
        }

    def thread_event(self, t: ThreadState, ended: datetime | None = None) -> dict:
        last = next(((sid, text) for k, sid, text in reversed(t.lines) if k == "speech"), None)
        return {
            "type": "thread",
            "thread": {
                "id": t.id, "channel": t.channel, "kind": t.kind, "started_at": t.started.isoformat(),
                "ended_at": ended.isoformat() if ended else None, "participants": list(t.ever),
                "root_text": self._root_text(t), "count": len(t.lines), "table": t.table,
                "last": {"speaker_id": last[0], "text": last[1]} if last else None,
            },
        }

    def _root_text(self, t: ThreadState) -> str:
        people = [self.people[m] for m in t.ever if m in self.people]
        if t.kind == "order":
            guest = next((p for p in people if not p.is_bartender), people[0])
            if t.again:
                return f"{guest.short} orders another round"
            return f"{guest.short} takes a seat at the bar" if t.seated else f"{guest.short} steps up to the bar"
        guests, bts = [p.short for p in people if not p.is_bartender], [p.short for p in people if p.is_bartender]
        if t.kind == "chat" and t.channel == "bar" and guests and bts:
            return f"{_names(guests)} chatting with {_names(bts)} across the bar"
        names = [p.short for p in people]
        if t.kind == "staff":
            return f"{' and '.join(names)} catch up behind the bar"
        head = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
        return f"{head} {'are' if len(names) > 1 else 'is'} chatting"

    # ---------------------------------------------------------------- messages & threads

    async def post(self, channel: str, text: str, speaker: str | None = None, kind: str = "speech",
                   thread: ThreadState | None = None, thought: str | None = None) -> None:
        ts = self.clock.now()
        async with Session() as s:
            m = Message(thread_id=thread.id if thread else None, channel=channel, speaker_id=speaker,
                        kind=kind, text=text, sim_ts=ts, thought=thought or None)
            s.add(m)
            await s.commit()
        if thread:
            if kind == "speech" and speaker:
                self.realism.add(speaker, text, first=not any(k == "speech" for k, _, _ in thread.lines))
            thread.lines.append((kind, speaker or "", text))
        bus.publish({"type": "message", "message": {
            "id": m.id, "thread_id": m.thread_id, "channel": channel, "speaker_id": speaker,
            "kind": kind, "text": text, "sim_ts": ts.isoformat(),
        }})
        if thread:
            bus.publish(self.thread_event(thread))

    async def beat(self, p: PersonState, text: str, thread: ThreadState | None = None) -> None:
        """Something a person does rather than says, shown under their name."""
        await self.post(thread.channel if thread else (p.location or "door"), text, p.id, "action", thread)

    def song(self, now: datetime) -> tuple[str, str] | None:
        return self.now_playing[:2] if self.now_playing and now < self.now_playing[2] else None

    async def open_thread(self, channel: str, kind: str, members: list[str], max_turns: int,
                          seated: bool = False, again: bool = False, ask: bool = False) -> ThreadState:
        now = self.clock.now()
        async with Session() as s:
            row = Thread(channel=channel, kind=kind, started_at=now, participants=list(members))
            s.add(row)
            await s.commit()
        t = ThreadState(id=row.id, channel=channel, kind=kind, started=now, members=list(members),
                        ever=dict.fromkeys(members), max_turns=max_turns, seated=seated, again=again, ask=ask)
        if self.god and kind == "chat":
            self.roll_event(t)
        t.span = {m: [0, None] for m in members}
        for m in members:
            p = self.people[m]
            if not p.is_bartender:
                p.thread_id, p.free_since = t.id, None
        if kind == "chat" and channel in TABLES:
            self.seat_group(t)
        self.threads[t.id] = t
        bus.publish(self.thread_event(t))
        self.publish_presence()
        self.spawn(self.run_thread(t))
        return t

    def roll_event(self, t: ThreadState) -> None:
        """Decide whether a chat is about the God Mode event. Fans and the affected join in; the indifferent mostly don't."""
        now = self.clock.now()
        guests = [self.people[m] for m in t.members if not self.people[m].is_bartender]
        cares = any(godmode.stance(self.god, g.id, g.persona) != "shrug" for g in guests)
        was = t.on_event
        openness = sum(human.event_interest(g.persona) for g in guests) / len(guests) if guests else 1.0
        t.on_event = self.rng.random() < godmode.chance(self.god, now) * (1.0 if cares else 0.4) * openness
        if t.on_event and not was:
            t.max_turns += godmode.stretch(self.god, now)

    def seat_group(self, t: ThreadState) -> None:
        """Put a new chat at one table: a member's own table if the group fits there, else the emptiest."""
        guests = [m for m in t.members if not self.people[m].is_bartender]
        mine = {self.people[m].table for m in guests} - {None}
        fits = [i for i in mine if len([q for q in self.table_occupants(t.channel, i) if q.id not in guests]) + len(guests) <= TABLE_SEATS]
        t.table = fits[0] if fits else self.pick_table(t.channel, guests)
        for m in guests:
            self.people[m].table = t.table

    async def close_thread(self, t: ThreadState) -> None:
        if self.threads.pop(t.id, None) is None:
            return
        t.closing = True
        now = self.clock.now()
        said = [x for k, _, x in t.lines if k == "speech"]
        if t.kind == "chat" and len(said) >= realism.TIDY_MIN_LINES:
            self.realism.add_ending(realism.tidy_ending(said))
        for a in t.members:
            for b in t.members:
                if a < b:
                    self.cooldown[(a, b)] = now
        for m in list(t.members):
            self._release(t, m)
        async with Session() as s:
            row = await s.get(Thread, t.id)
            if row:
                row.ended_at, row.participants = now, list(t.ever)
                await s.commit()
        bus.publish(self.thread_event(t, ended=now))
        self.publish_presence()
        self.spawn(wrap_up(self, t))

    def _release(self, t: ThreadState, pid: str) -> None:
        if pid in t.members:
            t.members.remove(pid)
            if pid in t.span:
                t.span[pid][1] = len(t.lines)
        p = self.people[pid]
        if p.thread_id == t.id:
            p.thread_id, p.free_since = None, self.clock.now()

    async def leave_thread(self, t: ThreadState, p: PersonState, note: str) -> None:
        if p.id not in t.members:
            return
        self._release(t, p.id)
        await self.post(t.channel, note, kind="system", thread=t)
        if len([m for m in t.members if self.people[m].present]) < 2:
            t.closing = True
        self.publish_presence()

    async def join_thread(self, t: ThreadState, p: PersonState) -> None:
        t.members.append(p.id)
        t.ever[p.id] = None
        t.span[p.id] = [len(t.lines), None]
        if p.is_bartender:
            text = f"{p.short} drifts over and leans on the bar to listen in."
        else:
            p.thread_id, p.free_since = t.id, None
            if t.table is not None:
                room = len([q for q in self.table_occupants(t.channel, t.table) if q.id != p.id]) < TABLE_SEATS
                p.table = t.table if room else self.pick_table(t.channel, [p.id])
            text = f"{p.short} joins the conversation."
        await self.post(t.channel, text, kind="system", thread=t)
        self.publish_presence()

    # ---------------------------------------------------------------- conversation loop

    async def run_thread(self, t: ThreadState) -> None:
        try:
            await self.clock.sleep(self.rng.uniform(5, 25))
            while not t.closing and t.id in self.threads:
                live = [m for m in t.members if self.people[m].present]
                if t.kind == "order" and t.turns >= t.max_turns:
                    await self.finish_order(t)
                if t.kind == "order" and t.seated and not t.lingered and t.turns >= t.max_turns:
                    await self.maybe_linger(t)
                if len(live) < 2 or t.turns >= t.max_turns or t.failures >= 3:
                    break
                if t.kind == "chat" and not any(not self.people[m].is_bartender for m in live):
                    break  # only bartenders left; the bar chat is over
                speaker = self.pick_speaker(t)
                if speaker is None:
                    break
                began = self.clock.now()
                await self.take_turn(t, speaker)
                await self.quiet_step(t, speaker)
                await self.maybe_second_bartender(t)
                # Time spent waiting on the model already counts as part of the pause between lines.
                waited = (self.clock.now() - began).total_seconds()
                await self.clock.sleep(max(0.0, self.rng.uniform(45, 170) * (1.4 - 0.6 * speaker.talk) * human.pace(speaker) - waited))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("thread %s crashed", t.id)
        finally:
            patron = None
            if t.kind == "order":
                await self.finish_order(t)
            if t.kind == "order" and not t.seated:
                patron = next((self.people[m] for m in t.ever if not self.people[m].is_bartender), None)
            await self.close_thread(t)
            if patron and patron.present and patron.thread_id is None:
                if not await self.rejoin(patron):
                    await self.settle(patron)
            # Seated guests stay on their stool after ordering or chatting; the social step takes it from here.

    async def quiet_step(self, t: ThreadState, speaker: PersonState) -> None:
        """What fills the gaps between lines: someone fidgets, or the talk stalls."""
        if t.kind != "chat" or t.closing or t.id not in self.threads:
            return
        now = self.clock.now()
        others = [self.people[m] for m in t.members if m != speaker.id and self.people[m].present and not self.people[m].is_bartender]
        if others:
            q = self.rng.choice(others)
            live = environment.live(environment.game_on(now), now) and q.location == "bar"
            if text := beats.chat_beat(self.rng, q, live):
                await self.beat(q, text, t)
        said = [x for k, _, x in t.lines if k == "speech"]
        short = bool(said) and len(said[-1]) < 25
        flagging = t.turns - t.last_topic_turn >= 6
        if t.turns < 2 or t.turns >= t.max_turns or self.rng.random() >= beats.lull_chance(short, flagging, t.lulls):
            t.lulls = 0
            return
        t.lulls += 1
        t.lull = True
        if t.lulls >= 2:
            t.max_turns = min(t.max_turns, t.turns + 2)  # two stalls in a row and the chat is done
        await self.post(t.channel, self.rng.choice(beats.LULL_TEXT), None, "action", t)
        await self.clock.sleep(self.rng.uniform(60, 150))

    # ---------------------------------------------------------------- the register

    async def rejoin(self, p: PersonState) -> bool:
        """After a trip to the bar, go back to the group you left if it is still going."""
        tid, p.return_to = p.return_to, None
        t = self.threads.get(tid) if tid else None
        if (not t or t.closing or t.kind != "chat" or len(t.members) >= self.max_group(t) or t.turns >= t.max_turns - 1
                or not any(self.people[m].present and not self.people[m].is_bartender for m in t.members)):
            return False
        if t.channel == "bar" and not await self.move(p, "bar"):
            return False
        p.location = t.channel
        await self.join_thread(t, p)
        return True

    # ---------------------------------------------------------------- taste and money

    def taste_of(self, p: PersonState) -> taste.TasteRec:
        """Someone's tastes, made from their persona the first time they are needed."""
        if p.id not in self.tastes:
            self.tastes[p.id] = taste.seed(p.persona, random.Random(f"taste:{p.id}"))
        return self.tastes[p.id]

    def log_taste(self, kind: str, p: PersonState, **extra) -> None:
        self.taste_log.append({"kind": kind, "pid": p.id, "day": self.clock.now().strftime("%Y-%m-%d"), **extra})
        del self.taste_log[:-taste.LOG_KEEP]

    def broke(self, p: PersonState) -> bool:
        """Another round would take them past what they meant to spend tonight."""
        return p.drinks > 0 and p.cap > 0 and not taste.can_afford(p.spent, p.cap, sales.PRICE_CENTS)

    def hold_off(self, p: PersonState) -> None:
        """They stop here: no more rounds, and a small action to show it."""
        p.drink_goal, p.next_drink_at = p.drinks, None
        self.log_taste("skip", p, spent=p.spent, cap=p.cap)
        self.spawn(self.beat(p, f"{p.short} checks {beats.pos(p)} card, thinks about it, and decides to hold off on another."))

    def usual_for(self, p: PersonState) -> str:
        """The drink they are most likely to be on: what they had last, otherwise their favourite."""
        return p.drink if p.drink and p.drink != menu.WATER and p.drinks > 0 else ""

    def pick_drink(self, p: PersonState, rng: random.Random | None = None) -> str:
        """A drink for someone who is not ordering for themselves (a friend treated to a round, a party's first drink)."""
        rng = rng or self.rng
        now = self.clock.now()
        tight = p.spent >= 0.6 * p.cap or taste.budget(p.persona) == "tight"
        specials = sales.specials(now) if sales.happy_hour(now) else []
        i = taste.intend(self.taste_of(p), p.persona, self.usual_for(p), rng, now.strftime("%Y-%m-%d"), specials=specials, tight=tight)
        return i.drink or taste.recommend({}, self.taste_of(p), rng, now.strftime("%Y-%m-%d"), specials)

    def schedule_next_drink(self, p: PersonState, now: datetime) -> None:
        if p.drinks >= p.drink_goal:
            p.next_drink_at = None
            return
        left = ((p.leave_at or now + timedelta(minutes=60)) - now).total_seconds() / 60
        wait = max(12.0, left / (p.drink_goal - p.drinks + 1) * self.rng.uniform(0.7, 1.3))
        p.next_drink_at = now + timedelta(minutes=wait * (drunk.SLOW_WAIT if drunk.service(p) != "pour" else 1.0))

    def wants_round(self, p: PersonState, now: datetime) -> bool:
        if not p.present or p.next_drink_at is None or now < p.next_drink_at or p.drinks >= p.drink_goal or p.wants_leave:
            return False
        if self.broke(p):
            self.hold_off(p)
            return False
        if p.leave_at and now >= p.leave_at - timedelta(minutes=10):
            return False
        return now < open_close(now)[1] - timedelta(minutes=10)

    def _finalize(self, pay: Payment, p: PersonState | None, now: datetime) -> None:
        """Pick the tip and close the card transaction."""
        pct = sales.pick_tip(p.persona.get("tipper", "standard") if p else "standard", self.rng)
        pay.tip_pct, pay.tip = pct, sales.tip_cents(pay.subtotal, pct)
        pay.total, pay.status = pay.subtotal + pay.tip, "closed"
        pay.closed_at = min(now, sales.day_end(pay.opened_at))

    async def finish_order(self, t: ThreadState) -> None:
        """Ring up the order once, when the order conversation is done (or the guest walks out mid-order)."""
        if t.charged:
            return
        t.charged = True
        guest = next((self.people[m] for m in t.ever if not self.people[m].is_bartender), None)
        bt = next((m for m in t.ever if self.people[m].is_bartender), None)
        if guest is None:
            return
        now = self.clock.now()
        self.settle_suggestion(t, guest)
        if t.suggest and t.intent is not None and t.intent.kind == "rec":
            self.log_taste("rec_taken" if t.order_drink == t.suggest else "rec_declined", guest, drink=t.suggest)
        if t.order_drink and (t.ordered or not t.again):
            drink = t.order_drink
            if drink != menu.WATER and drunk.service(guest) == "cut":
                await self.cut_off(guest, bt, t)
                drink = menu.WATER
            await self.charge(guest, drink, bt, t)
            if t.treat:
                await self.round_for(guest, t, bt)
            for pid in ([] if t.treat else t.party):  # the rest of the party's first round rides on the leader's order
                q = self.people[pid]
                if q.present and q.drinks == 0:
                    await self.charge(q, self.pick_drink(q), bt, t)
        elif t.again:
            # Passed on another: they want fewer drinks, and the bartender will not ask again right away.
            guest.drink_goal = max(guest.drinks, guest.drink_goal - 1)
            guest.next_drink_at = now + timedelta(minutes=30) if guest.drinks < guest.drink_goal else None
        else:
            guest.next_drink_at = now + timedelta(minutes=5)  # never settled on a drink; try again shortly
        for pid in ([] if t.treat else t.party):  # nobody in a party is left waiting on an order that never paid
            q = self.people[pid]
            if q.present and q.drinks == 0 and q.next_drink_at is None:
                q.next_drink_at = now + timedelta(minutes=5)

    async def round_for(self, buyer: PersonState, t: ThreadState, bt: str | None) -> None:
        """The buyer pays for a drink for each friend who is still here and still being poured."""
        now = self.clock.now()
        mine = self.taste_of(buyer)
        treated: list[PersonState] = []
        for pid in t.party:
            q = self.people[pid]
            if not q.present or drunk.service(q) != "pour":
                continue
            await self.charge(q, self.pick_drink(q), bt, t, buyer=buyer)
            treated.append(q)
            theirs = self.taste_of(q)
            mine.owes[q.id] = max(-taste.OWES_CAP, mine.owes.get(q.id, 0) - 1)
            theirs.owes[buyer.id] = min(taste.OWES_CAP, theirs.owes.get(buyer.id, 0) + 1)
            await self.social.add_memory(q.id, now, f"{buyer.short} bought me a drink.", [buyer.id], 4)
            await self.social.apply_delta(q.id, buyer.id, 1, 3, "")
        if treated:
            await self.post(t.channel, f"🍻 {buyer.short} buys a round for {_names([q.short for q in treated])}.", kind="system", thread=t)
            await self.social.add_memory(buyer.id, now, f"Bought a round for {_names([q.short for q in treated])}.", [q.id for q in treated], 4)
            self.log_taste("round", buyer, to=[q.id for q in treated])
            self.publish_relationships([buyer.id, *[q.id for q in treated]])

    def treat_friends(self, p: PersonState, now: datetime) -> list[PersonState]:
        """Friends here who would get a drink on someone's tab, if p feels like buying and can afford it; else none."""
        friends = []
        for q in self.patrons():
            if q.id == p.id or not q.present or q.location != p.location or q.waiting or q.thread_id is not None or q.wants_leave:
                continue
            rel = self.social.rel(p.id, q.id)
            if rel.familiarity >= 40 and rel.affinity >= 0 and not bonds.avoids(rel, now) and drunk.service(q) == "pour":
                friends.append(q)
        self.rng.shuffle(friends)
        friends = friends[:taste.MAX_FRIENDS]
        while friends and p.cap > 0 and not taste.can_afford(p.spent, p.cap, sales.PRICE_CENTS * (len(friends) + 1)):
            friends.pop()
        if not friends:
            return []
        mine = self.taste_of(p)
        owed = sum(max(mine.owes.get(q.id, 0), 0) for q in friends)
        flush = any(e.kind == "windfall" and life.freshness(e, now) > 0 for e in self.life.get(p.id, []))
        return friends if taste.buys_round(p.persona, p.mood, p.buzz, owed, flush, self.rng, len(friends)) else []

    async def cut_off(self, p: PersonState, bartender_id: str | None, t: ThreadState) -> None:
        """The bartender stops serving them: no more rounds, water instead, and they head home before long."""
        now = self.clock.now()
        p.cut_off, p.drink_goal, p.next_drink_at = True, p.drinks, None
        p.leave_at = min(p.leave_at or now + timedelta(hours=1), now + timedelta(minutes=self.rng.uniform(*drunk.CUT_LEAVE_MIN)))
        human.nudge_mood(p, -0.15)
        who = self.people[bartender_id].short if bartender_id else "The bartender"
        await self.post(t.channel, f"🚫 {who} cuts {p.short} off.", kind="system", thread=t)

    async def serve_water(self, p: PersonState, t: ThreadState) -> None:
        """A free glass of water: no sale, but it counts as one of their planned rounds and helps them sober up."""
        now = self.clock.now()
        p.drink, p.on_water_until = menu.WATER, now + timedelta(minutes=self.rng.uniform(*drunk.WATER_MIN))
        if p.drinks:
            p.drink_goal = max(p.drinks, p.drink_goal - 1)
        self.schedule_next_drink(p, now)
        await self.post(t.channel, f"{p.short} gets a water.", kind="system", thread=t)
        self.publish_presence()

    async def charge(self, p: PersonState, drink: str, bartender_id: str | None, t: ThreadState,
                     buyer: PersonState | None = None) -> None:
        """Ring up a drink for p. When `buyer` is given they pay for it (a round) and p only drinks it."""
        if drink == menu.WATER:
            await self.serve_water(p, t)
            return
        now = self.clock.now()
        payer = buyer or p
        list_price, cost, happy = sales.price(drink, now)
        brand, last4 = sales.card_for(payer.id)
        async with Session() as s:
            pay = await s.get(Payment, payer.tab_id) if payer.tab_id else None
            if pay is None:
                pay = Payment(person_id=payer.id, bartender_id=bartender_id, kind="tab" if payer.pay_mode == "tab" else "per_drink",
                              status="open", opened_at=now, card_brand=brand, card_last4=last4)
                s.add(pay)
                await s.flush()
                if pay.kind == "tab":
                    payer.tab_id = pay.id
            s.add(SaleItem(payment_id=pay.id, person_id=p.id, bartender_id=bartender_id, thread_id=t.id, drink=drink,
                           list_price=list_price, price=cost, happy_hour=happy, sim_ts=now, buyer_id=buyer.id if buyer else None))
            pay.subtotal += cost
            pay.bartender_id = bartender_id
            if pay.kind == "per_drink":
                self._finalize(pay, payer, now)
            else:
                pay.total = pay.subtotal
            await s.commit()
        payer.spent += cost
        p.drinks += 1
        p.buzz = human.add_drink(p.buzz, p.persona, drunk.strength(menu.abv(drink)))
        p.peak_buzz = max(p.peak_buzz, p.buzz)
        p.drink = drink
        if p.drinks >= p.drink_goal and drunk.tier(p.buzz) in ("sober", "tipsy") and self.rng.random() < 0.1:
            p.drink_goal += 1  # one more for the road
        self.schedule_next_drink(p, now)
        bus.publish({"type": "sale", "payment_id": pay.id, "person_id": payer.id, "status": pay.status})
        extra = " (happy hour)" if happy else ""
        whose = f"{p.short}'s " if buyer else ""
        if pay.kind == "per_drink":
            tip = f", {pay.tip_pct}% tip" if pay.tip_pct else ", no tip"
            text = f"{payer.short} pays by card: {whose}{drink} {sales.money(cost)}{extra}{tip}."
        else:
            text = f"{payer.short} puts {whose}{drink} on the tab ({sales.money(cost)}{extra}; {sales.money(pay.subtotal)} so far)."
        await self.post(t.channel, text, kind="system", thread=t)
        await self.taste_after(p, drink, t, bartender_id, buyer)
        self.publish_presence()

    async def taste_after(self, p: PersonState, drink: str, t: ThreadState, bartender_id: str | None, buyer: PersonState | None) -> None:
        """How the drink landed: their tastes move, a rut can start to wear, and a suggestion that worked is remembered."""
        now = self.clock.now()
        day = now.strftime("%Y-%m-%d")
        rec = self.taste_of(p)
        if drink not in rec.tried:
            self.log_taste("new", p, drink=drink)
        v = taste.verdict(rec, p.persona, drink, self.rng)
        taste.after_drink(rec, drink, v)
        if p.drinks == 1 and taste.first_of_visit(rec, drink, day, self.rng):
            self.log_taste("tired", p, drink=drink)
        if bartender_id and buyer is None and t.suggest and drink == t.suggest:
            b = self.people[bartender_id]
            text = {"loved": f"{b.short} suggested the {drink} and it was exactly right.",
                    "fine": f"{b.short} suggested the {drink}; it was fine.",
                    "meh": f"{b.short} suggested the {drink}; it wasn't for you."}[v]
            await self.social.add_memory(p.id, now, text, [b.id], 4)
            if v == "loved":
                await self.social.apply_delta(p.id, b.id, 1, 2, "")
                self.log_taste("rec_loved", p, drink=drink)

    async def close_tab(self, p: PersonState) -> None:
        if p.tab_id is None:
            return
        tab_id, p.tab_id = p.tab_id, None
        now = self.clock.now()
        async with Session() as s:
            pay = await s.get(Payment, tab_id)
            if pay is None or pay.status != "open":
                return
            n = await s.scalar(select(func.count()).select_from(SaleItem).where(SaleItem.payment_id == tab_id))
            self._finalize(pay, p, now)
            await s.commit()
        bus.publish({"type": "sale", "payment_id": tab_id, "person_id": p.id, "status": "closed"})
        tip = f"{pay.tip_pct}% tip" if pay.tip_pct else "no tip"
        await self.post("bar", f"💳 {p.short} closes out the tab: {n} drink{'s' if n != 1 else ''}, "
                        f"{sales.money(pay.subtotal)} + {tip} = {sales.money(pay.total)}.", kind="system")

    # ---------------------------------------------------------------- bar seating

    def stools_taken(self) -> set[int]:
        return {p.stool for p in self.patrons() if p.present and p.stool is not None}

    def free_stool(self, near: list[int] | None = None) -> int | None:
        free = [i for i in range(BAR_STOOLS) if i not in self.stools_taken()]
        if not free:
            return None
        if near:
            return min(free, key=lambda i: (min(abs(i - n) for n in near), self.rng.random()))
        return self.rng.choice(free)

    def table_occupants(self, area: str, table: int) -> list[PersonState]:
        return [q for q in self.patrons() if q.present and q.location == area and q.table == table]

    def held_tables(self, area: str, mine: set | frozenset = frozenset()) -> set[int]:
        """Tables a party is holding in this area, other than the parties in `mine`."""
        return {i for pt in self.parties.values() if pt.area == area and pt.id not in mine for i in pt.tables}

    def pick_table(self, area: str, group: list[str] | tuple = ()) -> int | None:
        """The emptiest table in the area that still has room for the group, or None (standing)."""
        n = TABLES.get(area, 0)
        need = max(1, len(group))
        held = self.held_tables(area, {self.people[g].party for g in group if g in self.people} - {None})
        counts = [len([q for q in self.table_occupants(area, i) if q.id not in group]) for i in range(n)]
        fits = [i for i in range(n) if counts[i] + need <= TABLE_SEATS and i not in held]
        if not fits:
            return None
        return min(fits, key=lambda i: (counts[i], self.rng.random()))

    def friends_on_stools(self, p: PersonState, min_fam: int = 35) -> list[int]:
        return [q.stool for q in self.patrons()
                if q.present and q.id != p.id and q.stool is not None and self.social.rel(p.id, q.id).familiarity >= min_fam]

    def bartenders_on(self) -> list[PersonState]:
        return [b for b in self.people.values() if b.is_bartender and b.present]

    def bartender_thread(self, b: PersonState) -> ThreadState | None:
        """The one conversation a bartender is in, whether taking an order or talking: they do one thing at a time."""
        return next((t for t in self.threads.values() if b.id in t.members and not t.closing), None)

    def free_bartenders(self) -> list[PersonState]:
        return [b for b in self.bartenders_on() if self.bartender_thread(b) is None]

    def pick_bartender(self, p: PersonState) -> PersonState | None:
        """A bartender with nothing on, favouring the ones the guest knows."""
        bts = self.free_bartenders()
        if not bts:
            return None
        return self.rng.choices(bts, [1.0 + self.social.rel(p.id, b.id).familiarity / 40 for b in bts])[0]

    def area_room(self) -> tuple[dict[str, int], dict[str, int]]:
        """Free seats and total seats in each area."""
        cap = {"bar": BAR_STOOLS, **{a: n * TABLE_SEATS for a, n in TABLES.items()}}
        free = {"bar": BAR_STOOLS - len(self.stools_taken())}
        for a in TABLES:
            free[a] = cap[a] - len([q for q in self.patrons() if q.present and q.location == a and q.table is not None])
            # A party member up at the bar still has a seat waiting.
            free[a] -= sum(1 for pt in self.parties.values() if pt.area == a for m in pt.members
                           if self.people[m].present and not (self.people[m].location == a and self.people[m].table is not None))
            free[a] = max(0, free[a])
        return free, cap

    def choose_area(self, p: PersonState, no_bar: bool = False) -> str:
        """Where this guest plans to spend the visit: see seating.area_weights."""
        now = self.clock.now()
        party = 1 + sum(1 for q in self.patrons()
                        if q.id != p.id and self.social.rel(p.id, q.id).familiarity >= 55
                        and (q.pending_arrival is not None
                             or (q.present and q.arrived_at and now - q.arrived_at <= timedelta(minutes=20))))
        lean = p.persona.get("bar_seat")
        lean = 2 * lean if lean is not None else 0.75 + 0.5 * p.talk
        g = environment.game_on(now)
        fan = p.reason == "game" or bool(g and environment.fan_of(g.team, p.persona))
        knows = any(self.social.rel(p.id, b.id).familiarity >= 40 for b in self.bartenders_on())
        free, cap = self.area_room()
        if no_bar:
            free["bar"] = 0
        return seating.pick_area(self.rng, seating.area_weights(min(party, 3), lean, knows, fan, now, free, cap))

    async def sit(self, p: PersonState, text: str, near: list[int] | None = None) -> bool:
        stool = self.free_stool(near)
        if stool is None or not p.present:
            return False
        p.stool, p.location, p.free_since, p.table = stool, "bar", self.clock.now(), None
        await self.post("bar", text.format(p.short), kind="system")
        self.publish_presence()
        return True

    def linger_chance(self, t: ThreadState) -> float:
        guest = next((self.people[m] for m in t.members if not self.people[m].is_bartender), None)
        bts = [self.people[m] for m in t.members if self.people[m].is_bartender]
        if not guest or not bts:
            return 0.0
        fam = max(self.social.rel(guest.id, b.id).familiarity for b in bts)
        busy = sum(1 for p in self.patrons() if p.present and p.location == "bar") > 8
        return max(0.0, min(0.9, 0.35 + 0.3 * guest.talk + fam / 200 - (0.2 if busy else 0)))

    async def maybe_linger(self, t: ThreadState) -> None:
        """A seated guest who has ordered may stay and talk across the bar; same thread, so it stays one card."""
        t.lingered = True
        if self.rng.random() < self.linger_chance(t):
            t.kind, t.again = "chat", False
            t.max_turns = t.turns + self.rng.randint(4, 9)
            t.last_topic_turn = t.turns
            bus.publish(self.thread_event(t))

    async def maybe_second_bartender(self, t: ThreadState) -> None:
        if t.kind != "chat" or t.channel != "bar" or t.closing or len(t.members) >= MAX_GROUP_BAR:
            return
        has_bt = any(self.people[m].is_bartender for m in t.members)
        others = [b for b in self.free_bartenders() if b.id not in t.members]
        quiet = sum(1 for p in self.patrons() if p.present and p.location == "bar") <= 3
        if others and self.rng.random() < (0.14 if quiet else 0.07) * (1 if has_bt else 0.5):
            await self.join_thread(t, self.rng.choice(others))

    def stool_neighbors(self, p: PersonState, others: list[str]) -> bool:
        """True if p sits within two stools of any of `others`."""
        if p.stool is None:
            return False
        return any(self.people[o].stool is not None and abs(self.people[o].stool - p.stool) <= 2 for o in others if o in self.people)

    def max_group(self, t: ThreadState) -> int:
        return MAX_GROUP_BAR if t.channel == "bar" else MAX_GROUP

    def pick_speaker(self, t: ThreadState) -> PersonState | None:
        members = [self.people[m] for m in t.members if self.people[m].present]
        if not members:
            return None
        if t.kind == "order":
            # The guest orders, the bartender answers, the guest wraps up.
            guests, bts = [p for p in members if not p.is_bartender], [p for p in members if p.is_bartender]
            order = bts + guests if t.ask else guests + bts
            return order[t.turns % len(order)] if len(order) > 1 else None
        recent = [s for k, s, _ in t.lines if k == "speech"][-3:]
        weights = []
        if t.interrupt and recent and recent[-1] == t.interrupt[0] and t.interrupt[1] in t.members:
            cutter = self.people[t.interrupt[1]]
            if cutter.present:
                return cutter  # they talk over whoever just spoke
        for p in members:
            w = (0.2 + p.talk) * human.speaker_weight(p) * dynamics.dominance(p)
            if p.id == t.outsider:
                w *= 0.5
            if recent and p.id == recent[-1]:
                w *= dynamics.floor_keep(p)
            elif p.id in recent:
                w *= 0.6
            if p.wants_leave:
                w *= 2.0
            weights.append(w)
        return self.rng.choices(members, weights)[0]

    def halt(self, text: str) -> None:
        self.clock.pause()
        self.banner = text
        bus.publish({"type": "banner", "text": text})

    def cooling(self, a: str, b: str, now: datetime) -> bool:
        """True if these two just finished talking and should not immediately restart."""
        t = self.cooldown.get((a, b) if a < b else (b, a))
        return t is not None and now - t < timedelta(minutes=25)

    def check_budget(self) -> bool:
        if settings.llm_mode == "live" and usage.over_budget():
            if not self.budget_paused:
                self.budget_paused = True
                self.halt(f"Daily budget of ${usage.budget:.2f} reached. Simulation paused.")
                log.warning("budget reached; pausing")
            return True
        return False

    async def take_turn(self, t: ThreadState, p: PersonState) -> None:
        if self.check_budget():
            return
        if p.wants_leave and p.id in t.members:
            t.nudge_leave.add(p.id)
        wind_down = t.kind == "chat" and t.turns >= t.max_turns - 2
        if t.kind == "chat" and not p.is_bartender and p.id not in t.excuse:
            if why := human.excuse_due(p, self.clock.now(), t.turns, self.rng):
                t.excuse[p.id] = why
                if p.need == "call" and why.startswith("You need") and self.rng.random() < 0.5:
                    t.cut.add(p.id)  # the call comes in mid-sentence
            elif p.id not in t.cut and beats.cut_due(self.rng, t.turns):
                t.cut.add(p.id)
        self.roll_dynamics(t, p)
        req = agent_mod.build_turn(self, t, p, wind_down)
        bus.publish({"type": "typing", "thread_id": t.id, "person_id": p.id, "on": True})
        began = time.monotonic()
        try:
            utt = await self.llm.speak(req)
        finally:
            took = time.monotonic() - began
            self.latency = took if self.latency == 0 else 0.8 * self.latency + 0.2 * took
            bus.publish({"type": "typing", "thread_id": t.id, "person_id": p.id, "on": False})
        if utt is None:
            t.failures += 1
            return
        utt = agent_mod.sanitize(utt, p)
        if t.kind != "chat":
            utt.beat = ""
        if not utt.say and not utt.beat:
            t.failures += 1
            return
        # The world moved while we waited on the model: make sure this turn still makes sense.
        member_ok = p.id in t.members
        if t.closing or t.id not in self.threads or not p.present or not member_ok:
            return
        t.failures = 0
        t.turns += 1
        t.ever[p.id] = None
        p.last_spoke = self.clock.now()
        if utt.beat:
            await self.beat(p, f"{p.short} {utt.beat}.", t)
        if utt.say:
            await self.post(t.channel, utt.say, p.id, "speech", t, thought=utt.thought)
        if not p.is_bartender:
            if utt.say:
                human.spoke(p)
            human.blend_mood(p, utt.mood)
            p.thought = utt.thought or p.thought
        if t.kind == "order":
            self.record_drink(t, p, utt)
        await self.escalate(t, p)
        if utt.lookup:
            self.spawn(self.lookup_task(p, utt.lookup, t))
        await self.apply_action(t, p, utt, forced_leave=p.id in t.nudge_leave)
        await self.after_turn(t, p, utt)

    # ---------------------------------------------------------------- group dynamics

    def log_group(self, kind: str, pids: list[str], **extra) -> None:
        self.group_log.append({"kind": kind, "pids": pids, "day": self.clock.now().strftime("%Y-%m-%d"), **extra})
        del self.group_log[:-dynamics.LOG_KEEP]

    def table_of(self, t: ThreadState) -> list[PersonState]:
        return [self.people[m] for m in t.members if self.people[m].present and not self.people[m].is_bartender]

    def roll_dynamics(self, t: ThreadState, p: PersonState) -> None:
        """Before a guest's turn in a chat: who is on the outside, and whether this turn they get talked over, joke or change the subject."""
        if t.kind != "chat" or p.is_bartender:
            return
        rng = random.Random(t.id * 7919 + t.turns)
        table = self.table_of(t)
        if t.interrupt and p.id not in t.interrupt:
            t.interrupt = None  # the moment passed
        t.joking = ""
        old, t.outsider = t.outsider, dynamics.outsider([g.id for g in table], self.social.rel) or ""
        if t.outsider and t.outsider != old:
            self.log_group("outsider", [t.outsider])
        if t.outsider == p.id and p.id not in t.excuse and dynamics.outsider_leaves(rng, t.turns):
            t.excuse[p.id] = dynamics.OUTSIDER_EXCUSE_TEXT
        if not t.lines or t.turns < 2 or t.interrupt or p.id in t.cut or p.id in t.excuse or p.wants_leave:
            return
        others = [g for g in table if g.id != p.id]
        if cutter := dynamics.interrupter(rng, p, others):
            t.interrupt = (p.id, cutter.id)
            return
        recent = [x for k, _, x in t.lines if k == "speech"][-3:]
        touchy = [q.short for q in self.patrons() if q.present and q.id not in t.members
                  and self.social.rel(p.id, q.id).bond in ("falling_out", "ex")]
        gossiped = any(p.short.lower() in x.lower() and realism.topic_of(x) == "gossip" for x in recent)
        if (go := dynamics.steer_due(rng, p, recent, touchy, gossiped, t.turns - t.last_topic_turn)):
            t.steer[p.id] = go[1]
            t.last_topic_turn = t.turns
            self.log_group("steer", [p.id], why=go[0])
        elif dynamics.joke_due(rng, p):
            t.joking = p.id

    async def after_turn(self, t: ThreadState, p: PersonState, utt) -> None:
        """After a guest's line in a chat: who talked over whom, how a joke went down, the table's mood, and pairs splitting off."""
        if t.kind != "chat" or p.is_bartender or t.closing or t.id not in self.threads:
            return
        rng = random.Random(t.id * 7919 + t.turns + 1)
        if t.interrupt and p.id == t.interrupt[0]:
            if utt.say and t.interrupt[1] in t.members:
                self.log_group("interrupt", list(t.interrupt))
            else:
                t.interrupt = None
        elif t.interrupt and p.id == t.interrupt[1]:
            t.interrupt = None
        table = self.table_of(t)
        if t.joking == p.id:
            t.joking = ""
            if utt.say:
                await self.land_joke(t, p, [g for g in table if g.id != p.id], rng)
        t.vibe = dynamics.vibe(table)
        for g in table:
            dynamics.catch(g, t.vibe)
        if p.id == t.outsider:
            p.battery = max(0.0, p.battery - 0.02)  # sitting on the outside is tiring
        if p.id in t.members and not t.on_event and t.turns >= dynamics.SPLINTER_MIN_TURNS:
            if pair := dynamics.splinter(rng, table, self.social.rel):
                await self.split_thread(t, pair)

    async def land_joke(self, t: ThreadState, teller: PersonState, listeners: list[PersonState], rng: random.Random) -> None:
        """Each listener takes a joke their own way; one action line says how it went round the table."""
        if not listeners:
            return
        results = {g.id: dynamics.reception(rng, teller, g, self.social.rel(g.id, teller.id)) for g in listeners}
        t.joke = {"teller": teller.id, "by": dict(results)}
        names = {g.id: g.short for g in listeners}
        await self.post(t.channel, dynamics.reaction(teller.short, results, names), None, "action", t)
        v = dynamics.verdict(results)
        human.nudge_mood(teller, dynamics.teller_mood(v))
        for g in listeners:
            human.nudge_mood(g, dynamics.joke_mood(results[g.id]))
            if results[g.id] == "stung":
                await self.social.apply_delta(teller.id, g.id, 0, -3, "a joke that stung")
        self.log_group("joke", [teller.id, *results], result=v)

    async def split_thread(self, t: ThreadState, pair: tuple[str, str]) -> None:
        """Two people at a big table drift into a conversation of their own, at the same table."""
        a, b = (self.people[x] for x in pair)
        for x in (a, b):
            self._release(t, x.id)
        t.max_turns += 3
        await self.post(t.channel, f"{a.short} and {b.short} drift into a conversation of their own.", kind="system", thread=t)
        side = await self.open_thread(t.channel, "chat", [a.id, b.id], self.rng.randint(6, 12))
        side.split_from = t.id
        self.log_group("split", [a.id, b.id], size=len(t.members))

    # ---------------------------------------------------------------- God Mode escalation

    async def escalate(self, t: ThreadState, p: PersonState) -> None:
        """Opposing sides in a chat about a divisive event wind each other up, until someone steps in or storms off."""
        g = self.god
        if not g or not t.on_event or t.kind != "chat" or p.is_bartender or t.closing:
            return
        now = self.clock.now()
        mine = godmode.stance(g, p.id, p.persona)
        rivals = [self.people[m] for m in t.members if m != p.id and not self.people[m].is_bartender
                  and godmode.opposed(mine, godmode.stance(g, m, self.people[m].persona))]
        if not rivals:
            t.tension = max(0.0, t.tension - 0.1)
            return
        t.tension += 0.12 * g["divisiveness"] * self.rng.uniform(0.5, 1.5) * godmode.fade(g, now) * human.escalation(p.persona)
        human.nudge_mood(p, -0.04)
        if g["divisiveness"] < 3 or t.tension < 2:
            return
        bts = self.bartenders_on()
        if not t.stepped_in and bts:
            t.stepped_in, t.tension = True, 1.0
            b = self.rng.choice(bts)
            how = "leans in and" if t.channel == "bar" else "comes over from the bar and"
            await self.post(t.channel, f"{b.short} {how} asks everyone to keep it friendly.", kind="system", thread=t)
            return
        who = self.rng.choices([p, *rivals], [1.0] + [1.2 - r.talk for r in rivals])[0]
        others = [m for m in t.members if m != who.id and not self.people[m].is_bartender]
        t.tension = 0.5
        if g["divisiveness"] >= 4 and bts and self.rng.random() < 0.2:
            await self.leave_thread(t, who, f"{self.rng.choice(bts).short} tells {who.short} it's time to cool off outside.")
            await self.depart(who)
        else:
            await self.leave_thread(t, who, f"{who.short} shakes their head and walks off.")
            await self.move(who, self.rng.choice([x for x in LOCATIONS if x != t.channel]))
        human.nudge_mood(who, -0.2)
        for o in others:
            human.nudge_mood(self.people[o], -0.1)
            await self.social.apply_delta(who.id, o, 0, -6, f"argued about: {g['text'][:70]}")
        self.publish_relationships([who.id, *others])

    def record_drink(self, t: ThreadState, p: PersonState, utt) -> None:
        """Remember what the guest is drinking: only names on the menu count, and the guest's own order wins."""
        # On a repeat round a name in the chatter ("not another Fallforge") is not an order; only the drink field is.
        name = menu.match(utt.drink) or (None if t.again else menu.match(utt.say))
        if not name:
            return
        guest = p if not p.is_bartender else next(
            (self.people[m] for m in t.members if not self.people[m].is_bartender), None)
        if guest is None or (p.is_bartender and (t.ordered or (t.again and not t.suggest))):
            return
        guest.drink, t.ordered, t.order_drink = name, t.ordered or not p.is_bartender, name
        self.publish_presence()

    async def excuse(self, t: ThreadState, p: PersonState, why: str, cut: bool = False) -> None:
        """Bow out of a conversation but stay in the taproom, for a few minutes or a good while."""
        need = p.need if why.startswith("You need") else ""
        if cut:  # a phone call, mid-sentence
            need, why = (p.need if p.need == "call" else ""), "You need to take a call."
            await self.leave_thread(t, p, f"📱 {p.short}'s phone buzzes and {p.short} breaks off mid-sentence to take it.")
        else:
            await self.leave_thread(t, p, f"{p.short} excuses themselves" + (f" to {human.NEEDS[need]}." if need else "."))
        p.free_since = self.clock.now() + human.away_for(why, self.rng)
        if need:
            p.need, p.need_at = "", None

    async def apply_action(self, t: ThreadState, p: PersonState, utt, forced_leave: bool) -> None:
        if p.is_bartender:
            return
        if utt.action == "leave" or forced_leave:
            await self.leave_thread(t, p, f"{p.short} heads out.")
            await self.depart(p)
        elif (utt.action == "excuse" or p.id in t.excuse or p.id in t.cut) and t.kind == "chat":
            cut = p.id in t.cut
            t.cut.discard(p.id)
            await self.excuse(t, p, t.excuse.pop(p.id, ""), cut)
        elif utt.action == "move" and utt.target != t.channel:
            if utt.target == "bar" and not p.seated and self.free_stool() is None:
                return  # no stool free; they stay where they are
            await self.leave_thread(t, p, f"{p.short} wanders off to the {utt.target}.")
            await self.move(p, utt.target)
        elif utt.action == "introduce":
            qid = self.resolve(utt.target)
            q = self.people.get(qid) if qid else None
            if (q and q.present and not q.is_bartender and q.id not in t.members
                    and len(t.members) < self.max_group(t) and q.location == t.channel):
                if q.thread_id and q.thread_id in self.threads:
                    other = self.threads[q.thread_id]
                    await self.leave_thread(other, q, f"{q.short} gets waved over to another conversation.")
                await self.join_thread(t, q)

    # ---------------------------------------------------------------- lookups & news

    async def lookup_task(self, p: PersonState, query: str, t: ThreadState) -> None:
        now = self.clock.now()
        self.lookups = [x for x in self.lookups if now - x < timedelta(hours=1)]
        if not settings.web_search_enabled or len(self.lookups) >= settings.max_lookups_per_sim_hour or self.check_budget():
            return
        self.lookups.append(now)
        await self.beat(p, f"{p.short} pulls out a phone to look something up.", t)
        fact = await self.llm.lookup(query, settings.brewery_city)
        if fact:
            p.pending_fact = fact[:400]

    async def recent_news(self, day: str) -> list[str]:
        async with Session() as s:
            rows = (await s.scalars(select(NewsItem).where(NewsItem.sim_day < day).order_by(NewsItem.id.desc()).limit(18))).all()
        return [r.text for r in rows]

    async def news_desk(self, day: str) -> None:
        if self.check_budget():
            return
        now = self.clock.now()
        recent: list[str] = []
        try:
            recent = await self.recent_news(day)
            lines = await self.llm.news(settings.brewery_city, now.strftime("%A, %B %-d, %Y"), recent)
        except Exception:
            log.exception("news fetch failed")
            lines = []
        lines = [x for x in lines if x not in recent] if lines else []
        if not lines:
            if now.hour < 20:  # try again in a sim hour, until the evening
                self.news_day, self.news_retry_at = "", now + timedelta(hours=1)
            return
        self.news, self.news_for = lines, day
        async with Session() as s:
            for ln in lines:
                s.add(NewsItem(sim_day=day, text=ln))
            await s.commit()
        await self.post("door", "📰 Around town today:\n" + "\n".join(f"• {x}" for x in lines), kind="system")

    # ---------------------------------------------------------------- people movement

    def check_in(self, p: PersonState) -> None:
        """Everything about a guest's visit that is settled at the door: stay, tab, drinks, mood. No routing."""
        now = self.clock.now()
        p.present, p.location, p.visited_day, p.wants_leave, p.pending_arrival = True, "ordering", now.strftime("%Y-%m-%d"), False, None
        mine = self.life.get(p.id, [])
        stay = p.persona.get("stay", 90) * self.rng.uniform(0.6, 1.5) * human.stay_scale(p.persona) * life.stay_mult(mine, now)
        close = open_close(now)[1]
        p.leave_at = min(now + timedelta(minutes=stay), close + timedelta(minutes=self.rng.uniform(0, 5)))
        p.free_since = None
        # Today's tab, drink count and card habit; one visit in ten they do the opposite of their usual.
        usual = p.persona.get("pay", "card")
        p.pay_mode = usual if self.rng.random() < 0.9 else ("card" if usual == "tab" else "tab")
        p.pay_mode = life.pay_override(mine, now) or p.pay_mode
        p.drinks, p.drink_goal, p.tab_id, p.return_to = 0, max(1, human.goal_shift(p.persona, sales.pick_goal(self.rng, stay), self.rng) + life.drink_delta(mine, now)), None, None
        p.next_drink_at = None
        prev = self.visits.get(p.id, {})
        p.gap_days = max(0, (now.date() - datetime.fromisoformat(prev["last"]).date()).days) if prev.get("last") else 0
        self.visits[p.id] = {"n": prev.get("n", 0) + 1, "last": now.isoformat()}
        p.arrived_at, p.reason, p.busy_until, p.thought = now, life.reason_override(mine, now) or human.pick_reason(p.persona, self.rng), None, ""
        p.mood = max(-1.0, min(1.0, human.opening_mood(p.persona, self.rng) + life.mood_shift(mine, now)))
        p.buzz, p.battery = 0.0, self.rng.uniform(0.8, 1.0)
        p.peak_buzz, p.cut_off, p.on_water_until, p.slops, p.overshare_pending, p.overshared_with = 0.0, False, None, [], False, set()
        p.spent, p.cap = 0, taste.visit_cap(p.persona, mine, now, life.freshness)
        h = self.hangovers.get(p.id)
        if h and h["written"]:  # the morning after: a rough start, and a lighter plan for tonight
            del self.hangovers[p.id]
            if (now - datetime.strptime(h["day"], "%Y-%m-%d")).days <= 3:
                human.nudge_mood(p, -0.15)
                p.drink_goal = drunk.hangover_goal(p.drink_goal)
        p.need, p.need_at = human.pick_need(self.rng, stay, now, now.weekday() >= 3, beats.smoker(p))
        p.first_visit = bool(p.persona.get("walkin")) and self.visits[p.id]["n"] == 1
        bus.publish({"type": "person", "person": self.person_view(p)})  # keeps visit counts current in open browsers

    async def arrive(self, p: PersonState) -> None:
        self.check_in(p)
        now = self.clock.now()
        close = open_close(now)[1]
        await self.post("door", f"🍺 {p.display} walks in.", kind="system")
        await self.wave_hello(p, now)
        # Friends tend to follow each other in.
        if now < close - timedelta(minutes=LAST_CALL_MIN + 20):
            good = any(e.cat == "good" for e in life.freshest(self.life.get(p.id, []), now))
            for q in self.patrons():
                if (not q.present and q.visited_day != p.visited_day and q.pending_arrival is None
                        and (self.social.rel(p.id, q.id).familiarity >= 55 or self.social.rel(p.id, q.id).bond == "couple")
                        and self.rng.random() < bonds.follow_chance(self.social.rel(p.id, q.id), p.reason, good)):
                    q.pending_arrival = now + timedelta(minutes=self.rng.uniform(5, 25))
        if self.bartenders_on():
            p.spot = self.choose_area(p)
            if p.spot == "bar":
                await self.sit(p, "{} pulls up a stool at the bar.", self.friends_on_stools(p) or None)
            await self.request_order(p)
        else:
            p.spot = self.choose_area(p)
            p.next_drink_at = now + timedelta(minutes=10)
            await self.settle(p)

    async def wave_hello(self, p: PersonState, now: datetime) -> None:
        """Friends already in the room notice someone come in and wave, now and then."""
        friends = [q for q in self.patrons() if q.present and q.id != p.id and not q.waiting
                   and self.social.rel(q.id, p.id).familiarity >= 35 and not bonds.avoids(self.social.rel(q.id, p.id), now)]
        self.rng.shuffle(friends)
        for q in friends[:2]:
            if self.rng.random() < 0.4:
                self.waved[(q.id, p.id)] = now
                await self.beat(q, beats.wave_text(self.rng, q, p))

    def wave_boost(self, a: str, b: str, now: datetime) -> float:
        """A wave from the door makes a chat between the two a little likelier for a while."""
        when = self.waved.get((a, b)) or self.waved.get((b, a))
        return 1.5 if when and now - when < timedelta(minutes=20) else 1.0

    def party_table(self, p: PersonState, area: str) -> int | None:
        """The table held for this guest's party in this area, if it still has a seat for them."""
        pt = self.parties.get(p.party) if p.party is not None else None
        t = pt.tables_of.get(p.id) if pt and pt.area == area else None
        if t is None or len([q for q in self.table_occupants(area, t) if q.id != p.id]) >= TABLE_SEATS:
            return None
        return t

    async def depart(self, p: PersonState) -> None:
        if not p.present:
            return
        if p.thread_id and p.thread_id in self.threads:
            t = self.threads[p.thread_id]
            if t.kind == "order":
                await self.finish_order(t)  # walking out mid-order still pays for the pour
            await self.leave_thread(t, p, f"{p.short} heads out.")
        await self.close_tab(p)
        self.queue = [w for w in self.queue if w.pid != p.id]
        now = self.clock.now()
        pt = self.parties.get(p.party) if p.party is not None else None
        ride = drunk.ride_home(p, [self.people[m] for m in pt.members] if pt else [], self.rng)
        if rec := drunk.record(p, now.strftime("%Y-%m-%d"), ride[0] if ride else ""):
            self.hangovers[p.id] = rec
            self.drunk_log = (self.drunk_log + [dict(rec)])[-drunk.LOG_KEEP:]
        p.waiting = False
        p.present, p.location, p.thread_id, p.wants_leave, p.free_since, p.stool, p.drink = False, None, None, False, None, None, ""
        p.table, p.spot = None, None
        p.return_to, p.next_drink_at = None, None
        self.beat_pool.pop(p.id, None)
        self.leave_party(p)
        await self.post("door", f"👋 {p.display} heads out.", kind="system")
        if ride:
            if ride[0] == "driver":
                driver = self.people[ride[1]]
                driver.leave_at = min(driver.leave_at or now + timedelta(minutes=5), now + timedelta(minutes=5))
                await self.post("door", f"🚗 {driver.short} drives {p.short} home.", kind="system")
            else:
                await self.post("door", f"📱 {p.short} calls a rideshare.", kind="system")
        self.publish_presence()

    def leave_party(self, p: PersonState) -> None:
        """Let go of a party's tables once its last member has left."""
        pid, p.party = p.party, None
        pt = self.parties.get(pid) if pid is not None else None
        if pt and not any(self.people[m].present and self.people[m].party == pid for m in pt.members):
            del self.parties[pid]

    async def move(self, p: PersonState, loc: str) -> bool:
        """Go somewhere else. The bar means a stool, so a full bar says no."""
        if loc not in LOCATIONS or not p.present:
            return False
        if loc == "bar":
            ok = p.seated or await self.sit(p, "{} grabs a stool at the bar.", self.friends_on_stools(p) or None)
            if ok:
                p.spot = "bar"
            return ok
        p.location, p.free_since, p.stool, p.spot = loc, self.clock.now(), None, loc
        p.table = self.party_table(p, loc) if p.party is not None else None
        if p.table is None:
            p.table = self.pick_table(loc, [p.id])
        await self.post(loc, f"{p.short} settles in at the {LOC_DESC[loc]}.", kind="system")
        self.publish_presence()
        return True

    async def settle(self, p: PersonState) -> None:
        """After ordering, a guest goes back to their spot for the visit; on a first drink they may follow a friend instead."""
        free, _ = self.area_room()
        loc = None
        friends = [q for q in self.patrons() if q.present and q.id != p.id and q.location in LOCATIONS
                   and free[q.location] > 0 and self.social.rel(p.id, q.id).familiarity >= 35]
        if p.drinks <= 1 and friends and p.party is None and self.rng.random() < 0.5:
            weights = [self.social.rel(p.id, q.id).familiarity for q in friends]
            loc = self.rng.choices(friends, weights)[0].location
        loc = loc or p.spot or self.choose_area(p)
        p.free_since = self.clock.now()
        if loc == "bar" and not await self.move(p, "bar"):
            loc = self.choose_area(p, no_bar=True)  # every stool is taken
        if loc != "bar" and loc != p.location:
            await self.move(p, loc)
        if p.party is not None:
            await self.convene(p.party)

    async def bartender_on(self, b: PersonState) -> None:
        b.present, b.location = True, "bar"

    def bartender_off(self, b: PersonState) -> None:
        for t in self.threads.values():
            if b.id in t.members:
                self._release(t, b.id)
                if len([m for m in t.members if self.people[m].present and m != b.id]) < 2:
                    t.closing = True
        b.present, b.location, b.thread_id = False, None, None

    # ---------------------------------------------------------------- the world tick

    async def tick(self) -> None:
        now = self.clock.now()
        if self.clock.paused:
            return
        prev = self._last_tick_sim or now
        self._last_tick_sim = now
        dt_min = min((now - prev).total_seconds() / 60, 20)
        day = now.strftime("%Y-%m-%d")
        open_t, close_t = open_close(now)

        if self.news and self.news_for != day:
            self.news, self.news_retry_at = [], None  # yesterday's headlines are not today's
        if self.news_day != day and now.hour >= 10 and (self.news_retry_at is None or now >= self.news_retry_at):
            self.news_day = day
            self.spawn(self.news_desk(day))

        if self.life_day != day:
            self.life_day = day  # claimed now so a slow roll is not started twice
            self.spawn(self.life_step(day))

        await self.update_shift(now)

        if is_open(now):
            self.crowd_days[day] = max(self.crowd_days.get(day, 0.0), self.crowd)
            if self.opened_day != day:
                self.opened_day = day
                await self.post("door", "🔓 Modist Social is open.", kind="system")
                if sales.happy_hour(now):
                    await self.post("door", "🍻 Happy hour until 6pm: half price on " + _names(sales.specials(now)) + ".", kind="system")
            if now >= close_t - timedelta(minutes=LAST_CALL_MIN) and self.last_call_day != day:
                self.last_call_day = day
                await self.post("door", "🔔 Last call in 30 minutes.", kind="system")
                await self.post("bar", "Last call in 30 minutes, folks.", kind="system")
                for p in self.patrons():
                    if p.present and p.leave_at:
                        p.leave_at = min(p.leave_at, close_t + timedelta(minutes=self.rng.uniform(0, 5)))
            if now < close_t - timedelta(minutes=LAST_CALL_MIN):
                await self.arrivals(now, dt_min, day)
                self.walk_ins(now, dt_min)
                self.group_arrivals(now, dt_min)
        elif self.closed_day != day and self.opened_day == day:
            self.closed_day = day
            await self.post("door", "🔒 Modist Social is closed. Thanks for coming out.", kind="system")
            self.spawn(reflect_day(self, day))
        elif not self.threads and not any(p.present for p in self.patrons()) and (resume := launch_time(now)) != now:
            # Nobody is left and nothing is happening: skip the dead hours instead of watching them go by.
            await self.post("door", f"⏩ Closed for the night. Skipping ahead to {(resume + timedelta(minutes=10)).strftime('%-I:%M%p').lower()} opening.", kind="system")
            self.clock.skip_to(resume)
            self._last_tick_sim = self._last_social_sim = None
            return

        if is_open(now):
            await self.environment_step(now)
            self.maybe_refresh_beats(now)
        for p in self.patrons():
            if p.present:
                human.tick(p, dt_min, drunk.decay_mult(p, now))
        await self.sloppy_step(dt_min)
        for p in self.patrons():
            if not p.present or p.leave_at is None:
                continue
            if drunk.tier(p.buzz) == "wasted" and p.thread_id is None:
                p.leave_at = min(p.leave_at, now + timedelta(minutes=20))  # time to go home
            overdue = now >= p.leave_at + timedelta(minutes=25) or (not is_open(now) and now > close_t + timedelta(minutes=10))
            if now >= p.leave_at and (p.thread_id is None or overdue):
                await self.depart(p)
            elif now >= p.leave_at:
                p.wants_leave = True

        real = time.monotonic()
        if real - self._last_social_real >= SOCIAL_EVERY:
            self._last_social_real = real
            prev_s = self._last_social_sim or now
            self._last_social_sim = now
            await self.social_step(now, max((now - prev_s).total_seconds() / 60, 0.0))

    async def sloppy_step(self, dt_min: float) -> None:
        """The drunk make a mess now and then: a dropped glass, a spill, a secret that slips out."""
        for p in self.patrons():
            t = drunk.tier(p.buzz)
            if not p.present or t not in drunk.SLOP_PER_HOUR or self.rng.random() >= drunk.slop_chance(t, dt_min):
                continue
            th = self.threads.get(p.thread_id) if p.thread_id else None
            kind = drunk.roll_slop(self.rng, p, bool(th and th.kind == "chat"))
            if kind == "overshare":
                p.overshare_pending = True
            elif kind:
                text = drunk.slop_text(self.rng, kind, p)
                p.drink = ""
                p.slops.append("dropped a glass" if kind == "dropped_glass" else "spilled a drink")
                human.nudge_mood(p, -0.15)
                for m in (th.members if th else []):
                    if m != p.id and not self.people[m].is_bartender:
                        human.nudge_mood(self.people[m], -0.05)
                await self.post(th.channel if th else p.location, text, kind="system", thread=th)
                self.publish_presence()

    async def environment_step(self, now: datetime) -> None:
        """Things happening in the room itself: the game on the TV, trivia starting."""
        day = now.strftime("%Y-%m-%d")
        prev = self._env_prev if self._env_prev and now - self._env_prev < timedelta(minutes=30) else now
        self._env_prev = now
        g = environment.game_on(now)
        if g and environment.live(g, now) and f"{day}-game" not in self._env_flags:
            self._env_flags.add(f"{day}-game")
            await self.post("bar", f"📺 The {g.team} game is on the bar TV: {g.team} vs. {g.opp}.", kind="system")
        if g:
            for ours, pts, us, them in environment.new_plays(g, prev, now):
                who = g.team if ours else g.opp
                await self.post("bar", f"📺 {who} score. {g.team} {us}, {g.opp} {them}.", kind="system")
                for q in self.patrons():
                    if q.present and environment.fan_of(g.team, q.persona):
                        human.nudge_mood(q, 0.15 if ours else -0.15)
        if environment.trivia_on(now) and f"{day}-trivia" not in self._env_flags:
            self._env_flags.add(f"{day}-trivia")
            await self.post("inside-tables", "🎲 Trivia is starting at the inside tables.", kind="system")

    async def update_shift(self, now: datetime) -> None:
        pair = on_shift(now) if is_open(now) else None
        if pair == self.shift:
            return
        old, self.shift = set(self.shift or ()), pair
        new = set(pair or ())
        for bid in old - new:
            self.bartender_off(self.people[bid])
        for bid in new - old:
            await self.bartender_on(self.people[bid])
        if pair:
            names = " and ".join(self.people[b].display for b in pair)
            await self.post("door", f"🔁 {names} {'are' if len(pair) > 1 else 'is'} behind the bar.", kind="system")
            await self.post("staff", f"Shift starts: {names}.", kind="system")
        self.publish_presence()

    async def arrivals(self, now: datetime, dt_min: float, day: str) -> None:
        for p in self.patrons():
            if p.present or p.visited_day == day:
                continue
            if p.pending_arrival is not None:
                if now >= p.pending_arrival:
                    await self.arrive(p)
                continue
            d = p.persona
            rate = arrival_rate(d.get("freq", 2), d.get("days", []), d.get("window", [17, 20]), now) * self.crowd
            rate *= life.visit_mult(self.life.get(p.id, []), now)
            if self.rng.random() < 1 - math.exp(-rate * dt_min / 60):
                await self.arrive(p)

    def walk_ins(self, now: datetime, dt_min: float) -> None:
        """Now and then a stranger walks in. They are made on the spot (see welcome_newcomer), so this only rolls."""
        if (not settings.newcomers_enabled or self.generating or len(self.patrons()) >= settings.max_patrons
                or self.check_budget()):
            return
        rate = arrival_rate(settings.newcomers_per_week / NEWCOMER_SCALE, NEWCOMER_DAYS, NEWCOMER_WINDOW, now) * self.crowd
        if self.rng.random() < 1 - math.exp(-rate * dt_min / 60):
            self.generating = True
            self.spawn(self.welcome_newcomer())

    async def make_newcomer(self) -> PersonState | None:
        """Make a person who has never been here and save them. None when the name pool is spent."""
        now = self.clock.now()
        picked = newcomers.pick_name(
            self.rng, {q.short for q in self.people.values()} | {short_name(n) for n in self.naming},
            {q.display for q in self.people.values()} | {display_name(n) for n in self.naming})
        if picked is None:
            return None
        name, pronouns = picked
        self.naming.add(name)  # parties make several people at once; keep their names apart
        try:
            return await self._make_newcomer(name, pronouns, now)
        finally:
            self.naming.discard(name)

    async def _make_newcomer(self, name: str, pronouns: str, now: datetime) -> PersonState:
        skel = newcomers.skeleton(self.rng, now)
        raw = None
        if (make := getattr(self.llm, "persona", None)) and not self.check_budget():
            jobs = [q.persona.get("job", "") for q in self.patrons()]
            jobs = self.rng.sample(jobs, min(40, len(jobs)))  # a taste of what's common, so the model varies
            raw = await make(newcomers.brief(name, pronouns, skel, now, settings.brewery_city, jobs))
        return await self.add_person(name, pronouns, newcomers.validate(raw, skel, self.rng))

    async def welcome_newcomer(self) -> None:
        """Make a person who has never been here, save them, and have them walk in."""
        try:
            p = await self.make_newcomer()
            if p is None:
                return  # every name in the pool is taken
            if not is_open(self.clock.now()):
                return  # the bar closed while they were being made; they'll come on their own schedule
            hosts = [q for q in self.patrons() if q.present and q.id != p.id]
            host = self.rng.choice(hosts) if hosts and self.rng.random() < PLUS_ONE_CHANCE else None
            if host:
                await self.befriend(host, p)
            await self.arrive(p)
        finally:
            self.generating = False

    # ---------------------------------------------------------------- parties

    def group_arrivals(self, now: datetime, dt_min: float) -> None:
        """Now and then a party walks in together: regulars, regulars with new faces, or all new faces."""
        if not settings.groups_enabled or self.generating or self.check_budget():
            return
        rate = arrival_rate(settings.groups_per_week / NEWCOMER_SCALE, groups.GROUP_DAYS, groups.GROUP_WINDOW, now) * self.crowd
        if self.rng.random() < 1 - math.exp(-rate * dt_min / 60):
            self.generating = True
            self.spawn(self.welcome_group())

    async def welcome_group(self) -> None:
        try:
            members = await self.build_group(groups.pick_size(self.rng), groups.pick_kind(self.rng))
            if len(members) >= 2 and is_open(self.clock.now()):
                await self.arrive_group(members)
        finally:
            self.generating = False

    def friends_of(self, anchor: PersonState, min_fam: int = 35) -> list[PersonState]:
        """People who are not here, have not been today and know the anchor, closest friends first."""
        day = self.clock.now().strftime("%Y-%m-%d")
        friends = [q for q in self.patrons() if q.id != anchor.id and not q.present and q.visited_day != day
                   and q.pending_arrival is None and self.social.rel(anchor.id, q.id).familiarity >= min_fam]
        self.rng.shuffle(friends)
        return sorted(friends, key=lambda q: -self.social.rel(anchor.id, q.id).familiarity)

    async def build_group(self, size: int, kind: str) -> list[PersonState]:
        """Pick or make the people for a party. Falls short of `size` when the roster or the patron cap runs out."""
        day = self.clock.now().strftime("%Y-%m-%d")
        free = [q for q in self.patrons() if not q.present and q.visited_day != day and q.pending_arrival is None]
        members: list[PersonState] = []
        if kind != "new" and free:
            anchor = self.rng.choice(free)
            members = [anchor]
            want = size if kind == "regulars" else self.rng.randint(1, max(1, size - 1))
            members += self.friends_of(anchor)[:max(0, want - 1)]
            if kind == "regulars" and len(members) < 2:
                kind = "mixed"
        room = max(0, settings.max_patrons - len(self.patrons()))
        need = min(size - len(members), room)
        if kind == "mixed" and len(members) == 1 and need < 1:
            return []
        made = await asyncio.gather(*(self.make_newcomer() for _ in range(max(0, need))), return_exceptions=True)
        for m in made:
            if isinstance(m, PersonState):
                members.append(m)
            elif isinstance(m, Exception):
                log.warning("could not make a party member: %s", m)
        return members

    async def bond_group(self, members: list[PersonState]) -> None:
        """People who come in together already know each other a little, and will remember it."""
        now = self.clock.now()
        names = _names([m.short for m in members])
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if self.social.rel(a.id, b.id).familiarity < 30:
                    for k in range(3):
                        await self.social.apply_delta(a.id, b.id, 8, 3, f"came in together with {names}" if k == 0 else "")
                await self.social.mark_met(a.id, b.id, now)
        for m in members:
            others = [o for o in members if o.id != m.id]
            await self.social.add_memory(m.id, now, f"Came to the taproom with {_names([o.short for o in others])}.",
                                         [o.id for o in others], 5)
        self.publish_relationships([m.id for m in members])

    def claim_party_tables(self, size: int) -> tuple[str, list[int]]:
        """Where a party of this size sits: an area and the tables it holds (none when everything is taken)."""
        now = self.clock.now()
        free, cap = self.area_room()
        w = seating.area_weights(min(size, 3), 1.0, False, False, now, free, cap)
        w["bar"] = 0.0  # a party takes a table
        area = seating.pick_area(self.rng, w)
        order = [area] + [a for a in TABLES if a != area]
        for a in order:
            held = self.held_tables(a)
            empty = [i for i in range(TABLES[a]) if i not in held and not self.table_occupants(a, i)]
            if groups.tables_needed(size) == 1:
                if empty:
                    return a, [self.rng.choice(empty)]
            else:
                pairs = [pr for pr in TABLE_PAIRS[a] if all(i in empty for i in pr)]
                if pairs:
                    return a, list(self.rng.choice(pairs))
        return area, []

    async def arrive_group(self, members: list[PersonState]) -> None:
        """A party walks in together: one door line, one set of tables, one first round, one conversation."""
        now = self.clock.now()
        for m in members:
            self.check_in(m)
        close = open_close(now)[1] + timedelta(minutes=5)
        stays = sorted(m.leave_at for m in members if m.leave_at)
        for m in members:  # they leave about together
            m.leave_at = min(stays[len(stays) // 2] + timedelta(minutes=self.rng.uniform(-10, 10)), close)
            if m.reason in ("solo", "game"):
                m.reason = "catch_up"
        await self.bond_group(members)
        self._party_seq += 1
        area, tables = self.claim_party_tables(len(members))
        leader = max(members, key=lambda m: m.talk)
        pt = PartyState(id=self._party_seq, members=[m.id for m in members], leader=leader.id, area=area, tables=tables)
        if tables:
            for chunk, table in zip(groups.split(pt.members), tables if len(tables) > 1 else tables * 2):
                for pid in chunk:
                    pt.tables_of[pid] = table
        self.parties[pt.id] = pt
        for m in members:
            m.party, m.spot = pt.id, area
        await self.post("door", f"🍺 A group of {len(members)} walks in: {_names([m.display for m in members])}.", kind="system")
        b = bool(self.bartenders_on())
        for m in members:
            if m is leader and b:
                continue  # the leader goes to the bar first
            m.next_drink_at = None if b else now + timedelta(minutes=10)  # with a bartender, the leader's order pays
            m.location, m.free_since, m.stool = area, now, None
            m.table = pt.tables_of.get(m.id)
        if tables or len(members) > 1:
            await self.post(area, f"A group of {len(members)} settles in at the {LOC_DESC[area]}.", kind="system")
        if b:
            await self.request_order(leader, party=[m.id for m in members if m is not leader])
        else:
            await self.settle(leader)
        self.publish_presence()
        await self.convene(pt.id)

    async def convene(self, party: int) -> None:
        """Start the table's conversation: one chat of up to MAX_GROUP for each part of the party that is sitting free."""
        pt = self.parties.get(party)
        if not pt:
            return
        for chunk in groups.split(pt.members):
            sitting = [self.people[m] for m in chunk if self.people[m].present and self.people[m].location == pt.area
                       and not self.people[m].wants_leave]
            free = [q for q in sitting if q.thread_id is None]
            live = next((self.threads[q.thread_id] for q in sitting if q.thread_id in self.threads
                         and self.threads[q.thread_id].kind == "chat" and not self.threads[q.thread_id].closing), None)
            if live:
                for q in free:
                    if len(live.members) < self.max_group(live):
                        await self.join_thread(live, q)
            elif len(free) >= 2:
                await self.open_thread(pt.area, "chat", [q.id for q in free], self.rng.randint(10, 24))

    async def befriend(self, host: PersonState, guest: PersonState) -> None:
        """A friend who brought someone along: they already know each other a little."""
        now = self.clock.now()
        for i in range(5):
            await self.social.apply_delta(host.id, guest.id, 8, 3, f"{host.short} brought {guest.short} along" if i == 0 else "")
        await self.social.mark_met(host.id, guest.id, now)
        await self.social.add_memory(host.id, now, f"Brought {guest.short} along to the taproom for the first time.", [guest.id], 5)
        await self.social.add_memory(guest.id, now, f"{host.short} brought me along to the taproom.", [host.id], 6)
        await self.post("door", f"{host.short} brought {guest.short} along.", kind="system")
        self.publish_relationships([host.id, guest.id])

    async def request_order(self, p: PersonState, party: list[str] | None = None, treat: bool = False) -> None:
        """Ask for a drink: a free bartender takes the order now, otherwise the guest waits in line at the bar."""
        w = Waiting(p.id, self.clock.now(), p.drinks > 0, list(party or []), treat)
        if not p.seated and p.location != "ordering":
            if p.location in LOCATIONS:
                await self.post(p.location, f"{p.short} heads up to the bar{' for another' if w.again else ''}.", kind="system")
            p.location, p.table = "ordering", None
        if b := self.pick_bartender(p):
            await self.open_order(p, b, w)
            return
        self.queue.append(w)
        p.waiting = True
        await self.post("bar" if p.seated else "ordering", f"{p.short} waits for a bartender.", kind="system")
        self.publish_presence()

    async def open_order(self, p: PersonState, b: PersonState, w: Waiting) -> None:
        # A repeat round is offered to a guest on a stool ("another?"); a first drink is asked for.
        t = await self.open_thread("bar" if p.seated else "ordering", "order", [p.id, b.id], max_turns=2 if w.again else 3,
                                   seated=p.seated, again=w.again, ask=w.again and p.seated)
        t.party, t.treat = w.party, w.treat
        self.plan_order(t, p, b)

    def plan_order(self, t: ThreadState, p: PersonState, b: PersonState) -> None:
        """Decide, in code, what this guest means to order and whether the bartender gets to suggest it."""
        now = self.clock.now()
        day = now.strftime("%Y-%m-%d")
        rec = self.taste_of(p)
        specials = sales.specials(now) if sales.happy_hour(now) else []
        tight = taste.budget(p.persona) == "tight" or (p.cap > 0 and p.spent >= 0.6 * p.cap)
        i = taste.intend(rec, p.persona, self.usual_for(p), self.rng, day, specials=specials, tight=tight)
        if p.first_visit and not t.again and i.kind != "rec" and self.rng.random() < 0.5:
            i = taste.Intent("rec", "", "you're new here and the bartender offered a taster")
        t.intent = i
        if i.kind == "rec":
            t.suggest = taste.recommend(b.persona, rec, self.rng, day, specials)
            t.take_rec = taste.takes_rec(p.persona, self.social.rel(p.id, b.id).familiarity, self.rng)
            t.fallback = (taste.top(rec, 1) or [taste.usual(p.persona) or t.suggest])[0]

    def settle_suggestion(self, t: ThreadState, guest: PersonState) -> None:
        """A guest who asked for a suggestion ends up with it or, if they turned it down, with their fallback."""
        i = t.intent
        if i is None or i.kind != "rec" or not t.suggest or t.ordered:
            return
        t.order_drink = t.suggest if t.take_rec else t.fallback
        t.ordered = True
        guest.drink = t.order_drink

    async def serve_queue(self, now: datetime) -> None:
        """First in line gets the next free bartender. After two minutes the order beats a chat: the bartender excuses themselves."""
        self.queue = [w for w in self.queue if self.people[w.pid].present and self.people[w.pid].waiting]
        while self.queue:
            w = self.queue[0]
            p = self.people[w.pid]
            b = self.pick_bartender(p)
            if b is None and now - w.since >= WAIT_BEFORE_INTERRUPT:
                for cand in self.bartenders_on():
                    t = self.bartender_thread(cand)
                    if t and t.kind in ("chat", "staff"):
                        await self.leave_thread(t, cand, f"{cand.short} excuses themselves to serve {p.short}.")
                        b = cand
                        break
            if b is None:
                return
            self.queue.pop(0)
            p.waiting = False
            await self.open_order(p, b, w)

    async def step_out(self, p: PersonState, now: datetime) -> None:
        """A smoker with nobody to talk to steps outside for a few minutes."""
        p.need, p.need_at = "", None
        p.free_since = now + timedelta(minutes=self.rng.uniform(5, 12))
        await self.beat(p, f"🚬 {p.short} steps out front for a smoke.")

    async def idle_beat(self, p: PersonState, now: datetime, game, free: list[PersonState]) -> bool:
        """Something a free guest does while nobody talks to them: a glance at the phone, the TV, the jukebox."""
        live = environment.live(game, now) and p.location == "bar"
        jukebox_ok = self.last_song is None or now - self.last_song >= timedelta(minutes=beats.JUKEBOX_COOLDOWN_MIN)
        kind = beats.roll_idle(self.rng, p, game_live=live, friends_in_area=bool(free), jukebox_ok=jukebox_ok)
        if kind == "jukebox":
            title, artist = beats.pick_song(self.rng, p.persona)
            self.last_song, self.now_playing = now, (title, artist, now + timedelta(minutes=4))
            text = f"🎵 {p.short} puts \"{title}\" by {artist} on the jukebox."
        elif kind in beats.POOLABLE and self.beat_pool.get(p.id) and self.rng.random() < 0.6:
            text = f"{p.short} {self.beat_pool[p.id].pop(0)}."
        else:
            text = beats.idle_text(self.rng, kind, p, game.team if game else "")
        p.busy_until = now + timedelta(minutes=self.rng.uniform(*beats.IDLE_MIN[kind]))
        await self.beat(p, text)
        return True

    def maybe_refresh_beats(self, now: datetime) -> None:
        """Once the room has run out of model-written beats, ask for a fresh batch: one small call, capped per sim hour."""
        guests = [p for p in self.patrons() if p.present]
        if (not settings.llm_beats or self.beat_busy or len(guests) < 3 or not hasattr(self.llm, "beats")
                or sum(len(self.beat_pool.get(p.id, [])) for p in guests) >= len(guests)):
            return
        self.beat_calls = [x for x in self.beat_calls if now - x < timedelta(hours=1)]
        if len(self.beat_calls) >= settings.beat_calls_per_sim_hour or self.check_budget():
            return
        self.beat_calls.append(now)
        self.beat_busy = True
        self.spawn(self.beat_refresh(self.rng.sample(guests, min(8, len(guests))), now))

    async def beat_refresh(self, guests: list[PersonState], now: datetime) -> None:
        try:
            roster = "\n".join(
                f"{p.short} | {p.persona.get('job', '')} | {p.persona.get('quirk', '')} | "
                f"{(p.persona.get('interests') or [''])[0]} | {p.drink or 'no drink'} | {p.location}" for p in guests)
            room = environment.room_line(now, sum(1 for p in self.patrons() if p.present), self.song(now))
            got = await self.llm.beats(roster, room)
        except Exception:
            log.exception("beats call failed")
            got = None
        finally:
            self.beat_busy = False
        for name, lines in (got or {}).items():
            pid = self.resolve(name)
            p = self.people.get(pid) if pid else None
            if not p or p.is_bartender:
                continue
            pool = self.beat_pool.setdefault(pid, [])
            for text in lines:
                if text := beats.clean_beat(text, p):
                    pool.append(text)
            del pool[beats.POOL_PER_PERSON:]

    async def social_step(self, now: datetime, dt_min: float) -> None:
        if self.god and not godmode.alive(self.god, now):
            await self.clear_god()
        await self.social.flush()
        k = max(dt_min, 0.05) * math.sqrt(self.crowd)
        taken: set[str] = set()
        game = environment.game_on(now)
        await self.serve_queue(now)
        for loc in LOCATIONS:
            free = [p for p in self.patrons() if p.present and p.location == loc and p.thread_id is None and not p.waiting
                    and p.free_since is not None and (now - p.free_since).total_seconds() >= 90]
            self.rng.shuffle(free)
            for p in free:
                if p.id in taken:
                    continue
                if self.wants_round(p, now) and self.bartenders_on():
                    taken.add(p.id)
                    friends = self.treat_friends(p, now)
                    await self.request_order(p, [q.id for q in friends], treat=bool(friends))
                    continue
                if p.need == "smoke" and p.need_at and now >= p.need_at:
                    taken.add(p.id)
                    await self.step_out(p, now)
                    continue
                foe = next((q for q in self.patrons() if q.present and q.location == loc and q.id != p.id
                            and bonds.avoids(self.social.rel(p.id, q.id), now)), None)
                if foe and self.rng.random() < _prob(0.05, k):
                    taken.add(p.id)
                    dest = self.rng.choice([x for x in LOCATIONS if x != loc])
                    await self.post(loc, f"{p.short} sees {foe.short} and drifts over to the {dest}.", kind="system")
                    await self.move(p, dest)
                    continue
                joinable = [t for t in self.threads.values()
                            if t.channel == loc and t.kind == "chat" and not t.closing
                            and len(t.members) < self.max_group(t) and t.turns < t.max_turns - 3]
                best, best_p = None, 0.0
                for t in joinable:
                    if any(self.cooling(p.id, m, now) for m in t.members):
                        continue
                    affs = [self.social.rel(p.id, m).affinity for m in t.members]
                    if any(bonds.avoids(self.social.rel(p.id, m), now) for m in t.members):
                        continue
                    fam = max((self.social.rel(p.id, m).familiarity for m in t.members), default=0)
                    pr = _prob(0.03 + 0.3 * fam / 100 + 0.04 * p.talk + (0.05 if self.stool_neighbors(p, t.members) else 0), k)
                    pr = min(0.99, pr * human.drive(p, now) * human.affinity_weight(sum(affs) // max(1, len(affs)))
                             * max((bonds.join_weight(self.social.rel(p.id, m)) for m in t.members), default=1.0))
                    if pr > best_p:
                        best, best_p = t, pr
                if best and self.rng.random() < best_p:
                    await self.join_thread(best, p)
                    taken.add(p.id)
                    continue
                partners = [q for q in free if q.id != p.id and q.id not in taken and not self.cooling(p.id, q.id, now)
                            and not bonds.avoids(self.social.rel(p.id, q.id), now)]
                if partners:
                    fams = [self.social.rel(p.id, q.id).familiarity for q in partners]
                    # Strangers on neighbouring stools strike up a conversation far more often than strangers across the room.
                    near = [1.0 if self.stool_neighbors(p, [x.id]) else 0.0 for x in partners]
                    q = self.rng.choices(partners, [(0.05 + f / 100 + 0.3 * x.talk + 0.4 * n) * human.affinity_weight(self.social.rel(p.id, x.id).affinity) * bonds.join_weight(self.social.rel(p.id, x.id)) * self.wave_boost(p.id, x.id, now)
                                                    for f, x, n in zip(fams, partners, near)])[0]
                    fam = self.social.rel(p.id, q.id).familiarity
                    if self.rng.random() < min(0.99, _prob(0.04 + 0.35 * fam / 100 + 0.04 * p.talk + (0.06 if self.stool_neighbors(p, [q.id]) else 0), k) * human.drive(p, now)):
                        taken |= {p.id, q.id}
                        await self.open_thread(loc, "chat", [p.id, q.id], self.rng.randint(10, 24))
                        continue
                bartenders = self.free_bartenders()
                if loc == "bar" and bartenders:
                    b = self.pick_bartender(p)
                    # Seated regulars chat with the bartenders much more than people standing by.
                    rate = 0.12 + 0.1 * self.social.rel(p.id, b.id).familiarity / 100 if p.seated else 0.05
                    if self.rng.random() < _prob(rate, k):
                        taken.add(p.id)
                        members = [p.id, b.id]
                        quiet = sum(1 for x in self.patrons() if x.present and x.location == "bar") <= 3
                        if quiet and len(bartenders) == 2 and self.rng.random() < 0.25:
                            members = [p.id] + [x.id for x in bartenders]
                        await self.open_thread("bar", "chat", members, self.rng.randint(5, 9))
                        continue
                idle = p.busy_until is None or now >= p.busy_until
                restless = p.reason in ("solo", "game") or p.battery < human.LOW_BATTERY
                if idle and self.rng.random() < _prob(0.04 if restless else 0.012, k):
                    if await self.idle_beat(p, now, game, [q for q in free if q.id != p.id]):
                        continue
                if (now - p.free_since).total_seconds() >= 20 * 60 and self.rng.random() < _prob(0.03, k):
                    busy = [t.channel for t in self.threads.values() if t.kind == "chat" and t.channel != loc and len(t.members) < MAX_GROUP]
                    if busy:
                        taken.add(p.id)
                        await self.move(p, self.rng.choice(busy))

        # Guests in the middle of a conversation elsewhere walk up to the bar when they want another drink.
        for p in self.patrons():
            t = self.threads.get(p.thread_id) if p.thread_id else None
            if (t and t.kind == "chat" and not t.closing and not p.seated and self.wants_round(p, now)
                    and self.rng.random() < _prob(0.25, k) and self.free_bartenders()):
                await self.leave_thread(t, p, f"{p.short} heads up to the bar for another.")
                p.return_to, p.location, p.table = t.id, "ordering", None
                await self.request_order(p)

        pair = [self.people[b] for b in (self.shift or ()) if self.people[b].present]
        staff_open = any(t.channel == "staff" for t in self.threads.values())
        quiet = sum(1 for p in self.patrons() if p.present and p.location == "bar") <= 2
        if len(pair) == 2 and not staff_open and quiet and not self.queue and all(self.bartender_thread(b) is None for b in pair) and self.rng.random() < _prob(0.04, k):
            await self.open_thread("staff", "staff", [b.id for b in pair], self.rng.randint(4, 7))

    # ---------------------------------------------------------------- loop & control

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
                real = time.monotonic()
                if real - self._last_clock_pub >= 1.0:
                    self._last_clock_pub = real
                    bus.publish(self.clock_event())
                if real - self._last_stats_pub >= 3.0:
                    self._last_stats_pub = real
                    bus.publish({"type": "stats", "stats": usage.snapshot()})
                self.govern()
                if real - self._last_save >= 10.0:
                    self._last_save = real
                    await self.save_clock()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("tick failed")
            await asyncio.sleep(TICK)

    def govern(self) -> None:
        """Hold the clock back when model calls are slower than the sim can afford, so a spoken line never costs
        more than LINE_BUDGET sim seconds. Chat per sim hour then looks the same at any speed setting."""
        cap = max(5.0, min(240.0, LINE_BUDGET / self.latency)) if self.latency > 0.05 else 0.0
        if abs(cap - self._last_cap) <= 0.1 * max(cap, self._last_cap):
            return  # not worth rebasing the clock for a small change
        self._last_cap = cap
        self.clock.set_cap(cap or None)

    async def save_clock(self) -> None:
        async with Session() as s:
            await set_state(s, "visits", self.visits)
            await set_state(s, "lives", self.lives)
            await set_state(s, "life_day", {"day": self.life_day})
            await set_state(s, "hangovers", self.hangovers)
            await set_state(s, "drunk_log", self.drunk_log)
            await set_state(s, "taste", {pid: rec.dump() for pid, rec in self.tastes.items()})
            await set_state(s, "taste_log", self.taste_log)
            await set_state(s, "gossip_cred", self.gossip_cred)
            await set_state(s, "gossip_log", self.gossip_log)
            await set_state(s, "group_log", self.group_log)
            await set_state(s, "clock", {
                "sim_now": self.clock.now().isoformat(), "speed": self.clock.speed,
                "crowd": self.crowd, "crowd_days": self.crowd_days,
            })
            await s.commit()

    def god_people(self) -> list[dict]:
        """Who the model hears about when it scores an event: everyone here, then the most frequent visitors.
        Anyone left out still gets a stable stance from a hash of their id (god.stance)."""
        ranked = sorted(self.people.values(), key=lambda p: (not p.present, -float(p.persona.get("freq", 2))))
        return [{"id": p.id, "short": p.short, "persona": p.persona} for p in ranked[:GOD_ROSTER]]

    async def assess_god(self, text: str) -> dict:
        """Score an event (reach, divisiveness, sides, who feels what). One model call, remembered for set_god."""
        text = godmode.clean(text)
        if self._assessed and self._assessed[0] == text:
            return self._assessed[1]
        a = await godmode.assess(self.llm, text, self.god_people())
        self._assessed = (text, a)
        return a

    async def set_god(self, text: str, reach: int | None = None, divisiveness: int | None = None) -> None:
        text = godmode.clean(text)
        a = await self.assess_god(text)
        self.god = godmode.build(text, a, self.clock.now(), reach, divisiveness, self.god_people())
        for t in self.threads.values():
            t.tension = 0.0
            if t.kind == "chat":
                self.roll_event(t)
        async with Session() as s:
            await set_state(s, "god", self.god)
            await s.commit()
        await self.post("door", f"📣 Word around town: {text}", kind="system")
        bus.publish(self.clock_event())

    async def clear_god(self) -> None:
        if not self.god:
            return
        self.god = None
        for t in self.threads.values():
            t.tension = 0.0
        async with Session() as s:
            await s.execute(delete(SimState).where(SimState.key == "god"))
            await s.commit()
        await self.post("door", "📣 The buzz has died down.", kind="system")
        bus.publish(self.clock_event())

    def control(self, action: str, speed: float | None = None, extra_budget: float | None = None,
                crowd: float | None = None) -> None:
        if action == "pause":
            self.clock.pause()
        elif action == "resume":
            if extra_budget:
                usage.budget = usage.spent_today + extra_budget
            if usage.over_budget() and settings.llm_mode == "live":
                self.halt("Budget still exhausted. Add budget to resume.")
                return
            self.budget_paused = False
            self.banner = ""
            self.clock.resume()
            bus.publish({"type": "banner", "text": ""})
        elif action == "speed" and speed:
            self.clock.set_speed(speed)
        elif action == "crowd" and crowd:
            self.crowd = max(0.3, min(crowd, 3.0))
        bus.publish(self.clock_event())

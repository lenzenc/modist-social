import random
import re
from datetime import datetime

from sqlalchemy import select, update

from app.db.models import BondChange, Memory, Relationship, Session
from app.seed.loader import pair_key
from app.sim import bonds
from app.sim.state import MemoryRec, RelState

MAX_MEMORIES = 200  # held in RAM per person; the pool recall scores from
RECALL_MAX = 20  # most memories one chat turn gets
RECALL_QUICK = 6  # order and staff turns are quick, so they get fewer
_WORD = re.compile(r"[a-z]{4,}")


def rel_time(ts: datetime, now: datetime) -> str:
    """How long ago, the way a person would say it."""
    days = (now.date() - ts.date()).days
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"on {ts.strftime('%A')}"
    if days < 14:
        return f"last {ts.strftime('%A')}"
    return f"{days // 7} weeks ago" if days < 60 else "a while back"


def relation_label(rel: RelState) -> str:
    f = rel.familiarity
    if f <= 0:
        return "you have never met"
    if special := bonds.label(rel):
        base = special
    elif rel.kind not in ("stranger", "acquaintance") and f >= 30:
        base = rel.kind
    elif f < 25:
        base = "you've seen them around"
    elif f < 50:
        base = "acquaintances"
    elif f < 75:
        base = "friends"
    else:
        base = "close friends"
    tone = "" if abs(rel.affinity) < 20 else (", you like them" if rel.affinity > 0 else ", they rub you the wrong way")
    return f"{base}{tone}"


class Social:
    """Relationships and memories, held in memory and written through to Postgres."""

    def __init__(self) -> None:
        self.rels: dict[tuple[str, str], RelState] = {}
        self.memories: dict[str, list[MemoryRec]] = {}
        self.done_ids: list[int] = []  # followups raised in conversation, to mark done in the DB

    async def load(self) -> None:
        async with Session() as s:
            for r in (await s.scalars(select(Relationship))).all():
                self.rels[(r.a_id, r.b_id)] = RelState(
                    r.kind, r.familiarity, r.affinity, r.notes, r.met_at,
                    r.bond or bonds.from_seed(r.kind, r.familiarity, r.affinity), r.bond_since, r.bond_until,
                    r.prior or "", r.crush_by or "", r.mentor_id or "",
                )
            rows = (await s.scalars(select(Memory).order_by(Memory.id))).all()
        for m in rows:
            self.memories.setdefault(m.person_id, []).append(MemoryRec(m.sim_ts, m.text, m.about or [], m.importance or 5, m.kind or "event", m.id))
        for pid, lst in self.memories.items():
            del lst[:-MAX_MEMORIES]

    def rel(self, a: str, b: str) -> RelState:
        return self.rels.get(pair_key(a, b)) or RelState()

    async def apply_delta(self, a: str, b: str, fam: int, aff: int, note: str) -> None:
        key = pair_key(a, b)
        rel = self.rels.setdefault(key, RelState())
        rel.familiarity = max(0, min(100, rel.familiarity + max(-8, min(8, fam))))
        rel.affinity = max(-100, min(100, rel.affinity + max(-8, min(8, aff))))
        if rel.kind == "stranger" and rel.familiarity >= 15:
            rel.kind = "acquaintance"
        if rel.bond in ("", "stranger") and rel.familiarity >= 15:
            rel.bond = "acquaintance"
        if note.strip():
            parts = [p for p in rel.notes.split(" | ") if p]
            parts.append(note.strip()[:160])
            # Keep the seeded first note plus the two most recent.
            rel.notes = " | ".join(parts[:1] + parts[1:][-2:]) if len(parts) > 3 else " | ".join(parts)
        async with Session() as s:
            row = await s.get(Relationship, key)
            if row is None:
                row = Relationship(a_id=key[0], b_id=key[1])
                s.add(row)
            row.kind, row.familiarity, row.affinity, row.notes = rel.kind, rel.familiarity, rel.affinity, rel.notes
            row.met_at = rel.met_at
            row.bond = rel.bond
            await s.commit()

    async def set_bond(self, a: str, b: str, change: bonds.Change, now: datetime) -> str:
        """Move a pair to a new bond and record it. Returns the bond they had."""
        key = pair_key(a, b)
        rel = self.rels.setdefault(key, RelState())
        old = rel.bond or "stranger"
        if change.new in ("falling_out", "crush"):
            rel.prior = old
        elif old in ("falling_out", "crush"):
            rel.prior = ""
        rel.bond, rel.bond_since, rel.bond_until = change.new, now, change.until
        rel.crush_by = change.by if change.new == "crush" else ""
        rel.mentor_id = change.by if change.new == "mentor" else ""
        async with Session() as s:
            row = await s.get(Relationship, key)
            if row is None:
                row = Relationship(a_id=key[0], b_id=key[1], kind=rel.kind, familiarity=rel.familiarity,
                                   affinity=rel.affinity, notes=rel.notes, met_at=rel.met_at)
                s.add(row)
            row.bond, row.bond_since, row.bond_until = rel.bond, rel.bond_since, rel.bond_until
            row.prior, row.crush_by, row.mentor_id = rel.prior, rel.crush_by, rel.mentor_id
            s.add(BondChange(a_id=key[0], b_id=key[1], from_bond=old, to_bond=change.new, why=change.why, sim_ts=now))
            await s.commit()
        return old

    async def mark_met(self, a: str, b: str, ts: datetime) -> None:
        """Record the day these two first met."""
        key = pair_key(a, b)
        rel = self.rels.setdefault(key, RelState())
        if rel.met_at is not None:
            return
        rel.met_at = ts
        async with Session() as s:
            row = await s.get(Relationship, key)
            if row is None:
                row = Relationship(a_id=key[0], b_id=key[1], kind=rel.kind, familiarity=rel.familiarity,
                                   affinity=rel.affinity, notes=rel.notes)
                s.add(row)
            row.met_at = ts
            await s.commit()

    async def add_memory(self, pid: str, ts: datetime, text: str, about: list[str], importance: int = 5,
                         kind: str = "event") -> MemoryRec | None:
        text = text.strip()
        if not text:
            return None
        rec = MemoryRec(ts, text, about, max(1, min(10, int(importance))), kind)
        lst = self.memories.setdefault(pid, [])
        lst.append(rec)
        del lst[:-MAX_MEMORIES]
        async with Session() as s:
            row = Memory(person_id=pid, sim_ts=ts, text=text, about=about, importance=rec.importance, kind=kind)
            s.add(row)
            await s.commit()
            rec.id = row.id
        return rec

    def bump(self, rec: MemoryRec, importance: int) -> None:
        rec.importance = max(rec.importance, importance)

    async def flush(self) -> None:
        """Persist followups that came up in conversation."""
        if not self.done_ids:
            return
        ids, self.done_ids = self.done_ids, []
        async with Session() as s:
            await s.execute(update(Memory).where(Memory.id.in_(ids)).values(kind="done"))
            await s.commit()

    def recall_recs(self, pid: str, present: set[str], now: datetime | None = None, text: str = "",
                    k: int = RECALL_MAX) -> list[MemoryRec]:
        """The memories worth having in mind right now, oldest first.

        Each is scored on recency, importance, and relevance (the people in the room, words in the talk), as in
        Park et al.'s generative agents. Followups about someone present always surface; one stray rumor rides along.
        """
        mems = [m for m in self.memories.get(pid, []) if m.kind != "done"]
        if not mems:
            return []
        words = set(_WORD.findall(text.lower()))
        follow = [m for m in mems if m.kind == "followup" and present & set(m.about)][:3]
        rest = [m for m in mems if m not in follow and m.kind != "followup"]

        def score(m: MemoryRec) -> float:
            hours = max(0.0, (now - m.sim_ts).total_seconds() / 3600) if now else 0.0
            rel = 2.0 if present & set(m.about) else 0.0
            rel += min(1.0, 0.3 * len(words & set(_WORD.findall(m.text.lower())))) if words else 0.0
            return 0.995 ** hours + m.importance / 10 + rel

        room = max(1, k - len(follow) - 1)
        picked = sorted(rest, key=score, reverse=True)[:room]
        rumor = [m for m in rest if m.about and not (present & set(m.about)) and m not in picked]
        if rumor and len(picked) + len(follow) < k:
            picked.append(random.choice(rumor))
        return sorted(picked + follow, key=lambda m: m.sim_ts)

    def recall(self, pid: str, present: set[str], k: int = RECALL_MAX, now: datetime | None = None, text: str = "") -> list[str]:
        return [m.text for m in self.recall_recs(pid, present, now, text, k)]

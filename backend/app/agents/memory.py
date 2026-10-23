import logging

from app.agents.prompts import persona_prompt
from app.sim import bonds, gossip, human
from app.sim.social import relation_label
from app.sim.state import LOC_DESC, ThreadState

log = logging.getLogger("memory")

MIN_LINES = 4
TRANSCRIPT_CAP = 30
FIRST_MEETING_LINES = 2  # lines two strangers must share a thread for before it counts as meeting
REFLECT_PEOPLE = 30  # most people one nightly reflection call covers
REFLECT_MEMORIES = 6  # a person's most important memories of the day that go into the nightly reflection


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


async def wrap_up(d, t: ThreadState) -> None:
    """Everything that follows a finished conversation: the summary, and a record of anyone who just met."""
    firsts = first_meetings(d, t)
    mem_done: set[tuple[str, str]] = set()
    rel_done: set[tuple[str, str]] = set()
    try:
        mem_done, rel_done = await summarize_thread(d, t, {_key(a, b) for a, b, _ in firsts})
    finally:
        # The summary can fail or be skipped; a first meeting is still recorded.
        await record_first_meetings(d, t, firsts, mem_done, rel_done)


def first_meetings(d, t: ThreadState) -> list[tuple[str, str, int]]:
    """Pairs who had never met and shared enough of this conversation to count: (a, b, shared speech lines)."""
    ids = [m for m in t.ever if m in d.people and m in t.span]
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            rel = d.social.rel(a, b)
            if rel.familiarity > 0 or rel.met_at is not None:
                continue
            (sa, ea), (sb, eb) = t.span[a], t.span[b]
            lo = max(sa, sb)
            hi = min(len(t.lines) if ea is None else ea, len(t.lines) if eb is None else eb)
            shared = sum(1 for k, _, _ in t.lines[lo:hi] if k == "speech")
            if shared >= FIRST_MEETING_LINES:
                out.append((a, b, shared))
    return out


async def record_first_meetings(d, t: ThreadState, firsts, mem_done: set, rel_done: set) -> None:
    if not firsts:
        return
    now = d.clock.now()
    where = LOC_DESC.get(t.channel, t.channel)
    when = now.strftime("%A %b %-d")
    touched: set[str] = set()
    for a, b, _ in firsts:
        if _key(a, b) not in rel_done:
            await d.social.apply_delta(a, b, 6, 0, f"First met {when} at the {where}")
        await d.social.mark_met(a, b, now)
        for x, y in ((a, b), (b, a)):
            if (x, y) not in mem_done:
                await d.social.add_memory(x, now, f"Met {d.people[y].short} for the first time at the {where}.", [y], 6)
        touched |= {a, b}
    d.publish_relationships(sorted(touched))


async def summarize_thread(d, t: ThreadState, firsts: set | None = None) -> tuple[set, set]:
    """One cheap call per finished conversation: what each person remembers, how relationships moved.

    Returns which (person, other) memories and which pairs' relationships the summary covered.
    """
    firsts = firsts or set()
    mem_done: set[tuple[str, str]] = set()
    rel_done: set[tuple[str, str]] = set()
    speech = [(s, text) for k, s, text in t.lines if k == "speech" and s in d.people]
    speakers = list(dict.fromkeys(s for s, _ in speech))
    if len(speech) < MIN_LINES or len(speakers) < 2:
        return mem_done, rel_done
    transcript = "\n".join(f"{d.people[s].short}: {text}" for s, text in speech[-TRANSCRIPT_CAP:])
    roster = "\n".join(
        f"{d.people[a].short} | "
        + "; ".join(
            f"{d.people[b].short}: " + ("first time meeting" if _key(a, b) in firsts else relation_label(d.social.rel(a, b)))
            for b in speakers if b != a
        )
        for a in speakers
    )
    for q in speakers:
        heard = [d.people[o].short for o in sorted(d.people[q].overshared_with) if o in speakers]
        if heard:
            roster += f"\n({d.people[q].short} drank too much and told {' and '.join(heard)} something private.)"
    result = await d.llm.summarize(transcript, roster)
    if not result:
        return mem_done, rel_done
    now = d.clock.now()
    confronted: set[tuple[str, str]] = set()  # one reckoning per teller and subject, however many heard it
    for m in result.get("memories", []):
        pid = d.resolve(m.get("person", ""))
        if pid not in speakers:
            continue
        about = [x for x in (d.resolve(n) for n in m.get("about", [])) if x and x != pid]
        importance = int(m.get("importance") or 5)
        if any(_key(pid, o) in firsts for o in about):
            importance = max(importance, 6)
        text = m.get("text", "")
        prov = await trace_rumor(d, t, pid, speakers, about, text, m)
        rec = await d.social.add_memory(pid, now, text, about, importance, **prov)
        if rec:
            mem_done |= {(pid, o) for o in about}
            if prov:
                await settle_rumor(d, rec, speakers, confronted)
        if followup := str(m.get("followup", "")).strip():
            await d.social.add_memory(pid, now, followup, about, 6, "followup")
    for r in result.get("relationships", []):
        a, b = d.resolve(r.get("a", "")), d.resolve(r.get("b", ""))
        if not a or not b or a == b or a not in speakers or b not in speakers:
            continue
        key = _key(a, b)
        if key in rel_done:
            continue
        rel_done.add(key)
        fam, aff = int(r.get("familiarity_delta", 0)), int(r.get("affinity_delta", 0))
        await d.social.apply_delta(a, b, fam, aff, r.get("note", ""))
        for pid in (a, b):
            human.nudge_mood(d.people[pid], aff * 0.02)
        await bond_step(d, a, b, str(r.get("moment", "none")), d.resolve(r.get("by", "")) or "", aff, str(r.get("note", "")))
    d.publish_relationships(speakers)
    return mem_done, rel_done


async def trace_rumor(d, t: ThreadState, pid: str, speakers: list[str], about: list[str], text: str, m: dict) -> dict:
    """Provenance for a memory the summary says was heard from someone: where it came from and how much it has changed.

    Empty for anything first-hand. A retelling is linked to the memory the teller actually had in mind, and loses accuracy;
    a claim the teller made up (or blurted when drunk) starts its own chain.
    """
    src = d.resolve(m.get("heard_from", "")) or ""
    if not src or src == pid or src not in speakers or not about:
        return {}
    sure = str(m.get("sure") or "fairly")
    teller = d.people[src]
    cred = gossip.get_cred(d.gossip_cred, src)
    parent = gossip.find_parent(d.social.memories.get(src, []), t.told.get(src, []), set(about), text)
    if parent is not None:
        if parent.origin_id is None:
            await d.social.set_provenance(parent, origin_id=parent.id)
        prov = gossip.retell(parent, text, sure, teller.buzz, cred, d.rng)
        prov["parent_id"] = parent.id
        better = gossip.correction(d.social.memories.get(pid, []), prov["origin_id"], prov["accuracy"])
        if better:
            # The listener knows better and says so; the version they hear is stored as doubtful.
            gossip.bump_cred(d.gossip_cred, src, -3)
            prov["confidence"] = min(prov["confidence"], 25)
            d.gossip_log.append({"day": d.clock.now().date().isoformat(), "origin": prov["origin_id"], "teller": src,
                                 "subject": about[0], "verdict": gossip.verdict(prov["accuracy"]), "kind": "correct"})
    elif pid in teller.overshared_with:
        prov = {"hops": 0, "confidence": 90, "accuracy": 100}  # a drunken confession is true, and now it is out
    else:
        conf = gossip.SURE.get(sure, gossip.SURE["fairly"]) * (0.5 + cred / 200)
        prov = {"hops": 0, "confidence": gossip.clamp(conf, 5), "accuracy": gossip.fresh_claim(teller.buzz, cred, d.rng)}
    prov["source_id"] = src
    return prov


async def settle_rumor(d, rec, speakers: list[str], confronted: set) -> None:
    """A new rumor copy: it roots its own chain if it has none, and if the person it is about is in the room, they hear it."""
    if rec.origin_id is None:
        await d.social.set_provenance(rec, origin_id=rec.id)
    now = d.clock.now()
    for subject in rec.about:
        key = (rec.source_id, subject)
        if subject not in speakers or subject == rec.source_id or key in confronted:
            continue
        confronted.add(key)
        kind = gossip.verdict(rec.accuracy)
        plan = gossip.confrontation(kind, d.rng)
        teller, who = d.people[rec.source_id], d.people[subject]
        await d.social.apply_delta(subject, rec.source_id, 0, plan.aff, f"{teller.short} spread a rumor about {who.short}")
        if plan.origin_aff and (first := _origin_teller(d, rec.origin_id)) not in ("", rec.source_id, subject):
            await d.social.apply_delta(subject, first, 0, plan.origin_aff, "")
        gossip.bump_cred(d.gossip_cred, rec.source_id, plan.cred)
        human.nudge_mood(teller, plan.teller_mood)
        human.nudge_mood(who, plan.subject_mood)
        said = gossip.texts(kind, teller.short, who.short, rec.text)
        await d.social.add_memory(subject, now, said["subject"], [rec.source_id], 8 if kind == "false" else 6)
        await d.social.add_memory(rec.source_id, now, said["teller"], [subject], 7)
        for other in speakers:
            if other in (subject, rec.source_id):
                continue
            await d.social.add_memory(other, now, said["listener"], [subject, rec.source_id], 5)
            if kind == "false":
                for copy in d.social.memories.get(other, []):
                    if copy.origin_id == rec.origin_id and copy.confidence > 20:
                        await d.social.set_provenance(copy, confidence=20)
        if plan.fight:
            await bond_step(d, subject, rec.source_id, "fight", subject, plan.aff, f"{teller.short} spread a lie about {who.short}")
        d.gossip_log = (d.gossip_log + [{"day": now.date().isoformat(), "origin": rec.origin_id, "teller": rec.source_id,
                                         "subject": subject, "verdict": kind, "kind": "confront"}])[-gossip.LOG_KEEP:]


def _origin_teller(d, origin_id: int | None) -> str:
    """Who first told the person who started this chain, if anyone did."""
    for lst in d.social.memories.values():
        for m in lst:
            if m.id == origin_id:
                return m.source_id
    return ""


async def bond_step(d, a: str, b: str, moment: str, by: str, aff_delta: int, note: str = "") -> None:
    """After a conversation: does it change what these two are to each other?"""
    rel = d.social.rel(a, b)
    ch = bonds.step(rel, d.people[a], d.people[b], moment, by, aff_delta, d.clock.now(), d.rng)
    if ch:
        await apply_bond(d, a, b, ch, note)


async def apply_bond(d, a: str, b: str, ch: bonds.Change, note: str = "") -> bool:
    """Make a bond change real: save it, and give both people a memory of it. False if the room has had enough romance today."""
    now = d.clock.now()
    if ch.new in ("crush", "couple"):
        if not d.romance_ok(now):
            return False
        d.romance_used(now)
    old = await d.social.set_bond(a, b, ch, now)
    for pid, text, importance, followup in _bond_memories(d, a, b, ch, old, note, now):
        about = [b if pid == a else a]
        await d.social.add_memory(pid, now, text, about, importance)
        if followup:
            await d.social.add_memory(pid, now, followup, about, 6, "followup")
    d.publish_relationships([a, b])
    return True


def _bond_memories(d, a: str, b: str, ch: bonds.Change, old: str, note: str, now) -> list[tuple[str, str, int, str]]:
    """(person, memory, importance, followup) for each side of a bond change."""
    day = now.strftime("%A")
    out = []
    for me, other in ((a, b), (b, a)):
        o = d.people[other].short
        extra = f" ({note.strip()})" if note.strip() else ""
        text, imp, follow = "", 6, ""
        if ch.new == "falling_out":
            text, imp, follow = f"You and {o} had a falling-out on {day}{extra}.", 8, f"Maybe clear the air with {o}"
        elif old == "falling_out":
            text, imp = (f"You and {o} made up on {day}." if ch.new != "ex" and ch.new != "acquaintance" and ch.new != "rivals"
                         else f"Things with {o} never got patched up; you've drifted apart."), 7
        elif ch.new == "crush":
            if me != ch.by:
                continue  # only the one with the feelings knows
            text, imp = f"You realized you have a crush on {o}.", 8
        elif ch.new == "couple":
            text, imp = f"You and {o} became a couple on {day}.", 9
        elif ch.new == "rivals":
            text, imp = f"You and {o} clearly don't get along{extra}.", 6
        elif ch.new == "ex":
            text, imp = f"You and {o} are over.", 8
        elif ch.new == "mentor":
            text, imp = (f"You took {o} under your wing." if me == ch.by else f"{o} gave you advice you'll remember."), 6
        elif ch.new in ("friends", "close_friends"):
            text, imp = f"You and {o} have become {'close friends' if ch.new == 'close_friends' else 'friends'}.", 6
        elif ch.new == "acquaintance":
            text, imp = f"You and {o} left things on better terms{extra}.", 5
        if text:
            out.append((me, text, imp, follow))
    return out


async def reflect_day(d, day: str) -> None:
    """After closing: each regular who came in thinks over the day, and their life moves on a little."""
    if d.check_budget():
        return
    rows = []
    for p in d.patrons():
        if p.visited_day != day:
            continue
        mems = [m for m in d.social.memories.get(p.id, [])
                if m.sim_ts.strftime("%Y-%m-%d") == day and m.kind in ("event", "reflection")]
        if not mems:
            continue
        mems = sorted(mems, key=lambda m: -m.importance)[:REFLECT_MEMORIES]
        life = p.persona.get("life", "")
        lately = d.lives.get(p.id, "")
        away = "; ".join(e.text for e in d.life.get(p.id, []) if e.ends_at > d.clock.now())
        rows.append((len(mems), (
            f"{p.display} | Life so far: {life}" + (f" Lately: {lately}" if lately else "")
            + (f" Off-screen this week: {away}." if away else "") + "\n"
            + "\n".join(f"  - {m.text}" for m in mems)
        )))
    if not rows:
        return
    rows = [r for _, r in sorted(rows, key=lambda x: -x[0])[:REFLECT_PEOPLE]]
    result = await d.llm.reflect("Today's memories for each person:\n\n" + "\n\n".join(rows))
    if not result:
        return
    now = d.clock.now()
    for row in result.get("people", []):
        pid = d.resolve(row.get("person", ""))
        if not pid or pid not in d.people:
            continue
        for r in row.get("reflections", [])[:2]:
            await d.social.add_memory(pid, now, str(r), [], 7, "reflection")
        if lately := str(row.get("lately", "")).strip():
            d.lives[pid] = lately[:300]
            d.persona_text[pid] = persona_prompt(d.people[pid], d.lives[pid])
    await d.save_clock()

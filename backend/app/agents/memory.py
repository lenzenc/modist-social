import logging

from app.agents.prompts import persona_prompt
from app.sim import human
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
    result = await d.llm.summarize(transcript, roster)
    if not result:
        return mem_done, rel_done
    now = d.clock.now()
    for m in result.get("memories", []):
        pid = d.resolve(m.get("person", ""))
        if pid not in speakers:
            continue
        about = [x for x in (d.resolve(n) for n in m.get("about", [])) if x and x != pid]
        importance = int(m.get("importance") or 5)
        if any(_key(pid, o) in firsts for o in about):
            importance = max(importance, 6)
        if await d.social.add_memory(pid, now, m.get("text", ""), about, importance):
            mem_done |= {(pid, o) for o in about}
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
    d.publish_relationships(speakers)
    return mem_done, rel_done


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
        rows.append((len(mems), (
            f"{p.display} | Life so far: {life}" + (f" Lately: {lately}" if lately else "") + "\n"
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

import random
import re
from datetime import datetime, timedelta

from app.agents.prompts import persona_prompt
from app.config import settings
from app.llm.types import TurnRequest, Utterance
from app.sim import bonds, drunk, environment, human, life
from app.sim import god as godmode
from app.sim import sales
from app.sim.social import RECALL_MAX, RECALL_QUICK, rel_time, relation_label
from app.sim.state import LOC_DESC, LOCATIONS, PersonState, ThreadState
from app.sim.topics import STRANGER_OPENERS, pick_topic

TRANSCRIPT_LINES = 10


def fmt_time(t: datetime) -> str:
    return t.strftime("%A %-I:%M %p")


def clean_say(text: str, p: PersonState) -> str:
    text = text.strip().strip('"“”').strip()
    text = re.sub(rf"^{re.escape(p.short)}\s*:\s*", "", text)
    return text.strip().strip('"“”').strip()


def _drinking(p: PersonState) -> str:
    return f", drinking {p.drink}" if p.drink else " with a beer"


def build_turn(d, t: ThreadState, p: PersonState, wind_down: bool) -> TurnRequest:
    """Assemble the volatile scene for one turn. `d` is the Director."""
    now = d.clock.now()
    rng = random.Random(t.id * 1000 + t.turns)
    others = [d.people[m] for m in t.members if m != p.id and m in d.people]
    # A bartender dropping into a bar thread is not a member but is in the room.
    for sid in {s for _, s, _ in t.lines[-4:] if s in d.people}:
        if sid != p.id and d.people[sid] not in others and d.people[sid].present:
            others.append(d.people[sid])
    present_ids = {o.id for o in others}

    out: list[str] = []
    where = LOC_DESC.get(t.channel, t.channel)
    if p.is_bartender:
        mates = [b.short for b in d.people.values() if b.is_bartender and b.present and b.id != p.id]
        crowd = sum(1 for x in d.people.values() if x.present and not x.is_bartender)
        out.append(
            f"It is {fmt_time(now)}. You are working behind the bar"
            + (f" with {mates[0]}" if mates else "")
            + f"; about {crowd} guests are in the taproom. This conversation is at the {where}."
        )
    elif p.seated:
        out.append(f"It is {fmt_time(now)}. You are sitting on a stool at the {where} of Modist Social{_drinking(p)}.")
        near = [d.people[q].short for q in d.people if d.people[q].present and q != p.id and d.people[q].stool is not None
                and abs(d.people[q].stool - p.stool) <= 2 and q not in {o.id for o in others}]
        if near:
            out.append(f"On the stools near you: {', '.join(near)}.")
    else:
        out.append(f"It is {fmt_time(now)}. You are at the {where} of Modist Social{_drinking(p)}.")

    guests_in = sum(1 for x in d.people.values() if x.present and not x.is_bartender)
    out.append(environment.room_line(now, guests_in))
    if not p.is_bartender and (feel := human.right_now(p, now)):
        out.append(feel)
    mine = d.life.get(p.id, []) if not p.is_bartender else []
    if mind := life.on_mind(mine, now):
        out.append(mind)

    out.append("\nIn this conversation with you:")
    greeted = None
    for o in others:
        rel = d.social.rel(p.id, o.id)
        line = f"- {o.display} ({o.pronouns}; {o.persona['job']}): {relation_label(rel)}."
        if rel.met_at and (now - rel.met_at).days < 7:
            line += f" You met {rel_time(rel.met_at, now)}."
        if hint := (bonds.scene_hint(rel, p.id, o.short, bonds.attached(p.persona), now, rng) if not p.is_bartender and not o.is_bartender else ""):
            line += f" {hint}"
        if rel.notes:
            line += f" What you know: {rel.notes[:220]}"
        out.append(line)
        if not t.lines and rel.familiarity >= 35 and o.arrived_at and now - o.arrived_at < timedelta(minutes=40) and o.gap_days >= 3:
            greeted = (o, o.gap_days)

    around = [x.short for x in d.people.values() if x.present and not x.is_bartender and x.id != p.id and x.id not in present_ids]
    if around:
        out.append(f"\nAlso in the room: {', '.join(rng.sample(around, min(6, len(around))))}.")

    if d.news and (not p.is_bartender or rng.random() < 0.5):
        picks = rng.sample(d.news, min(2, len(d.news)))
        out.append("\nIn the news around town today:\n" + "\n".join(f"- {x}" for x in picks))

    god = getattr(d, "god", None)
    event = god["text"] if god else ""
    now_ = d.clock.now()
    flagging = bool(t.lines) and (t.turns - t.last_topic_turn >= 6 or (len(t.lines) >= 2 and all(len(x[2]) < 25 for x in t.lines[-2:])))
    bled = bool(god) and t.kind == "chat" and not t.on_event and flagging and rng.random() < godmode.bleed(god, now_)
    if bled:
        # A hot story spills into a chat that was about something else.
        t.on_event = True
        t.max_turns += godmode.stretch(god, now_)
    on_event = bool(event) and t.on_event
    stance = ""
    if event:
        out.append(godmode.scene(god, p.id, p.persona, on_event or t.kind != "chat", p.is_bartender, now_))
        stance = godmode.stance(god, p.id, p.persona)

    talk = " ".join(x[2] for x in t.lines[-4:] if x[0] == "speech")
    recs = d.social.recall_recs(p.id, present_ids, now, talk, RECALL_QUICK if t.kind != "chat" else RECALL_MAX)
    if recs:
        out.append("\nThings you remember:")
        for m in recs:
            if m.kind == "followup":
                out.append(f"- (to bring up if it fits) {m.text}")
                m.kind = "done"
                if m.id is not None:
                    d.social.done_ids.append(m.id)
            else:
                out.append(f"- ({rel_time(m.sim_ts, now)}) {m.text}")
    if p.pending_fact:
        out.append(f"\nYou just looked this up on your phone: {p.pending_fact}")
        p.pending_fact = ""

    out.append("\nConversation so far:")
    if t.lines:
        for kind, sid, text in t.lines[-TRANSCRIPT_LINES:]:
            who = d.people[sid].short if sid in d.people else ""
            out.append(f"({text})" if kind == "system" else f"{who}{' (you)' if sid == p.id else ''}: {text}")
    else:
        out.append("(nobody has said anything yet)")

    hints: list[str] = []
    mode = "normal"
    serve, water = "", False  # how the bartender is treating the guest in an order, and whether the guest is switching to water
    last_speaker = next((s for k, s, _ in reversed(t.lines) if k == "speech"), None)
    if t.kind == "order":
        guest = p if not p.is_bartender else next((o for o in others if not o.is_bartender), None)
        if p.is_bartender:
            if t.ask:
                hints.append(f"{guest.short if guest else 'The guest'}'s glass is nearly empty. Ask, in a line, if they would like another (you may suggest something from the board).")
            else:
                what = "wants another round" if t.again else ("just took a seat at the bar" if t.seated else "just walked up to the bar")
                hints.append(f"A guest {what}. Greet them (by name if you know them), recommend or pour something from the board that suits them.")
            if guest:
                hints.append(_register_note(now, guest, d.visits.get(guest.id)))
                serve = drunk.service(guest)
                hints.append(drunk.bartender_note(guest, serve))
        elif t.again and t.ask:
            hints.append(f"The bartender is offering another. {_pick_line(p)} If you want one, say so and put its exact board name in drink (even for 'same again'); if you have had enough, politely pass and leave drink empty. {_pay_note(p)}")
        elif not t.lines and t.again:
            hints.append(f"You're ready for another round. {_pick_line(p)} {_pay_note(p)} Keep it brief.")
        elif not t.lines:
            hints.append(f"You just {'pulled up a stool at' if t.seated else 'walked up to'} the bar. Order a drink from the board by its exact name ({_pick_line(p)}) and say a word to the bartender. {_pay_note(p)}")
        else:
            hints.append("Respond to the bartender and settle up the order. Keep it brief.")
        if not p.is_bartender:
            serve = drunk.service(p)
            water = serve != "cut" and drunk.wants_water(p, rng)
            hints.append(drunk.guest_note(p, serve, water))
    elif t.kind == "staff":
        hints.append("You and your coworker are between orders. Talk shop or share something about the customers or your life.")
    elif not t.lines:
        strangers = [o for o in others if d.social.rel(p.id, o.id).familiarity == 0]
        if greeted:
            hints.append(f"{greeted[0].short} just got here and you haven't seen them in {greeted[1]} days. Greet them the way a friend would.")
        elif on_event:
            hints.append("Start by bringing up the big news today and how you feel about it.")
        elif strangers:
            hints.append(f"You don't know {strangers[0].short}. Start with {rng.choice(STRANGER_OPENERS)}.")
        else:
            hints.append("Start talking: pick up something from your day, or a joke or gossip you know they would like.")
    elif flagging:
        steer = on_event and (bled or rng.random() < 0.5 + 0.4 * godmode.heat(god, now_))
        topic = godmode.steer(event) if steer else pick_topic(rng)
        hints.append(f"If the talk is flagging, steer it toward: {topic}.")
        t.last_topic_turn = t.turns
    if t.kind == "chat" and t.channel == "bar":
        if p.is_bartender:
            hints.append("You're chatting across the bar while you work: friendly and brief, and you may get pulled away to pour.")
        elif any(o.is_bartender for o in others):
            hints.append("You're chatting with the bartender" + (" from your stool." if p.seated else "."))
        elif p.seated:
            hints.append("You're chatting with someone on a nearby stool.")
    if on_event and t.tension >= 1 and t.kind == "chat":
        if p.is_bartender:
            hints.append("Tempers are rising over the news. Keep the peace calmly, without taking a side.")
        else:
            hints.append("This is getting heated between you and the others over the news. Respond to the disagreement itself; don't smooth it over.")
    if t.kind == "chat" and not p.is_bartender:
        if why := t.excuse.get(p.id):
            hints.append(why + " Set action to excuse.")
        if t.lines:
            tipsy_in_room = sum(1 for x in d.people.values() if x.present and not x.is_bartender and drunk.tier(x.buzz) in ("drunk", "wasted"))
            mode = human.length_mode(p, rng, environment.is_loud(guests_in + tipsy_in_room))
            hints.append(human.MODE_HINT[mode])
            if slip := human.moves(rng, p.buzz):
                hints.append(slip)
        if h := drunk.speech_hint(p.buzz):
            hints.append(h)
        if p.overshare_pending and t.lines:
            guests = [o for o in others if not o.is_bartender]
            hints.append(drunk.overshare_hint([o.short for o in guests]))
            p.overshare_pending = False
            p.overshared_with |= {o.id for o in guests}
            p.slops.append("said something you shouldn't have")
    if last_speaker and last_speaker == p.id:
        hints.append("You spoke last; only add something if it moves things forward.")
    if wind_down:
        if d.realism.tidy_share() > 0.5 and rng.random() < 0.5:
            hints.append("The conversation is running out of steam. It can just fizzle, or you get distracted; no goodbye needed.")
        else:
            hints.append("The conversation is winding down. Wrap up naturally, perhaps with a parting remark.")
    avoid = d.realism.avoid_for(p.id, first_line=not t.lines) if settings.realism_feedback else []
    if avoid:
        hints.append("Don't reuse these worn-out phrases or openers: " + ", ".join(f'"{a}"' for a in avoid) + ".")
    if p.id in t.nudge_leave:
        hints.append("It is time for you to head out. Say goodbye in this turn and set action to leave.")
    out.append("\nYour turn, " + p.short + ". " + " ".join(h for h in hints if h))

    return TurnRequest(
        person_id=p.id,
        person_name=p.short,
        world=d.world_text,
        persona=_persona_text(d, p),
        context="\n".join(out),
        last_line=t.lines[-1][2] if t.lines and t.lines[-1][0] == "speech" else "",
        wants_leave=p.id in t.nudge_leave,
        location=t.channel,
        others=[o.short for o in others],
        kind=t.kind,
        is_bartender=p.is_bartender,
        again=t.again,
        event=event if on_event else "",
        stance=stance if on_event else "",
        heat=godmode.heat(god, now_) if god else 0.0,
        tension=t.tension if on_event else 0.0,
        mode=mode if (t.kind == "chat" and not p.is_bartender and t.lines) else "normal",
        mood=p.mood, buzz=p.buzz, battery=p.battery,
        drunk=drunk.tier(p.buzz), serve=serve, water=water,
        excuse=t.excuse.get(p.id, ""),
        avoid=avoid,
        life=(life.freshest(mine, now, 1)[0].text if life.freshest(mine, now, 1) else ""),
    )


def _persona_text(d, p: PersonState) -> str:
    """The cached persona block; built on the spot for anyone who joined after startup and was somehow missed."""
    if p.id not in d.persona_text:
        d.persona_text[p.id] = persona_prompt(p, d.lives.get(p.id, ""))
    return d.persona_text[p.id]


def _pay_note(p: PersonState) -> str:
    return "You're running a tab." if p.pay_mode == "tab" else "You pay by card, drink by drink."


def _register_note(now: datetime, guest: PersonState, visits: dict | None = None) -> str:
    """What the bartender knows about price and how this guest pays. Volatile, so it stays out of the cached world text."""
    parts = ["Every drink is $8."]
    if sales.happy_hour(now):
        parts.append(f"Happy hour is on until 6: half price on {', '.join(sales.specials(now))}.")
    if visits and visits.get("n", 0) >= 3:
        parts.append(f"{guest.short} is a regular (visit number {visits['n']}"
                     + (f", last here {guest.gap_days} days ago" if guest.gap_days else "")
                     + f"); their usual is {guest.persona.get('drink', 'whatever is new')}.")
    if guest.first_visit:
        parts.append(f"{guest.short} is new here: welcome them and offer a taster.")
    if guest.pay_mode == "tab":
        parts.append(f"{guest.short} is running a tab" + (f" ({guest.drinks} so far)." if guest.drinks else " tonight."))
    else:
        parts.append(f"{guest.short} pays by card per drink.")
    return " ".join(parts)


def _pick_line(p: PersonState) -> str:
    usual = p.persona.get("drink", "")
    if p.drink:
        return f"you had {p.drink}; get the same again or try something else"
    return f"your usual is {usual}, but you may try something new" if usual else "pick whatever sounds good"


def sanitize(u: Utterance, p: PersonState) -> Utterance:
    u.say = clean_say(u.say, p)
    if u.action not in ("none", "leave", "move", "introduce", "excuse"):
        u.action = "none"
    if u.mood not in human.MOOD_TAGS:
        u.mood = ""
    if u.action == "move" and u.target not in LOCATIONS:
        u.action, u.target = "none", ""
    return u

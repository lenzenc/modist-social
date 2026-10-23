import random
import zlib

from app.llm.types import TurnRequest, Utterance
from app.sim import menu
from app.sim.realism import norm

_MOMENTS = ["none", "fight", "flirt", "apology", "confided", "advice", "teasing"]
_MOMENT_WEIGHTS = [66, 4, 7, 8, 6, 4, 5]  # mostly nothing, so a mock run shows every arc without a soap opera
_OPENERS = [
    "Hey, is that the new {beer}? How is it?",
    "Long week. I just need one good pint and some quiet.",
    "Is this seat taken? Crowded in here tonight.",
    "Did you see the game last night? Unreal.",
    "The patio fire pits are going. Anyone brave enough?",
]
_REPLIES = [
    "Honestly? Better than I expected. A little hoppy for me, though.",
    "Ha, tell me about it. My boss has been on a tear all week.",
    "I heard the city's about to vote on that bike lane thing again.",
    "You know what I heard about the new development by the river...",
    "Don't get me started on the potholes. My car has opinions.",
    "I tried brewing a saison at home last month. It tasted like pepper and regret.",
    "Wait, really? Who told you that?",
    "That's fair. Cheers to that.",
    "My dog ate half a couch cushion yesterday, so, you know, a normal Tuesday.",
    "The food truck is out front tonight, anyone want anything?",
]
_EVENT_LINES = {
    "feels": ["Can you believe it? {event}. I can't stop thinking about it.", "Everyone's talking about it: {event}. Wild."],
    "pushback": ["Honestly I think people are overreacting about this. {event}? It'll blow over.", "I'm not buying the hype. {event}, so what?"],
    "mixed": ["{event}... I go back and forth. There's a case both ways.", "Part of me gets it, part of me doesn't. {event}."],
    "shrug": ["Eh, {event}. Anyway, how's your beer?", "Not really my thing. Can we talk about something else?"],
}
_HEATED_LINES = [
    "No, that's not it at all. You can't wave that away: {event}.",
    "I'm sorry, but you're wrong about this. {event}, and that matters.",
    "Come on, you can't actually believe that. Think about it.",
    "We're going in circles. I'm not changing my mind on this.",
    "That's exactly the problem with how people talk about this.",
]
_REACTS = ["Ha, no way.", "Ope, really?", "Huh.", "Ha! Fair.", "Yeah, same.", "Wait, what?", "Hm. Maybe.", "Oh come on."]
_TIRED = ["Yeah... sorry, I'm kind of fried tonight.", "Mm. Long day.", "Sure, whatever you think.", "I'm just gonna sit with this beer a sec."]
_LOOSE = [
    "Okay but did I ever tell you about the time I got locked out of my own place? Anyway, a story.",
    "You know what, I love this place. I love you guys. I mean it!",
    "Honestly? Between us? I think everyone's overthinking all of it.",
]
_SLURRED = [
    "Honeshtly? Thish is the besht beer I've had all week.",
    "Wait, wait, lishen. I love thish place. Did I tell you that?",
    "Sho anyway, as I was shaying...",
]
_WASTED = [
    "I'm fine! I'm totally... what were we talking about?",
    "You guysh are the *besht*. Don't tell anyone I said that.",
    "Sho my ex, right, and I shhhould not be telling you thish...",
]
_CUT = ["I think you've had enough for tonight, friend. Let me get you a water.", "That's your last one, I'm afraid. Water's on me, and let's get you a ride."]
_SLOW = ["Sure thing. Maybe a water to go with it?", "Coming up. Want a glass of water alongside?"]
_WATER_ASK = ["Actually, just a water for me, I think.", "Water, please. I should slow down."]
_EXCUSE = ["Be right back, I'll be a few minutes.", "Sorry, I need a breather. Back in a bit.", "Excuse me a sec, nature calls."]
_BEERS = menu.names()
_NEWS = [
    "City council delays vote on the proposed bike-lane expansion",
    "Local brewery wins gold at a regional beer competition",
    "Heavy rain forecast for the weekend; river parks may flood",
    "Neighborhood farmers market moves indoors for the season",
    "Parking meter rate increase proposed downtown",
    "Minneapolis hockey club announces a new head coach",
    "A new taco spot opens on Nicollet this weekend",
    "Light rail service runs on a reduced schedule after midnight this week",
    "Lake Harriet bandshell announces its fall concert lineup",
    "Neighborhood association plans a cleanup along the river trail",
    "Local roaster opens a second cafe near the university",
    "First frost expected overnight, gardeners urged to cover tomatoes",
]


def _fresh(lines: list[str], avoid: list[str], r: random.Random) -> str:
    """A canned line that doesn't contain a worn-out phrase, if there is one."""
    ok = [x for x in lines if not any(a in norm(x) for a in avoid)]
    return r.choice(ok or lines)


class MockLLM:
    """Canned dialogue so the entire simulation and UI can be exercised for $0."""

    async def speak(self, req: TurnRequest) -> Utterance | None:
        r = random.Random()
        if req.last_line:
            say = _fresh(_REPLIES, req.avoid, r)
        else:
            say = _fresh([x.format(beer=r.choice(_BEERS)) for x in _OPENERS], req.avoid, r)
        if req.life and not req.last_line and not req.is_bartender and r.random() < 0.4:
            say = f"Ugh, {req.life.rstrip('.')}."
        action, target, drink = "none", "", ""
        if req.kind == "order" and req.again and req.is_bartender and not req.last_line:
            say = "Can I get you another?"
        elif req.kind == "order" and req.again and not req.is_bartender and req.last_line:
            if r.random() < 0.75:
                drink = r.choice(_BEERS)
                say = f"Yes please, another {drink}."
            else:
                say = "I'm good for now, thanks."
        elif req.kind == "order" and not req.last_line and not req.is_bartender:
            drink = r.choice(_BEERS)
            say = f"Can I get a {drink}, please?"
        elif req.kind == "order" and req.is_bartender and not req.last_line:
            say = "Welcome in. What can I get you?"
        if req.kind == "order" and req.is_bartender and req.serve in ("cut", "slow"):
            say = r.choice(_CUT if req.serve == "cut" else _SLOW)
        elif req.kind == "order" and not req.is_bartender and (req.water or req.serve == "cut"):
            drink, say = "Water", r.choice(_WATER_ASK)
        elif req.event and req.kind == "chat" and req.tension >= 1 and not req.is_bartender and r.random() < 0.7:
            say = r.choice(_HEATED_LINES).format(event=req.event.rstrip(".!"))
        elif req.event and req.kind == "chat" and r.random() < 0.35:
            say = r.choice(_EVENT_LINES.get(req.stance, _EVENT_LINES["feels"])).format(event=req.event.rstrip(".!"))
        if req.kind == "chat" and req.last_line and not req.is_bartender:
            if req.mode == "react" or req.battery < 0.3:
                say = r.choice(_REACTS if req.mode == "react" else _TIRED)
            elif req.drunk in ("drunk", "wasted") and r.random() < 0.5:
                say = r.choice(_WASTED if req.drunk == "wasted" else _SLURRED)
            elif req.buzz > 0.4 and r.random() < 0.4:
                say = r.choice(_LOOSE)
        if req.wants_leave:
            say = "Alright, I should get going. Good talking to you all."
            action = "leave"
        elif req.excuse:
            say, action = r.choice(_EXCUSE), "excuse"
        elif req.kind != "order" and r.random() < 0.04:
            action, target = "move", r.choice(["patio", "inside-tables", "bar"])
        lookup = "who won the Twins game last night" if r.random() < 0.02 else ""
        mood = "annoyed" if req.tension >= 1 else r.choice(["good", "fine", "fine", "meh"])
        return Utterance(say=say, action=action, target=target, lookup=lookup, drink=drink, mood=mood)

    async def summarize(self, transcript: str, roster: str) -> dict | None:
        names = [line.split("|")[0].strip() for line in roster.splitlines() if "|" in line]
        mems = [{"person": n, "text": "Chatted at the taproom; learned a little about the others.", "about": [],
                 "importance": 3, "followup": ""} for n in names]
        rels = []
        r = random.Random(zlib.crc32(transcript.encode()))
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                moment = r.choices(_MOMENTS, _MOMENT_WEIGHTS)[0]
                rels.append({"a": a, "b": b, "familiarity_delta": 3, "affinity_delta": -5 if moment == "fight" else 2,
                             "note": "", "moment": moment, "by": r.choice([a, b]) if moment != "none" else ""})
        return {"memories": mems, "relationships": rels}

    async def news(self, city: str, date_text: str, recent: list[str]) -> list[str]:
        fresh = [x for x in _NEWS if x not in recent]
        return random.sample(fresh if len(fresh) >= 4 else _NEWS, 4)

    async def persona(self, brief: str) -> dict | None:
        return None  # newcomers are built from the template pools instead

    async def reflect(self, digest: str) -> dict | None:
        return {"people": []}  # nothing to add in mock mode

    async def polish(self, who: str, event: str) -> str | None:
        return None  # the template text stands

    async def classify(self, event: str, roster: str) -> dict | None:
        return None  # the keyword estimate in sim.god is used instead

    async def lookup(self, query: str, city: str) -> str | None:
        return f"(mock) A quick search suggests the answer to '{query}' is: close game, went to extra innings."

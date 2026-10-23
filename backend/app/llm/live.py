import asyncio
import json
import logging

import anthropic

from app.config import settings
from app.llm.types import TurnRequest, Utterance
from app.llm.usage import usage

log = logging.getLogger("llm")

UTTERANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "say": {"type": "string"},
        "action": {"type": "string", "enum": ["none", "leave", "move", "introduce", "excuse"]},
        "target": {"type": "string"},
        "lookup": {"type": "string"},
        "drink": {"type": "string"},
        "mood": {"type": "string", "enum": ["good", "fine", "meh", "annoyed", "down"]},
    },
    "required": ["thought", "say", "action", "target", "lookup", "drink", "mood"],
    "additionalProperties": False,
}

PERSONA_SCHEMA = {
    "type": "object",
    "properties": {
        "job": {"type": "string"},
        "traits": {"type": "array", "items": {"type": "string"}},
        "politics": {"type": "string"},
        "drink": {"type": "string"},
        "interests": {"type": "array", "items": {"type": "string"}},
        "quirk": {"type": "string"},
        "voice": {"type": "string"},
        "life": {"type": "string"},
        "takes": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "tics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["job", "traits", "politics", "drink", "interests", "quirk", "voice", "life", "takes", "avoid", "tics"],
    "additionalProperties": False,
}

REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person": {"type": "string"},
                    "reflections": {"type": "array", "items": {"type": "string"}},
                    "lately": {"type": "string"},
                },
                "required": ["person", "reflections", "lately"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["people"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person": {"type": "string"},
                    "text": {"type": "string"},
                    "about": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "integer"},
                    "followup": {"type": "string"},
                },
                "required": ["person", "text", "about", "importance", "followup"],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                    "familiarity_delta": {"type": "integer"},
                    "affinity_delta": {"type": "integer"},
                    "note": {"type": "string"},
                    "moment": {"type": "string", "enum": ["none", "fight", "flirt", "apology", "confided", "advice", "teasing"]},
                    "by": {"type": "string"},
                },
                "required": ["a", "b", "familiarity_delta", "affinity_delta", "note", "moment", "by"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["memories", "relationships"],
    "additionalProperties": False,
}

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "reach": {"type": "integer"},
        "divisiveness": {"type": "integer"},
        "sides": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "stance": {"type": "string", "enum": ["feels", "pushback", "mixed", "shrug"]},
                },
                "required": ["id", "stance"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reach", "divisiveness", "sides", "reason", "people"],
    "additionalProperties": False,
}

# Haiku 5.5 takes the basic web search tool (the dynamic-filtering _20260209 variant is not offered).
WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}


class AnthropicLLM:
    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
        self.sem = asyncio.Semaphore(settings.max_concurrent_llm)

    async def _create(self, **kwargs):
        """One API call with usage accounting. Returns the response, or None on failure."""
        async with self.sem:
            try:
                resp = await self.client.messages.create(model=settings.model, **kwargs)
            except anthropic.RateLimitError as e:
                usage.errors += 1
                wait = int(e.response.headers.get("retry-after", "10"))
                log.warning("rate limited; backing off %ss", wait)
                await asyncio.sleep(min(wait, 60))
                return None
            except anthropic.APIStatusError as e:
                usage.errors += 1
                log.error("API error %s: %s", e.status_code, e.message)
                return None
            except anthropic.APIConnectionError as e:
                usage.errors += 1
                log.error("connection error: %s", e)
                return None
            except TypeError as e:
                # The SDK raises a bare TypeError when no credentials can be resolved.
                usage.errors += 1
                log.error("no usable Anthropic credentials: %s", e)
                return None
        searches = getattr(getattr(resp.usage, "server_tool_use", None), "web_search_requests", 0) or 0
        usage.record(resp.usage, searches)
        return resp

    @staticmethod
    def _text(resp) -> str:
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def _json(self, resp, what: str) -> dict | None:
        if resp is None:
            return None
        if resp.stop_reason in ("refusal", "max_tokens"):
            log.warning("%s: stop_reason=%s", what, resp.stop_reason)
            return None
        try:
            return json.loads(self._text(resp))
        except json.JSONDecodeError:
            log.warning("%s: unparseable JSON", what)
            return None

    async def speak(self, req: TurnRequest) -> Utterance | None:
        resp = await self._create(
            max_tokens=settings.max_output_tokens,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": UTTERANCE_SCHEMA}},
            # Prefix order matters for caching: world (shared by everyone), then persona (per person),
            # then the volatile scene in the user turn.
            system=[
                {"type": "text", "text": req.world, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": req.persona, "cache_control": {"type": "ephemeral"}},
            ],
            messages=[{"role": "user", "content": req.context}],
        )
        data = await self._json(resp, "speak")
        if not data or not str(data.get("say", "")).strip():
            return None
        return Utterance(
            say=data["say"].strip(),
            action=data.get("action", "none"),
            target=data.get("target", ""),
            lookup=data.get("lookup", ""),
            drink=data.get("drink", ""),
            thought=str(data.get("thought", "")).strip()[:200],
            mood=data.get("mood", ""),
        )

    async def summarize(self, transcript: str, roster: str) -> dict | None:
        resp = await self._create(
            max_tokens=1000,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
            system=(
                "You keep the memory ledger for a taproom simulation. Given a conversation transcript, write what "
                "each speaker would realistically remember afterwards, and how each pair's relationship shifted. "
                "Memories are first-person, one concrete sentence each (a fact learned, a promise, a rumor heard, "
                "a disagreement), at most 2 per person, and only about things actually said. 'about' lists the "
                "names of other people the memory concerns (including third parties who were discussed). "
                "importance is 1 to 10: 2 for small talk, 5 for something worth bringing up again, 8 or more for a "
                "big confession, a fight or a promise. People who are meeting for the first time (marked in the "
                "list) should remember their first impression of each other. followup is one short first-person "
                "thing to ask or follow up on next time they talk (for example 'Ask Dana how the interview went'), "
                "or an empty string if there is nothing natural to follow up on. "
                "Relationship deltas: familiarity 0 to 8, affinity -8 to 8. Strangers who just met and chatted "
                "pleasantly gain about +4 familiarity. Use a short note only when something worth remembering "
                "about the pair happened, otherwise an empty string. moment is 'none' unless one clearly happened between the pair: "
                "a real fight, flirting (not just friendliness), an apology, one confiding something personal, "
                "advice from the more experienced, or playful teasing. by is the name of who did it (flirted, "
                "apologized, gave the advice), or an empty string. Use names exactly as given."
            ),
            messages=[{"role": "user", "content": f"People (name | what they already know of each other):\n{roster}\n\nTranscript:\n{transcript}"}],
        )
        return await self._json(resp, "summarize")

    async def persona(self, brief: str) -> dict | None:
        resp = await self._create(
            max_tokens=900,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": PERSONA_SCHEMA}},
            system=(
                "You invent ordinary, specific people for a neighborhood taproom simulation. Given a name, age and "
                "temperament, write the rest of who they are. Make them believable and particular: a real job, "
                "real hobbies, a quirk you could actually notice, opinions someone could argue with (some should be "
                "contrarian or unfashionable). No cliches, no caricatures, no brand names, no real people. Strings "
                "are short (a phrase or one sentence). 'voice' is how they talk, 'quirk' is a small habit, 'life' is "
                "one or two sentences on where their life stands now and what brought them here for the first time, "
                "'takes' are firm opinions as short statements, 'avoid' are topics they steer away from (can be "
                "empty), 'tics' are speech habits. 'drink' is their usual: use a name from the taproom board if you "
                "know one, otherwise a style of beer. Write in the third person, using no pronouns for the person "
                "except in 'life' where you may say 'they'."
            ),
            messages=[{"role": "user", "content": brief}],
        )
        return await self._json(resp, "persona")

    async def reflect(self, digest: str) -> dict | None:
        resp = await self._create(
            max_tokens=4000,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": REFLECT_SCHEMA}},
            system=(
                "You keep the inner life of regulars at a neighborhood taproom. For each person below you get what "
                "they remember from today. For each, write 1 or 2 reflections: first-person, one sentence, a "
                "higher-level realization drawn from several of the memories (who they are warming to or clashing "
                "with, how the place feels, what is on their mind). Then write 'lately': one or two sentences, in "
                "the third person, updating where their life stands now, building on 'Life so far' and moving it "
                "forward only a little (a small development, not a dramatic change). Use names exactly as given."
            ),
            messages=[{"role": "user", "content": digest}],
        )
        return await self._json(resp, "reflect")

    async def polish(self, who: str, event: str) -> str | None:
        resp = await self._create(
            max_tokens=80,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            system=(
                "You add texture to small things that happen to ordinary people away from a neighborhood taproom. "
                "You are given a person and an event written as a clause with no subject, such as 'had the car break "
                "down on Wednesday, and the repair bill is ugly'. Rewrite it in the same form: a single clause with no "
                "subject, starting with a verb, under 25 words, adding one concrete, believable detail that fits this "
                "person (a specific part, place, name or number). Keep the same facts and the same day, and stay "
                "mundane: no dramatic escalation. Never use the person's name, age or job, and never use pronouns "
                "(he, she, his, her, him). No final period. Reply with the clause only."
            ),
            messages=[{"role": "user", "content": f"Person: {who}\nEvent: {event}"}],
        )
        return self._text(resp) if resp else None

    async def classify(self, event: str, roster: str) -> dict | None:
        resp = await self._create(
            max_tokens=4000,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
            system=(
                "You judge how a piece of news lands in a neighborhood taproom. Score it on two scales, 1 to 5.\n"
                "reach: how many people care. 1 = only dedicated fans or insiders (a regular-season game, a politician's "
                "passing remark); 3 = a good share of the room; 5 = nearly everyone (a championship, a market crash, a war).\n"
                "divisiveness: how much people split into opposing sides. 1 = everyone agrees; 2 = shared feeling with "
                "friendly rivalry (a championship, a market crash); 4-5 = people pick strong sides and argue (war, "
                "contested politics, culture-war issues).\n"
                "sides: two short phrases (under 8 words each) naming the two camps: the first is the common reaction, "
                "the second is the opposing or dissenting one.\n"
                "reason: one sentence on why you scored it that way.\n"
                "people: one entry for every person in the roster, by id. stance is feels (with the common reaction), "
                "pushback (on the opposing side, or thinks it is overblown), mixed (torn), or shrug (does not care). "
                "Decide from each person's job, politics, interests and traits: a non-fan shrugs at a low-reach sports "
                "result, a fan feels it, and on a divisive issue the room should split along their politics and values."
            ),
            messages=[{"role": "user", "content": f"News: {event}\n\nRoster (id | name | job | politics | interests | traits):\n{roster}"}],
        )
        return await self._json(resp, "classify")

    async def _search(self, prompt: str, max_tokens: int) -> str | None:
        """Run a prompt with web search enabled, resuming if the server tool loop pauses."""
        messages = [{"role": "user", "content": prompt}]
        for _ in range(3):
            resp = await self._create(
                max_tokens=max_tokens, thinking={"type": "disabled"}, output_config={"effort": "low"},
                tools=[WEB_SEARCH], messages=messages,
            )
            if resp is None:
                return None
            if resp.stop_reason == "pause_turn":
                messages = [messages[0], {"role": "assistant", "content": resp.content}]
                continue
            # Server-tool errors come back as ordinary 200 results, so just take whatever text survived.
            return self._text(resp) or None
        return None

    async def news(self, city: str, date_text: str, recent: list[str]) -> list[str]:
        seen = "".join(f"\n- {x}" for x in recent[:18])
        text = await self._search(
            f"Today is {date_text}. Search the web for the most recent news around {city}: 3 local news or "
            "politics items, 2 local events or sports results, and 1 craft beer industry item. "
            + (f"These were already reported on earlier days, so do not repeat them or cover the same story:{seen}\n" if seen else "")
            + "If the search turns up fewer than 6 genuinely new items, complete the 6 with plausible, low-stakes local "
            "happenings for that date (a neighborhood event, a restaurant opening or closing, the weather, a local team "
            "result, a brewery release). "
            "Reply with exactly 6 lines, each starting with '- ', each a single plain sentence of at most 25 "
            "words with no citations or links, and never mention the search itself.",
            max_tokens=900,
        )
        if not text:
            return []
        lines = [ln[2:].strip() for ln in text.splitlines() if ln.startswith("- ")]
        return [x for x in lines if not x.startswith("I ") and "search results" not in x][:8]

    async def lookup(self, query: str, city: str) -> str | None:
        return await self._search(
            f"Quick web lookup for someone chatting at a bar near {city}: {query}\n"
            "Answer in at most 2 plain sentences with the key facts only, no links or citations.",
            max_tokens=250,
        )

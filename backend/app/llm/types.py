from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TurnRequest:
    """Everything one utterance call needs. `world`/`persona` are the cacheable prefix."""

    person_id: str
    person_name: str
    world: str
    persona: str
    context: str
    # Used only by the mock backend.
    last_line: str = ""
    wants_leave: bool = False
    location: str = "bar"
    others: list[str] = field(default_factory=list)
    kind: str = "chat"  # chat | order | staff
    is_bartender: bool = False
    again: bool = False  # a repeat order
    event: str = ""  # God Mode event this chat is about, if any
    stance: str = ""  # this person's stance on it: feels | pushback | mixed | shrug
    heat: float = 0.0  # how hot the event is right now, 0..1
    tension: float = 0.0  # how heated this chat has got between opposing sides
    mode: str = "normal"  # react | normal | story: how long this line should be
    mood: float = 0.0
    buzz: float = 0.0
    battery: float = 1.0
    drunk: str = ""  # sober | tipsy | drunk | wasted
    serve: str = ""  # in an order: how the bartender treats the guest (pour | slow | cut)
    water: bool = False  # the guest means to ask for water
    want: str = ""  # in an order: the drink the guest has decided on (empty while they ask for a suggestion)
    ask_rec: bool = False  # the guest asks the bartender what they would pour
    suggest: str = ""  # the drink the bartender is to recommend
    treat: str = ""  # the guest is buying a round for these people (comma-separated names)
    excuse: str = ""  # why this person should bow out of the chat this turn
    avoid: list[str] = field(default_factory=list)  # worn-out phrases and openers; the mock steers around them
    life: str = ""  # the freshest thing on this person's mind from off-screen, for the mock to bring up
    rumor: tuple[str, str] | None = None  # (who it's about, what was said): a rumor the mock may repeat
    lull: bool = False  # the talk just stalled (the mock may answer with a gesture alone)
    cut: bool = False  # break off mid-sentence and step away for a call
    joke: bool = False  # make a joke or tease someone
    laughed: bool | None = None  # the last joke landed (True) or didn't (False) with this person; None if there wasn't one
    interrupted: bool = False  # this line gets talked over: the mock trails off with a dash
    interrupting: str = ""  # talk over this person
    steer: str = ""  # change the subject on purpose to this
    outsider: bool = False  # on the outside of this chat
    vibe: str = ""  # the table's mood: lively | easy | flat | tense
    tired: str = ""  # a bartender's fatigue: tired | worn out (empty when fresh)
    rough: bool = False  # a bartender having a rough night
    peeve: bool = False  # the guest in this order trips the bartender's pet peeve
    favorite: bool = False  # the guest in this order is one of the bartender's favourites
    gripe: str = ""  # in a staff chat: the coworker this bartender is annoyed with (or who is annoyed with them, with grumble False)
    grumble: bool = True  # in a staff chat with a gripe: this bartender is the one complaining
    occasion: str = ""  # what's special tonight: a holiday, a band, a release, a power outage (empty on an ordinary night)
    birthday: str = ""  # "you" if it's this person's birthday, else the name of the birthday guest in the room
    farewell: str = ""  # "you" if this person is about to move away, else the name of the friend who is
    back_in_town: bool = False  # this person moved away and is back for a visit
    incident: str = ""  # an incident going on right now: power_out | fire_alarm


@dataclass
class Utterance:
    say: str
    action: str = "none"  # none | leave | move | introduce | excuse
    target: str = ""
    lookup: str = ""
    drink: str = ""  # exact menu name when ordering or pouring a specific drink
    thought: str = ""  # a private thought that nobody hears
    mood: str = ""  # how they feel after this line: good | fine | meh | annoyed | down
    beat: str = ""  # a small physical action as a clause with no subject ("glances at the TV"); say may be empty


class LLM(Protocol):
    async def speak(self, req: TurnRequest) -> Utterance | None: ...

    async def summarize(self, transcript: str, roster: str) -> dict | None: ...

    async def news(self, city: str, date_text: str, recent: list[str]) -> list[str]: ...

    async def lookup(self, query: str, city: str) -> str | None: ...

    async def persona(self, brief: str) -> dict | None: ...

    async def reflect(self, digest: str) -> dict | None: ...

    async def classify(self, event: str, roster: str) -> dict | None: ...

    async def polish(self, who: str, event: str) -> str | None: ...

    async def beats(self, roster: str, room: str) -> dict[str, list[str]] | None: ...

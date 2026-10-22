import re
from dataclasses import dataclass, field
from datetime import datetime

LOCATIONS = ["bar", "inside-tables", "patio"]
CHANNELS = ["door", "ordering", "bar", "inside-tables", "patio", "staff"]
CHANNEL_DESC = {
    "door": "Arrivals, departures and shift changes",
    "ordering": "Walk-up orders at the end of the bar",
    "bar": "Sitting at the long oak bar: seated orders and conversations",
    "inside-tables": "Inside tables by the windows",
    "patio": "Heated patio and fire pits",
    "staff": "Behind the bar, bartenders only",
}
LOC_DESC = {
    "ordering": "end of the bar, waiting to order",
    "bar": "long oak bar",
    "inside-tables": "inside tables by the front windows",
    "patio": "heated patio by the fire pits",
    "staff": "back of the bar between orders",
}
MAX_GROUP = 4
MAX_GROUP_BAR = 5  # a bar chat can hold guests plus one or both bartenders
BAR_STOOLS = 20
TABLES = {"inside-tables": 14, "patio": 6}  # tables per area; each seats a full group
TABLE_SEATS = MAX_GROUP
# Tables that sit next to each other in the floor plan (frontend/src/taproom/layout.ts: keep the two in step);
# a party of 5-8 pushes a pair together.
TABLE_PAIRS = {
    "inside-tables": [(i, i + 1) for row in (0, 7) for i in range(row, row + 6)],
    "patio": [(i, i + 1) for row in (0, 3) for i in range(row, row + 2)],
}


def short_name(name: str) -> str:
    m = re.search(r'"(\w+)"', name)
    return m.group(1) if m else name.split()[0]


def display_name(name: str) -> str:
    return f"{short_name(name)} {name.split()[-1]}"


@dataclass
class PersonState:
    id: str
    name: str
    short: str
    display: str
    role: str
    pronouns: str
    color: str
    persona: dict
    present: bool = False
    location: str | None = None
    thread_id: int | None = None
    free_since: datetime | None = None
    leave_at: datetime | None = None
    wants_leave: bool = False
    visited_day: str = ""
    pending_fact: str = ""
    pending_arrival: datetime | None = None
    last_spoke: datetime | None = None
    stool: int | None = None  # set while sitting at the bar
    table: int | None = None  # table index within their area; None when standing
    spot: str | None = None  # the area they chose for this visit (bar, inside-tables, patio)
    drink: str = ""  # what they are currently drinking (a menu name)
    drinks: int = 0  # drinks bought this visit
    drink_goal: int = 0  # how many they want this visit
    next_drink_at: datetime | None = None  # when they will want the next one
    pay_mode: str = "card"  # card (per drink) | tab
    tab_id: int | None = None  # open tab payment
    return_to: int | None = None  # chat thread to rejoin after a trip to the bar
    reason: str = "unwind"  # why they came tonight: see human.REASON_TEXT
    mood: float = 0.0  # -1..1
    buzz: float = 0.0  # 0..1, from drinks, wears off
    battery: float = 1.0  # 0..1 social energy
    need: str = ""  # a pending need: see human.NEEDS
    need_at: datetime | None = None
    busy_until: datetime | None = None  # doing something solo (phone, reading) until then
    arrived_at: datetime | None = None
    gap_days: int = 0  # days since their previous visit when they arrived
    thought: str = ""  # their latest private thought
    first_visit: bool = False  # a walk-in on their first ever visit
    party: int | None = None  # the party they walked in with, while it is still here
    waiting: bool = False  # in line for a bartender

    @property
    def seated(self) -> bool:
        return self.stool is not None

    @property
    def talk(self) -> float:
        return float(self.persona.get("talk", 0.6))

    @property
    def is_bartender(self) -> bool:
        return self.role == "bartender"


@dataclass
class ThreadState:
    id: int
    channel: str
    kind: str  # chat | order | staff
    started: datetime
    members: list[str]
    ever: dict[str, None]  # insertion-ordered set of everyone who took part
    max_turns: int
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, speaker_id, text)
    turns: int = 0
    closing: bool = False
    failures: int = 0
    last_topic_turn: int = -10
    nudge_leave: set[str] = field(default_factory=set)
    seated: bool = False  # an order placed from a bar stool
    again: bool = False  # a repeat order
    ordered: bool = False  # the guest has named a drink in this thread
    lingered: bool = False  # already rolled whether the order turns into a chat
    ask: bool = False  # the bartender opens by asking a seated guest if they want another
    order_drink: str = ""  # the menu drink this order settled on
    charged: bool = False  # the order has been rung up (or declined)
    on_event: bool = False  # this chat is mostly about the God Mode event
    tension: float = 0.0  # how heated opposing sides in an on-event chat have got
    stepped_in: bool = False  # a bartender has already calmed this chat down
    table: int | None = None  # the table this chat sits at (inside-tables and patio only)
    party: list[str] = field(default_factory=list)  # the leader's party: their first drinks ride on this order
    excuse: dict[str, str] = field(default_factory=dict)  # who should bow out this turn, and why
    span: dict[str, list] = field(default_factory=dict)  # pid -> [first line index, last line index or None]


@dataclass
class Waiting:
    """A guest in line for a bartender."""
    pid: str
    since: datetime
    again: bool  # a repeat round rather than a first drink
    party: list[str] = field(default_factory=list)  # a party leader's order pays for these first rounds


@dataclass
class PartyState:
    id: int
    members: list[str]
    leader: str
    area: str
    tables: list[int]  # tables held for the party, whether or not everyone is sitting at them
    tables_of: dict[str, int] = field(default_factory=dict)  # member -> their table


@dataclass
class RelState:
    kind: str = "stranger"
    familiarity: int = 0
    affinity: int = 0
    notes: str = ""
    met_at: datetime | None = None


@dataclass
class MemoryRec:
    sim_ts: datetime
    text: str
    about: list[str]
    importance: int = 5
    kind: str = "event"  # event | reflection | followup | done
    id: int | None = None

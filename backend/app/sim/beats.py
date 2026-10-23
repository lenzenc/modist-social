"""Physical and non-verbal behavior: action beats, awkward silences, and people breaking off mid-sentence.

Pure functions over a PersonState, in the style of drunk.py and human.py. Everything here is deterministic given an rng;
the model only adds its own beats, through the `beat` field of a turn and the batched `beats` call.
"""
import random
import zlib

from app.sim import realism

SMOKE_SHARE = 0.12  # share of people with no smoking in their persona who step out for one anyway
JUKEBOX_COOLDOWN_MIN = 20
CUT_CHANCE = 0.03  # per guest line, once a chat is a few turns in
CUT_MIN_TURNS = 3
CHAT_BEAT_CHANCE = 0.1  # per gap between lines, at an ordinary temperament
POOL_PER_PERSON = 3  # model-written idle beats held for each guest
GESTURE_ODDS = 0.1  # share of chat turns that are told a gesture is welcome
LULL_BASE = 0.04
LULL_MAX = 0.35
QUIET = {"green": (12, 40), "amber": (5, 55)}  # share of everything said or done that is not speech, in percent

SMOKE_NO = ("non-smok", "nonsmok", "quit smoking", "doesn't smoke", "does not smoke")
MUSIC_WORDS = ("music", "band", "concert", "vinyl", "guitar", "song", "drummer", "bass", "dj", "record")

IDLE = {
    "phone": ["{p} scrolls through {pos} phone.", "{p} thumbs out a text and sets {pos} phone face-down.",
              "{p} reads something on {pos} phone and snorts.", "{p} checks {pos} phone, then pockets it."],
    "tv": ["{p} glances up at the {team} game on the TV.", "{p} watches the {team} game on the bar TV.",
           "{p} groans at something on the TV."],
    "board": ["{p} studies the chalkboard like it owes {pos} money.", "{p} squints at the tap list, undecided."],
    "people_watch": ["{p} people-watches over {pos} pint.", "{p} looks around the room, taking it all in."],
    "time_check": ["{p} checks the time.", "{p} glances at the clock behind the bar."],
    "coaster": ["{p} turns {pos} coaster over and over.", "{p} peels the label off a coaster."],
    "laugh_across": ["{p} catches someone's eye across the room and grins.", "{p} laughs at something across the room."],
}
IDLE_MIN = {"phone": (5, 15), "tv": (10, 25), "board": (2, 6), "people_watch": (5, 12), "time_check": (1, 3),
            "coaster": (3, 8), "laugh_across": (1, 3), "jukebox": (2, 4)}
POOLABLE = ("phone", "board", "people_watch", "time_check", "coaster")  # kinds a model-written beat can stand in for

CHAT_BEATS = [
    "{p} takes a slow sip of {pos} {drink}.",
    "{p} glances at {pos} phone.",
    "{p} looks around the room.",
    "{p} turns {pos} glass on the coaster.",
    "{p} leans back and stretches.",
]
TV_BEAT = "{p} keeps half an eye on the TV."
WAVES = ["{p} spots {q} come in and raises a hand.", "{p} waves {q} over with a big grin.", "{p} catches {q}'s eye and nods hello."]
LULL_TEXT = ["A lull. Nobody says anything for a moment.", "The conversation stalls; everyone studies their glasses.",
             "A beat of awkward quiet.", "The table goes quiet for a bit."]
LULL_HINT = "The talk just went quiet. You can break the silence, or let it sit and answer with a gesture."
GESTURE_HINT = "A small physical beat is welcome (put it in beat), and if a gesture says it better than words, leave say empty."
CUT_HINT = ("Your phone buzzes mid-sentence: break off in the middle of your line with a dash (—) and step away to take it. "
            "Set action to excuse.")
JUKEBOX = [  # title, artist, what it sounds like
    ("Mr. Brightside", "The Killers", "rock"), ("Dancing Queen", "ABBA", "pop"), ("Folsom Prison Blues", "Johnny Cash", "country"),
    ("Take Five", "Dave Brubeck", "jazz"), ("Purple Rain", "Prince", "pop"), ("Hurt", "Johnny Cash", "country"),
    ("Float On", "Modest Mouse", "rock"), ("Jolene", "Dolly Parton", "country"), ("Free Bird", "Lynyrd Skynyrd", "rock"),
    ("Hey Ya!", "OutKast", "hip hop"), ("The Weight", "The Band", "folk"), ("Fast Car", "Tracy Chapman", "folk"),
    ("So What", "Miles Davis", "jazz"), ("Lose Yourself", "Eminem", "hip hop"),
]


def pos(p) -> str:
    return "her" if p.pronouns.startswith("she") else "his" if p.pronouns.startswith("he") else "their"


def _blob(persona: dict) -> str:
    return " ".join(str(v) for v in (persona.get("quirk"), persona.get("life"), *(persona.get("interests") or []),
                                      *(persona.get("traits") or []))).lower()


def smoker(p) -> bool:
    """Whether this person steps out for a smoke: their persona says so, else a stable roll on their id."""
    blob = _blob(p.persona)
    if any(k in blob for k in SMOKE_NO):
        return False
    if any(k in blob for k in ("smok", "cigar", "vape")):
        return True
    return zlib.crc32(p.id.encode()) % 100 < SMOKE_SHARE * 100


def music_fan(persona: dict) -> bool:
    return any(k in _blob(persona) for k in MUSIC_WORDS)


def roll_idle(rng: random.Random, p, *, game_live: bool, friends_in_area: bool, jukebox_ok: bool) -> str:
    """What a free guest does with a quiet moment: a key of IDLE, "jukebox", or "" for nothing."""
    w = {"phone": 3.0, "board": 1.5, "people_watch": 2.0, "time_check": 1.0, "coaster": 1.0}
    if p.reason == "solo" or p.battery < 0.3:
        w["phone"] += 3
    if game_live:
        w["tv"] = 7.0 if p.reason == "game" else 3.0
    if friends_in_area:
        w["laugh_across"] = 2.0
    if jukebox_ok:
        w["jukebox"] = 3.0 if music_fan(p.persona) else 0.8
    return rng.choices(list(w), list(w.values()))[0]


def idle_text(rng: random.Random, kind: str, p, team: str = "") -> str:
    return rng.choice(IDLE[kind]).format(p=p.short, pos=pos(p), team=team)


def wave_text(rng: random.Random, p, q) -> str:
    return rng.choice(WAVES).format(p=p.short, q=q.short)


def pick_song(rng: random.Random, persona: dict) -> tuple[str, str]:
    blob = _blob(persona)
    w = [1.0 + (3.0 if vibe in blob else 0.0) for _, _, vibe in JUKEBOX]
    title, artist, _ = rng.choices(JUKEBOX, w)[0]
    return title, artist


def chat_beat(rng: random.Random, p, game_live: bool) -> str:
    """A small action between lines in a chat, or "" most of the time. Reserved people and the drained fidget more."""
    chance = CHAT_BEAT_CHANCE * (1.5 if p.battery < 0.3 or p.persona.get("style") == "listener" else 1.0)
    if rng.random() >= chance:
        return ""
    pool = CHAT_BEATS + ([TV_BEAT] if game_live else [])
    return rng.choice(pool).format(p=p.short, pos=pos(p), drink=(p.drink or "beer").split(" - ")[0])


def lull_chance(last_short: bool, flagging: bool, in_a_row: int) -> float:
    """Chance the talk stalls after this line: more likely after a very short line or when the chat is running dry."""
    c = LULL_BASE + (0.08 if last_short else 0.0) + (0.1 if flagging else 0.0) + 0.1 * in_a_row
    return min(LULL_MAX, c)


def cut_due(rng: random.Random, turns: int) -> bool:
    return turns >= CUT_MIN_TURNS and rng.random() < CUT_CHANCE


def clean_beat(text: str, p) -> str:
    """A model-written beat as a bare clause: no quotes, asterisks, name or final period."""
    text = text.strip().strip('*"“”_ ').strip()
    if text.lower().startswith(p.short.lower() + " "):
        text = text[len(p.short) + 1:]
    return text.rstrip(".").strip()[:80]


# ---------------------------------------------------------------- the scorecard


def quiet_share(actions: int, speech: int, lulls: int = 0) -> dict:
    """How much of what happens in the room is not speech. Too little is a room of talking heads; too much, a mime show."""
    n = actions + speech
    share = None if n < realism.MIN_LINES else round(100 * actions / n)
    lo, hi = QUIET["green"]
    alo, ahi = QUIET["amber"]
    band = "none" if share is None else "green" if lo <= share <= hi else "amber" if alo <= share <= ahi else "red"
    return {"share": share, "band": band, "actions": actions, "speech": speech, "lulls": lulls}

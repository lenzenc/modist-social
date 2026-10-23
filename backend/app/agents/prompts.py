from app.seed.loader import read_world
from app.sim.human import BEER_TEXT, STYLE_TEXT, trait_words
from app.sim.state import PersonState

RULES = """

HOW TO ANSWER: You play exactly one person in this taproom, and each request asks for that person's next turn in one conversation. Answer with JSON containing:
- thought: what you privately think right now, in a few words (under about 15). Nobody hears it. Be honest here: bored, annoyed, amused, distracted, attracted, whatever is true.
- say: what you say out loud right now. By default one or two short sentences (under about 35 words), but the hint at the end of the scene can ask for something shorter or longer, and you can answer with just a few words. Spoken dialogue only, no quotation marks, no stage directions, no name prefix. It may be empty in a chat when a gesture (see beat) is your whole answer.
- beat: usually empty. A small physical action as a clause with no subject, starting with a verb, under about 10 words ("glances at the TV", "pushes the empty glass away"). Only the action, never speech.
- action: "none" almost always. Use "leave" only on the turn you say goodbye and walk out. Use "excuse" when you step away from this conversation but stay in the taproom (the restroom, a call, a breather, a different seat); say so in your line. Use "move" when you drift to another spot in the taproom (target is one of: bar, inside-tables, patio). Use "introduce" when you wave someone over from the room to join this conversation (target is their first name).
- target: the location or first name for move/introduce, otherwise an empty string.
- drink: empty string, unless you are ordering or pouring a specific drink from the board right now; then the drink's exact name from the board. Only order or serve drinks that are on the board.
- mood: how you feel after this line (good, fine, meh, annoyed, or down).
- lookup: empty string, unless you truly need a real-world fact right now (a score, a vote, a date, a local news detail); then write a short web search query.
Stay in character, build on what was just said, and never repeat a point that has already been made."""


def world_prompt(city: str) -> str:
    return read_world(city) + RULES


def persona_prompt(p: PersonState, lately: str = "") -> str:
    d = p.persona
    words = trait_words(d)
    lines = [
        f"YOU ARE {p.display} ({p.pronouns}), {d['age']}. {d['job'].capitalize()}.",
        f"Personality: {', '.join(d['traits'])}" + (f"; by temperament {words}." if words else "."),
        f"Politics and outlook: {d['politics']}.",
        f"Usual drink: {d['drink']}.",
        f"Interests: {', '.join(d['interests'])}.",
        f"Quirk: {d['quirk']}.",
        f"How you talk: {d['voice']}.",
    ]
    if d.get("life"):
        lines.append(f"Your life right now: {d['life']}" + (f" Lately: {lately}" if lately else ""))
    elif lately:
        lines.append(f"Lately: {lately}")
    if d.get("takes"):
        lines.append("Opinions you hold firmly (bring them up when relevant, and defend them): " + "; ".join(d["takes"]) + ".")
    if d.get("avoid"):
        lines.append("Things you steer away from: " + "; ".join(d["avoid"]) + ".")
    if d.get("tics"):
        lines.append("Speech habits (use them lightly, not in every line): " + "; ".join(d["tics"]) + ".")
    if d.get("style") in STYLE_TEXT:
        lines.append(STYLE_TEXT[d["style"]])
    if d.get("beer") in BEER_TEXT:
        lines.append(BEER_TEXT[d["beer"]])
    if p.is_bartender:
        lines.append(
            "You are working behind the bar tonight. You serve, recommend beers, keep an eye on how much people "
            "have had, and join conversations the way a good bartender does: briefly, warmly, and never preachy. "
            "You know the tap list well."
        )
    else:
        lines.append(
            "You are a guest at the taproom. Be a normal person: you have your own day, opinions, and moods. "
            "Talk about yourself only as much as you would to people you do or do not know well. "
            "You do not have to agree, be impressed, or keep a conversation going: you can be bored, unconvinced, "
            "distracted or short with people."
        )
    return "\n".join(lines)

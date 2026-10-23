import re
import unicodedata
from pathlib import Path

import yaml

DRINKS_FILE = Path(__file__).parent.parent / "seed" / "drinks.yaml"
WATER = "Water"  # free, always available, and not in drinks.yaml so it never turns up as a pick or a happy-hour special

# Display order and the style keywords that put a drink in each section (first match wins).
SECTIONS = [
    ("Seltzers, slushies and THC drinks", ("thc", "seltzer", "slushy")),
    ("Stouts and barrel-aged", ("stout", "barrel", "bourbon", "reserve")),
    ("Hazy and hoppy IPAs", ("ipa",)),
    ("Sours, goses and wheat ales", ("sour", "gose", "fruit", "wheat", "pickle")),
    ("Lagers, pilsners and classics", ()),
]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def default_board() -> list[dict]:
    """The snapshot of what is on tap that ships in drinks.yaml; the director replaces it with the live board at each start."""
    return yaml.safe_load(DRINKS_FILE.read_text())


_board: list[dict] = default_board()  # what is on tap right now: see sim.taplist


def set_board(entries: list[dict]) -> None:
    """Put these drinks on the board (the director calls this on load once it has read the website)."""
    _board[:] = [dict(e) for e in entries]


def drinks() -> list[dict]:
    return _board


def kind(name: str) -> str | None:
    """beer, hard_seltzer, thc_seltzer or thc_soda; None for water or an unknown name."""
    return next((d.get("kind", "beer") for d in drinks() if d["name"] == name), None)


def is_mainstay(name: str) -> bool:
    return any(d["name"] == name and d.get("mainstay") for d in drinks())


def beers(mainstay: bool | None = None) -> list[str]:
    """Names of the beers on tap, optionally only the mainstays (True) or only the rest (False)."""
    return [d["name"] for d in drinks() if d.get("kind", "beer") == "beer" and (mainstay is None or bool(d.get("mainstay")) == mainstay)]


def strength_label(d: dict) -> str:
    """'5.2%' for a drink with alcohol, '10 mg THC' for a THC one, '' when neither is stated."""
    if d.get("thc_mg"):
        return f"{d['thc_mg']:g} mg THC"
    return f"{d['abv']:g}%" if d.get("abv") else ""


def names() -> list[str]:
    return [d["name"] for d in drinks()]


def match(text: str) -> str | None:
    """Return the menu name mentioned in `text` (exact, then longest contained), or None."""
    if not text:
        return None
    t = f" {_norm(text)} "
    by_norm = {_norm(d["name"]): d["name"] for d in drinks()}
    if t.strip() in by_norm:
        return by_norm[t.strip()]
    hits = [n for n in by_norm if f" {n} " in t]
    if hits:
        return by_norm[max(hits, key=len)]
    return WATER if " water " in t else None


def abv(name: str) -> float | None:
    """A drink's strength; water is 0 and an unlisted or unstated one is None."""
    if name == WATER:
        return 0.0
    return next((d.get("abv") for d in drinks() if d["name"] == name), None)


def _section(d: dict) -> int:
    if d.get("kind", "beer") != "beer":
        return 0
    s = f"{d['style']} {d['name']}".lower()
    for i, (_, keys) in enumerate(SECTIONS[:-1]):
        if any(k in s for k in keys):
            return i
    return len(SECTIONS) - 1


def section_of(name: str) -> int:
    """Which tap-list section a drink sits in (a rough style bucket); -1 for water or an unknown name."""
    d = next((x for x in drinks() if x["name"] == name), None)
    return _section(d) if d else -1


def render_tap_list() -> str:
    lines = []
    for i, (title, _) in enumerate(SECTIONS):
        group = [d for d in drinks() if _section(d) == i]
        if not group:
            continue
        lines.append(f"{title}:")
        for d in group:
            strength = f" - {label}" if (label := strength_label(d)) else ""
            star = " (mainstay)" if d.get("mainstay") else ""
            lines.append(f"- {d['name']}{star} - {d['style']}{strength} - {d['note']}")
    lines.append(f"Always free: {WATER}")
    return "\n".join(lines)

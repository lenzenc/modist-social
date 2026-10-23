import re
import unicodedata
from functools import lru_cache
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


@lru_cache(maxsize=1)
def drinks() -> list[dict]:
    return yaml.safe_load(DRINKS_FILE.read_text())


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
    s = f"{d['style']} {d['name']}".lower()
    for i, (_, keys) in enumerate(SECTIONS[:-1]):
        if any(k in s for k in keys):
            return i
    return len(SECTIONS) - 1


def render_tap_list() -> str:
    lines = []
    for i, (title, _) in enumerate(SECTIONS):
        group = [d for d in drinks() if _section(d) == i]
        if not group:
            continue
        lines.append(f"{title}:")
        for d in group:
            abv = f" - {d['abv']:g}%" if d.get("abv") else ""
            lines.append(f"- {d['name']} - {d['style']}{abv} - {d['note']}")
    lines.append(f"Always free: {WATER}")
    return "\n".join(lines)

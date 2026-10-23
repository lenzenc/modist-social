import colorsys
import logging
from pathlib import Path

import yaml
from sqlalchemy import func, select

from app.db.models import Person, Relationship, Session

log = logging.getLogger("seed")
HERE = Path(__file__).parent

PALETTE = [
    "#e8912d", "#2eb67d", "#36c5f0", "#e01e5a", "#9b59b6", "#1264a3", "#d1453b", "#4a9c6d",
    "#c77dba", "#0f9d9a", "#b8860b", "#7a6ff0", "#e5683c", "#3b8ed4", "#8c6d46", "#c2185b",
]


def color_for(index: int) -> str:
    """A distinct, readable colour for the Nth person: hues step by the golden angle so neighbours never match."""
    r, g, b = colorsys.hls_to_rgb((index * 0.618033988749895) % 1.0, 0.5, 0.55)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def read_world(city: str) -> str:
    from app.sim.menu import render_tap_list  # local import: menu lives in the sim package

    return (HERE / "world.md").read_text().replace("{city}", city).replace("{tap_list}", render_tap_list())


def _persona(row: dict) -> dict:
    keep = ("age", "job", "traits", "politics", "drink", "interests", "quirk", "voice", "talk", "freq", "days", "window", "stay",
            "bar_seat", "pay", "tipper", "big5", "life", "beer", "style", "takes", "avoid", "tics", "reasons", "budget", "peeve", "rough")
    return {k: row[k] for k in keep if k in row}


async def _sync_personas(s) -> None:
    """Refresh persona cards from the YAML so menu/persona edits apply without wiping relationships and memories."""
    rows = yaml.safe_load((HERE / "patrons.yaml").read_text()) + yaml.safe_load((HERE / "bartenders.yaml").read_text())
    people = {p.id: p for p in (await s.scalars(select(Person))).all()}
    for r in rows:
        p = people.get(r["id"])
        if p and p.persona != _persona(r):
            p.persona = _persona(r)
    await s.commit()


async def seed_if_empty() -> None:
    async with Session() as s:
        if (await s.scalar(select(func.count()).select_from(Person))) > 0:
            await _sync_personas(s)
            return
        log.info("seeding people and relationships")
        rows = [("patron", r) for r in yaml.safe_load((HERE / "patrons.yaml").read_text())]
        rows += [("bartender", r) for r in yaml.safe_load((HERE / "bartenders.yaml").read_text())]
        for i, (role, r) in enumerate(rows):
            s.add(Person(
                id=r["id"], name=r["name"], role=role, pronouns=r["pronouns"],
                color=PALETTE[i % len(PALETTE)], persona=_persona(r),
            ))
        await s.flush()
        for r in yaml.safe_load((HERE / "relationships.yaml").read_text()):
            a, b = pair_key(r["a"], r["b"])
            s.add(Relationship(
                a_id=a, b_id=b, kind=r["kind"], familiarity=r["familiarity"],
                affinity=r["affinity"], notes=r.get("notes", ""),
            ))
        await s.commit()

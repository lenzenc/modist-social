"""What is on tap at the real Modist Brewing, read from modistbrewing.com/drinks. Costs no tokens.

The page lists every drink ever made; the "On Tap" toggle is only a client-side filter on each card's `data-category`
tags, so the static HTML already has what we need.
"""
import asyncio
import html
import logging
import re

import httpx

from app.config import settings
from app.sim.menu import _norm

log = logging.getLogger("taplist")

KINDS = ("beer", "hard_seltzer", "thc_seltzer", "thc_soda")
CARD = re.compile(r'<li data-category="([^"]*)"[^>]*>(.*?)</li>', re.S)
TIMEOUT = 15.0


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _kind(cats: set[str], style: str) -> str | None:
    if "thc" in cats:
        return "thc_soda" if "soda" in style.lower() else "thc_seltzer"
    if "hard-seltzer" in cats:
        return "hard_seltzer"
    if "beer" in cats:
        return "beer"
    return None


def parse(page: str) -> list[dict]:
    """Every on-tap card: {name, kind, style, abv, thc_mg, mainstay, note, url}. Off-tap and unreadable cards are skipped."""
    out = []
    for m in CARD.finditer(page):
        cats = {c.strip() for c in m.group(1).split(",") if c.strip()}
        if "on-tap" not in cats:
            continue
        body = m.group(2)
        ps = [_text(p) for p in re.findall(r"<p>(.*?)</p>", body, re.S)]
        names = re.findall(r"<h3>(.*?)</h3>", body, re.S)
        if not names or not ps:
            continue
        name, style = _text(names[0]), ps[0]
        kind = _kind(cats, style)
        if not name or kind is None:
            log.warning("skipping %r: no drink type in %s", name, sorted(cats))
            continue
        strength = ps[1] if len(ps) > 1 else ""
        abv = mg = None
        if mg_m := re.search(r"([\d.]+)\s*mg", strength, re.I):
            mg = float(mg_m.group(1))
            mg = int(mg) if mg == int(mg) else mg
        elif abv_m := re.search(r"([\d.]+)\s*%", strength):
            abv = float(abv_m.group(1))
        url = (re.findall(r'href="([^"]+)"', body) or [""])[0]
        out.append({"name": name, "kind": kind, "style": style, "abv": abv, "thc_mg": mg,
                    "mainstay": "mainstays" in cats, "note": style, "url": url})
    return out


def blurb(page: str) -> str:
    """The first sentence of a drink page's description, which follows 'Available to go Yes/No'."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
    m = re.search(r"Available to go\s+(?:Yes|No)\s+(.*?)(?:Join our mailing list|$)", _text(body), re.S)
    text = m.group(1).strip() if m else ""
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0] if text else ""
    return first[:200]


def diff(old: list[dict], new: list[dict]) -> tuple[list[dict], list[dict]]:
    """(added, removed): drinks only in `new`, and drinks only in `old`, matched by normalised name."""
    have, want = {_norm(d["name"]) for d in old}, {_norm(d["name"]) for d in new}
    return [d for d in new if _norm(d["name"]) not in have], [d for d in old if _norm(d["name"]) not in want]


async def fetch_board(old: list[dict] | None = None) -> list[dict] | None:
    """The live on-tap board, or None if the site could not be read (the caller then keeps what it has).

    A drink already on `old` keeps its note; a new one gets its page's first sentence, falling back to the style.
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (modist-social)"}) as c:
            r = await c.get(settings.tap_url)
            r.raise_for_status()
            board = parse(r.text)
            if not board:
                log.warning("tap list parsed to nothing; keeping the current board")
                return None
            known = {_norm(d["name"]): d for d in old or []}
            fresh = [d for d in board if _norm(d["name"]) not in known]
            pages = await asyncio.gather(*(c.get(d["url"]) for d in fresh if d["url"]), return_exceptions=True)
            for d, p in zip([d for d in fresh if d["url"]], pages):
                if isinstance(p, httpx.Response) and p.status_code == 200 and (b := blurb(p.text)):
                    d["note"] = b
    except (httpx.HTTPError, OSError) as e:
        log.warning("could not read the tap list: %s", e)
        return None
    for d in board:
        if (was := known.get(_norm(d["name"]))) and was.get("note"):
            d["note"] = was["note"]
    return board

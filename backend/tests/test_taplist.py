import asyncio
from pathlib import Path

import pytest

from app.sim import menu, taplist
from tests.test_occasions import _room

FIXTURE = (Path(__file__).parent / "fixtures" / "modist_drinks.html").read_text()


@pytest.fixture(autouse=True)
def default_board():
    menu.set_board(menu.default_board())
    yield
    menu.set_board(menu.default_board())


def _by_name(board):
    return {d["name"]: d for d in board}


def test_parse_keeps_only_what_is_on_tap_with_its_type_strength_and_mainstay():
    board = _by_name(taplist.parse(FIXTURE))
    assert len(board) == 29  # the three archived cards in the fixture are left out
    assert {d["kind"] for d in board.values()} == set(taplist.KINDS)
    dream = board["DREAMYARD"]
    assert (dream["kind"], dream["style"], dream["abv"], dream["thc_mg"], dream["mainstay"]) == ("beer", "Hazy IPA", 7.1, None, True)
    assert board["Fallforge"]["mainstay"] is False and board["Fallforge"]["abv"] == 5.2
    pop = board["MELT POP Citrus Punch"]
    assert (pop["kind"], pop["thc_mg"], pop["abv"], pop["mainstay"]) == ("thc_soda", 10, None, True)
    assert board["Half MELT Ginger Lemon Lime"]["thc_mg"] == 5 and board["TINT Blackberry Lime"]["kind"] == "thc_seltzer"
    assert board["Blueberry Blitz"]["kind"] == "hard_seltzer" and board["Skull Hard Seltzer Pineapple Key Lime Sea Salt"]["mainstay"]
    assert "Piña Colada Slushy" in board  # entities are unescaped
    assert board["Grape Ape"]["kind"] == "beer" and board["Grape Ape"]["abv"] == 11


def test_diff_finds_new_and_gone_drinks_by_name():
    old = [{"name": "Fallforge"}, {"name": "Old Beer"}]
    new = [{"name": "FALLFORGE"}, {"name": "New Beer"}]
    added, removed = taplist.diff(old, new)
    assert [d["name"] for d in added] == ["New Beer"] and [d["name"] for d in removed] == ["Old Beer"]


def test_blurb_is_the_first_sentence_of_the_description():
    page = "<p>Pickle Lager ABV 5% Available to go No It’s brine time. The best beer needs the best ingredients. Join our mailing list</p>"
    assert taplist.blurb(page) == "It’s brine time."
    assert taplist.blurb("<p>nothing here</p>") == ""


def _sync(d, monkeypatch, fetched, saved=None):
    async def fake(old=None):
        return fetched

    monkeypatch.setattr(taplist, "fetch_board", fake)
    monkeypatch.setattr("app.sim.director.settings.tap_sync", True)

    async def noop(*a, **k):
        pass

    monkeypatch.setattr("app.sim.director.set_state", noop)
    monkeypatch.setattr("app.sim.director.Session", lambda: _Null())
    asyncio.run(d.sync_board(saved))


class _Null:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        pass


def test_a_new_drink_is_released_and_a_gone_one_leaves_the_board(monkeypatch):
    d = _room()
    board = [dict(x) for x in menu.default_board()]
    gone, kept = board[0], board[1:]
    fresh = {"name": "Lantern Light", "kind": "beer", "style": "Amber Lager", "abv": 5.2, "thc_mg": None, "mainstay": False, "note": "toasty"}
    d.released = [{"name": gone["name"], "day": "2026-10-01"}]
    _sync(d, monkeypatch, kept + [fresh])
    day = d.clock.now().strftime("%Y-%m-%d")
    assert "Lantern Light" in menu.names() and gone["name"] not in menu.names()
    assert d.released == [{"name": "Lantern Light", "day": day}]  # a gone drink drops out of the releases
    assert d.gone == [gone["name"]] and "Lantern Light" in d.world_text and gone["name"] not in d.world_text
    assert any(h["kind"] == "board" for h in d.history)


def test_a_site_that_cannot_be_read_leaves_the_board_alone(monkeypatch):
    d = _room()
    saved = [dict(x) for x in menu.default_board()][:10]
    _sync(d, monkeypatch, None, saved)
    assert menu.names() == [x["name"] for x in saved] and d.gone == [] and d.released == []


def test_every_seeded_persona_drink_is_on_the_live_board():
    import yaml

    from app.seed.loader import HERE

    for f in ("patrons", "bartenders"):
        for r in yaml.safe_load((HERE / f"{f}.yaml").read_text()):
            if r["id"] != "b4":
                assert menu.match(r["drink"]), (r["id"], r["drink"])

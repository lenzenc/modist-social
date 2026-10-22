"""Parties that walk into the taproom together: how big, who they are, and how they split around the tables.

Pure functions, deterministic from their inputs, so tests need no director.
"""
import math
import random

from .state import MAX_GROUP, TABLE_SEATS

# Party size -> weight. Mostly two to four, and a party of eight is not that rare.
SIZES = {2: 30, 3: 22, 4: 20, 5: 7, 6: 8, 7: 4, 8: 9}
MAX_PARTY = max(SIZES)
KINDS = {"regulars": 40, "mixed": 35, "new": 25}  # who is in the party: regulars, a mix, or all new faces
GROUP_DAYS = [3, 4, 5, 6]  # Thu-Sun, when parties tend to come
GROUP_WINDOW = [16, 21]


def pick_size(rng: random.Random) -> int:
    return rng.choices(list(SIZES), list(SIZES.values()))[0]


def pick_kind(rng: random.Random) -> str:
    return rng.choices(list(KINDS), list(KINDS.values()))[0]


def tables_needed(size: int) -> int:
    return math.ceil(size / TABLE_SEATS)


def split(members: list[str]) -> list[list[str]]:
    """Even chunks of at most MAX_GROUP: 5 -> 3+2, 6 -> 3+3, 7 -> 4+3, 8 -> 4+4."""
    n = math.ceil(len(members) / MAX_GROUP)
    if n == 0:
        return []
    base, extra = divmod(len(members), n)
    out, i = [], 0
    for k in range(n):
        size = base + (1 if k < extra else 0)
        out.append(members[i:i + size])
        i += size
    return out

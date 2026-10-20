import random

# (weight, topic spark). Sparks are offered as optional nudges, not scripts.
TOPICS = [
    (22, "the beer in your hand, the tap list, or how brewing works (hops, yeast, water, a homebrew mishap)"),
    (12, "a local political or civic issue (the bike lanes, the zoning vote, potholes, parking, taxes)"),
    (14, "something happening around town: an event, a closing restaurant, the weather, the food truck"),
    (16, "a bit of gossip about someone you both know, or something you heard through the grapevine"),
    (10, "sports: last night's game, the standings, a fantasy league"),
    (14, "work, family, pets, or your week"),
    (6, "music, movies, books or something you watched recently"),
    (6, "a funny story from your own life"),
]


def pick_topic(rng: random.Random) -> str:
    return rng.choices([t for _, t in TOPICS], weights=[w for w, _ in TOPICS])[0]


STRANGER_OPENERS = [
    "small talk about the beer, the crowd, the weather, or the dog under the next table",
    "a friendly question about what the other person is drinking",
    "a comment on the game or the chalkboard",
]

"""Format templates: how many of each card category a good deck wants,
and what mana curve each archetype aims for.

These numbers encode standard Magic deckbuilding guidance (e.g. a Commander
deck wants ~10 ramp / ~10 draw / ~10 interaction / ~37 lands). The engine
fills toward these targets; it is the "logic" that shapes the deck.
"""

import re

# Category quotas per format. "theme" soaks up the remaining slots with
# on-flavor creatures / payoffs.
FORMAT_TEMPLATES = {
    "commander": {
        "deck_size": 100,
        "singleton": True,          # max 1 of any nonland card (and nonbasic land)
        "max_copies": 1,
        "commander": True,
        "categories": {             # target counts (excluding the commander)
            "lands": 36,
            "ramp": 10,
            "draw": 10,
            "removal": 8,
            "wipe": 3,
            "theme": 32,            # remainder -> on-theme creatures/synergy
        },
    },
    "standard": {                   # a 60-card Constructed deck
        "deck_size": 60,
        "singleton": False,
        "max_copies": 4,
        "commander": False,
        "categories": {
            "lands": 24,
            "ramp": 2,
            "draw": 3,
            "removal": 6,
            "wipe": 1,
            "theme": 24,
        },
    },
}

# Target share of nonland spells by converted mana cost, per archetype.
# Buckets: 1 = 0-1, 2 = 2, 3 = 3, 4 = 4, 5 = 5, 6 = 6+
CURVE_TARGETS = {
    "aggro":       {1: 0.34, 2: 0.30, 3: 0.20, 4: 0.10, 5: 0.04, 6: 0.02},
    "midrange":    {1: 0.14, 2: 0.24, 3: 0.24, 4: 0.18, 5: 0.12, 6: 0.08},
    "control":     {1: 0.12, 2: 0.20, 3: 0.20, 4: 0.18, 5: 0.16, 6: 0.14},
    "tokens":      {1: 0.18, 2: 0.28, 3: 0.24, 4: 0.16, 5: 0.08, 6: 0.06},
    "aristocrats": {1: 0.18, 2: 0.26, 3: 0.24, 4: 0.16, 5: 0.10, 6: 0.06},
    "ramp":        {1: 0.16, 2: 0.20, 3: 0.18, 4: 0.16, 5: 0.14, 6: 0.16},
    "spellslinger": {1: 0.22, 2: 0.26, 3: 0.22, 4: 0.16, 5: 0.08, 6: 0.06},
    "voltron":     {1: 0.20, 2: 0.28, 3: 0.24, 4: 0.16, 5: 0.08, 6: 0.04},
    "lifegain":    {1: 0.16, 2: 0.24, 3: 0.24, 4: 0.18, 5: 0.10, 6: 0.08},
}

# Wizards' Commander bracket system (October 2025 revision).
# Thresholds and restrictions per bracket level.
BRACKET_THRESHOLDS = {
    1: {
        "name": "Exhibition",
        "description": "Ultra-casual, themed, jank",
        "max_game_changers": 0,
        "allow_infinite_combos": False,
        "avg_mv_target": 2.5,
    },
    2: {
        "name": "Core",
        "description": "Precon level",
        "max_game_changers": 0,
        "allow_infinite_combos": False,
        "avg_mv_target": 3.0,
    },
    3: {
        "name": "Upgraded",
        "description": "Meaningfully tuned, still fair",
        "max_game_changers": 3,
        "allow_infinite_combos": False,  # late-game combos only, not enforced here
        "avg_mv_target": 3.2,
    },
    4: {
        "name": "Optimized",
        "description": "High power, short of cEDH",
        "max_game_changers": None,  # no restriction
        "allow_infinite_combos": True,
        "avg_mv_target": 3.5,
    },
    5: {
        "name": "cEDH",
        "description": "Tournament, metagame-tuned",
        "max_game_changers": None,  # no restriction
        "allow_infinite_combos": True,
        "avg_mv_target": 3.2,
    },
}


def curve_bucket(cmc: float) -> int:
    c = int(cmc)
    if c <= 1:
        return 1
    if c >= 6:
        return 6
    return c


def get_template(fmt: str) -> dict:
    return FORMAT_TEMPLATES.get(fmt, FORMAT_TEMPLATES["commander"])


def get_curve(archetype: str) -> dict:
    return CURVE_TARGETS.get(archetype, CURVE_TARGETS["midrange"])


def get_bracket_config(bracket: int | None) -> dict | None:
    """Get bracket thresholds for a given bracket level (1-5), or None if not specified."""
    if bracket is None or bracket not in BRACKET_THRESHOLDS:
        return None
    return BRACKET_THRESHOLDS[bracket]


def parse_bracket_from_description(description: str) -> int | None:
    """Try to extract bracket level from free-form description.
    
    Looks for patterns like:
    - "bracket 3" or "bracket3"
    - "cEDH" or "cedh" -> bracket 5
    - "optimized" -> bracket 4
    - "upgraded" or "tuned" -> bracket 3
    - "casual", "precon", "core", "beginner" -> bracket 2
    - "exhibition" -> bracket 1
    """
    import re
    low = description.lower()
    
    # Explicit bracket number (highest priority)
    match = re.search(r'\bbracket\s*([1-5])\b', low)
    if match:
        return int(match.group(1))
    
    # Named bracket levels (more specific before generic)
    if re.search(r'\b(cedh|c-edh|tournament)\b', low):
        return 5
    if re.search(r'\b(optimized|high power|high-power)\b', low):
        return 4
    if re.search(r'\b(upgraded|tuned)\b', low):
        return 3
    if re.search(r'\b(casual|precon|core|beginner)\b', low):
        return 2
    if re.search(r'\b(exhibition|jank|ultra-casual)\b', low):
        return 1
    
    return None

"""Theme interpreter: freeform description -> Magic deck parameters.

Given a natural-language theme ("a Red Rising rebellion deck") it derives a
colour identity (via the WUBRG colour pie), a strategic archetype, and Scryfall
search terms that capture the flavor of the theme. It reasons from Magic's own
colour philosophy rather than looking up a decklist someone else built. An
optional LLM pass (used only if an API key is set) can enrich the same output;
the heuristic runs regardless so the app always works offline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict

try:
    import requests
except ImportError:  # requests is optional for the pure-offline path
    requests = None

from .expand import expand_query

logger = logging.getLogger(__name__)

COLOR_CONCEPTS = {
    "W": ["order", "law", "justice", "peace", "protect", "protection", "hierarchy",
          "structure", "army", "soldier", "legion", "discipline", "duty", "honor",
          "angel", "heal", "unity", "society", "rule", "moral", "faith", "light",
          "noble", "knight", "civil", "authority", "tax"],
    "U": ["knowledge", "cunning", "intellect", "mind", "politic", "manipulat",
          "technology", "tech", "machine", "artifice", "illusion", "deceive",
          "spy", "strategy", "clever", "wisdom", "control", "scheme", "secret",
          "water", "sea", "storm", "invent", "logic", "information", "code",
          "hack", "science"],
    "B": ["ambition", "power", "death", "sacrifice", "ruthless", "corrupt",
          "greed", "selfish", "betray", "undead", "vampire", "demon", "disease",
          "decay", "shadow", "fear", "cruel", "torture", "blood",
          "amoral", "immoral", "necromanc", "plague", "gold", "wealth", "tyrant",
          "slave", "oppress", "murder"],
    "R": ["freedom", "rebel", "rebellion", "revolt", "revolution", "passion",
          "chaos", "war", "fire", "flame", "burn", "emotion", "impulse", "anger",
          "rage", "fury", "riot", "battle", "warrior", "destruction", "explos",
          "lightning", "speed", "aggress", "uprising", "liberty", "spark",
          "riotous", "wild", "haste"],
    "G": ["nature", "growth", "grow", "instinct", "primal", "beast", "forest",
          "wild", "survival", "strength", "tribe", "tribal", "harmony", "hunt",
          "predator", "elf", "druid", "earth", "root", "evolve",
          "ferocious", "pack", "herd", "green", "ramp", "big"],
}
COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
               "azorius": "WU", "dimir": "UB", "rakdos": "BR", "gruul": "RG",
               "selesnya": "GW", "orzhov": "WB", "izzet": "UR", "golgari": "BG",
               "boros": "RW", "simic": "GU", "mardu": "RWB", "jeskai": "URW",
               "abzan": "WBG", "sultai": "BGU", "temur": "GUR", "bant": "GWU",
               "esper": "WUB", "grixis": "UBR", "naya": "RGW", "jund": "BRG"}

ARCHETYPES = {
    "aggro": ["aggress", "fast", "rush", "war", "battle", "attack", "blitz",
              "assault", "haste", "burn", "aggro", "swarm", "charge", "raid"],
    "aristocrats": ["sacrifice", "death", "die", "martyr", "blood", "cult",
                    "undead", "necromanc", "reanimat", "grave", "drain"],
    "tokens": ["army", "legion", "swarm", "horde", "masses", "populace",
               "recruit", "rebellion", "uprising", "collective", "many"],
    "control": ["control", "politic", "manipulat", "patient", "counter", "deny",
                "lock", "prison", "tax", "stall", "grind", "attrition"],
    "ramp": ["nature", "growth", "big", "giant", "titan", "colossal", "primal",
             "ramp", "mana", "overwhelming"],
    "spellslinger": ["magic", "spell", "wizard", "arcane", "storm", "sorcery",
                     "cast", "pyromanc", "elemental"],
    "voltron": ["champion", "hero", "duel", "single", "warrior", "blade",
                "sword", "equip", "lone", "legendary"],
    "lifegain": ["heal", "life", "protect", "peace", "sanctuary", "restore"],
    "midrange": [],
}

# How the expansion module's MTG themes map onto strategy / colours / search
# terms. This is what lets a short prompt ("Iron Man") steer the whole build
# via its expanded themes (equipment, artifact, ...) instead of falling back
# to a generic mono-red deck.
THEME_ARCHETYPES = {
    "equipment": "voltron", "voltron": "voltron", "legendary": "voltron",
    "tokens": "tokens", "aggro": "aggro", "aristocrats": "aristocrats",
    "spellslinger": "spellslinger", "ramp": "ramp", "lifegain": "lifegain",
    "vehicle": "midrange", "artifact": "midrange", "tribal": "midrange",
}
THEME_COLOR_HINTS = {
    "equipment": "WR", "artifact": "WU", "vehicle": "WR", "tokens": "WG",
    "aristocrats": "B", "spellslinger": "UR", "tribal": "G", "ramp": "G",
    "aggro": "R", "flying": "WU", "voltron": "W", "legendary": "W",
    "lifegain": "W",
}
THEME_SEARCH_TERMS = {
    "equipment": ["equipment", "equip", "attach"],
    "artifact": ["artifact"],
    "vehicle": ["vehicle", "crew"],
    "tokens": ["create", "token"],
    "aristocrats": ["sacrifice", "dies"],
    "spellslinger": ["instant", "sorcery"],
    "aggro": ["haste"],
    "flying": ["flying"],
    "voltron": ["equip", "aura"],
    "lifegain": ["life"],
}

FLAVOR_TERMS = {
    "rebel": ["rebel", "revolt", "uprising", "riot"],
    "rebellion": ["rebel", "revolt", "uprising", "riot", "insurrect"],
    "revolt": ["revolt", "riot", "rebel"],
    "war": ["soldier", "warrior", "battle", "war", "legion"],
    "hierarchy": ["noble", "throne", "monarch", "royal", "command"],
    "sacrifice": ["sacrifice", "blood", "altar"],
    "sacrific": ["sacrifice", "blood", "altar"],
    "army": ["soldier", "token", "legion", "recruit", "muster"],
    "death": ["death", "dies", "grave", "perish"],
    "politic": ["vote", "monarch", "council", "influence"],
    "fire": ["flame", "burn", "fire", "lightning"],
    "nature": ["forest", "beast", "wild", "primal"],
    "tech": ["artifact", "construct", "assemble", "machine"],
    "vampire": ["vampire", "blood"],
    "zombie": ["zombie", "undead", "grave"],
    "dragon": ["dragon"],
    "angel": ["angel"],
    "demon": ["demon"],
    "elf": ["elf"],
    "goblin": ["goblin"],
    "knight": ["knight"],
    "wizard": ["wizard", "spell"],
}

CREATURE_TYPES = ["soldier", "warrior", "goblin", "elf", "zombie", "vampire",
                  "angel", "demon", "dragon", "knight", "wizard", "human",
                  "beast", "spirit", "merfolk", "elemental", "rogue", "cleric",
                  "cat", "dog", "dinosaur", "pirate", "ninja", "samurai",
                  "sliver", "hydra", "phoenix", "giant", "faerie", "kraken"]


@dataclass
class DeckParameters:
    description: str
    colors: list = field(default_factory=list)
    color_scores: dict = field(default_factory=dict)
    archetype: str = "midrange"
    oracle_terms: list = field(default_factory=list)
    creature_types: list = field(default_factory=list)
    set_names: list = field(default_factory=list)
    set_codes: list = field(default_factory=list)
    commander_name: str | None = None
    reference_cards: list = field(default_factory=list)
    reference_sources: list = field(default_factory=list)
    expansion: dict = field(default_factory=dict)
    reasoning: str = ""
    source: str = "heuristic"

    def as_dict(self):
        return asdict(self)


def _score_colors(text):
    scores = {c: 0.0 for c in "WUBRG"}
    low = text.lower()
    for name, letters in COLOR_NAMES.items():
        if re.search(r"\b" + name + r"\b", low):
            weight = 4.0 if len(letters) > 1 else 3.0
            for L in letters:
                scores[L] += weight
    for color, words in COLOR_CONCEPTS.items():
        for w in words:
            if w in low:
                scores[color] += 1.0
    return scores


def _pick_colors(scores, max_colors=3):
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ranked = [(c, s) for c, s in ranked if s > 0]
    if not ranked:
        return ["R"]
    top = ranked[0][1]
    chosen = [c for c, s in ranked if s >= max(1.0, top * 0.4)][:max_colors]
    return chosen or [ranked[0][0]]


def _pick_archetype(text, colors, themes=None):
    low = text.lower()
    best, best_score = "midrange", 0
    for arch, words in ARCHETYPES.items():
        score = sum(1 for w in words if w in low)
        if score > best_score:
            best, best_score = arch, score
    if best_score == 0:
        # No keyword signal in the text: let the expanded MTG themes decide
        # before falling back to a colour-based default.
        for theme in themes or []:
            if theme in THEME_ARCHETYPES:
                return THEME_ARCHETYPES[theme]
        if "R" in colors:
            return "aggro"
        if "U" in colors and "W" in colors:
            return "control"
        if "B" in colors:
            return "aristocrats"
        if "G" in colors:
            return "ramp"
    return best


SET_ALIASES = {
    "modern horizons 3": "mh3",
    "modern horizons 2": "mh2",
    "modern horizons": "mh3",
    "dominaria united": "dmu",
    "foundations": "fdn",
    "war of the spark": "war",
    "march of the machine": "mom",
    "the lost caverns of ixalan": "ltc",
    "phrexia: all will be one": "one",
    "phrexia all will be one": "one",
    "bloomburrow": "blb",
    "the brothers' war": "bro",
    "wilds of eldraine": "woe",
}


def _extract_reference_cards(text_or_items) -> list[str]:
    if text_or_items is None:
        return []
    if isinstance(text_or_items, str):
        items = [text_or_items]
    elif isinstance(text_or_items, (list, tuple, set)):
        items = list(text_or_items)
    else:
        items = [str(text_or_items)]

    cards: list[str] = []
    for item in items:
        if not item:
            continue
        text = str(item).strip()
        if not text:
            continue
        if re.match(r"^https?://", text, re.I):
            if not ("moxfield" in text.lower() or "archidekt" in text.lower()):
                continue
            if requests is None:
                continue
            try:
                resp = requests.get(text, timeout=10)
                resp.raise_for_status()
                html = resp.text or ""
            except Exception:
                continue
            for pattern in [
                r"(?i)(?:data-name|name)=['\"]([^'\"]+)['\"]",
                r"(?i)(?:card-name|title)[^>]*>([^<]+)<",
            ]:
                for match in re.finditer(pattern, html):
                    candidate = re.sub(r"\s+", " ", match.group(1)).strip().strip("•-*\"'")
                    if candidate and len(candidate.split()) <= 5 and candidate.lower() not in {"deck", "decklist", "moxfield", "archidekt", "view"}:
                        cards.append(candidate)
            continue
        for chunk in re.split(r"[\n,;]+", text):
            chunk = chunk.strip().strip("•-*\"'")
            if not chunk:
                continue
            chunk = re.sub(r"^(?:\d+|[xX]?)\s*", "", chunk)
            chunk = re.sub(r"^(?:\d+\s*[xX]\s*)", "", chunk)
            chunk = chunk.strip().strip(" .,:;")
            low = chunk.lower()
            if not chunk or any(skip in low for skip in ["moxfield", "archidekt", "deck", "decklist", "build", "use", "my", "the", "commander", "reference"]):
                continue
            cards.append(chunk)
    seen = []
    for card in cards:
        if card not in seen:
            seen.append(card)
    return seen


def _extract_reference_sources(text_or_items) -> list[str]:
    if text_or_items is None:
        return []
    if isinstance(text_or_items, str):
        items = [text_or_items]
    elif isinstance(text_or_items, (list, tuple, set)):
        items = list(text_or_items)
    else:
        items = [str(text_or_items)]

    sources = []
    for item in items:
        if not item:
            continue
        text = str(item).strip()
        if re.match(r"^https?://", text, re.I) and ("moxfield" in text.lower() or "archidekt" in text.lower()):
            sources.append(text)
    return sources


def _extract_commander_name(text: str) -> str | None:
    patterns = [
        re.compile(r"\buse\s+(.+?)\s+as\s+(?:my|the)\s+commander\b", re.I),
        re.compile(r"\b(?:my|the)\s+commander\s+is\s+(.+?)(?:[.?!,]|$)", re.I),
        re.compile(r"\bcommander\s*[:\-]\s*(.+?)(?:[.?!,]|$)", re.I),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            name = match.group(1).strip().strip('"\'')
            return name or None
    return None


def _extract_set_hints(text):
    low = text.lower()
    hints = []
    for alias in SET_ALIASES:
        if alias in low:
            hints.append(alias)
    for pattern in [r"\bfrom\s+([a-z0-9'&\- ]+)", r"\busing\s+([a-z0-9'&\- ]+)", r"\bset\s+([a-z0-9'&\- ]+)"]:
        for match in re.finditer(pattern, low):
            candidate = match.group(1).strip()
            if candidate and len(candidate.split()) <= 5 and candidate not in hints:
                hints.append(candidate)
    return hints[:3]


def _resolve_set_codes(set_names):
    if not set_names:
        return []
    try:
        from .scryfall import ScryfallClient
        client = ScryfallClient(offline=False)
        codes = []
        for name in set_names:
            code = client.resolve_set_code(name)
            if code and code not in codes:
                codes.append(code)
        return codes
    except Exception:
        return []


def _derive_oracle_terms(text):
    low = text.lower()
    terms = []
    for key, expanded in FLAVOR_TERMS.items():
        if key in low:
            terms.extend(expanded)
    for ct in CREATURE_TYPES:
        if ct in low:
            terms.append(ct)
    seen = []
    for t in terms:
        if t not in seen:
            seen.append(t)
    return seen[:8]


def _reason(desc, colors, archetype, terms, set_names, expansion, reference_cards=None):
    cnames = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    cl = ", ".join(cnames[c] for c in colors)
    t = ", ".join(terms) if terms else "general good-stuff for the colours"
    set_note = "" if not set_names else (" Set focus: " + ", ".join(set_names) + ".")
    expansion_note = "" if not expansion.get("concepts") else (" Expanded concepts: " + ", ".join(expansion["concepts"][:8]) + ".")
    ref_note = "" if not reference_cards else (" Reference cards: " + ", ".join(reference_cards[:6]) + ".")
    return ("Mapped the theme onto Magic's colour pie -> " + cl + ". "
            "Best-fit strategy: **" + archetype + "**. "
            "Flavor search terms: " + t + "." + set_note + expansion_note + ref_note + " "
            "Cards are assembled with deckbuilding math (curve, ratios, "
            "legality), not copied from any existing list.")


def interpret(description, use_llm=True, references=None):
    """Main entry point: description -> DeckParameters."""
    # Expand the prompt FIRST: short prompts like "Iron Man" carry no colour /
    # archetype keywords themselves — the expanded concepts and themes do.
    expansion = expand_query(description, use_llm=use_llm)
    set_names = _extract_set_hints(description)
    set_codes = _resolve_set_codes(set_names)
    commander_name = _extract_commander_name(description)
    reference_cards = _extract_reference_cards(references) if references is not None else []
    reference_sources = _extract_reference_sources(references) if references is not None else []

    if use_llm:
        llm_params = _try_llm(description)
        if llm_params is not None:
            # Keep the semantic expansion — the engine uses it to build the
            # theme card pool. Previously the LLM path dropped it entirely.
            llm_params.expansion = expansion
            llm_params.set_names = set_names
            llm_params.set_codes = set_codes
            llm_params.commander_name = commander_name
            llm_params.reference_cards = reference_cards
            llm_params.reference_sources = reference_sources
            return llm_params
        if os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("LLM interpretation failed for %r; using heuristics. "
                           "Check the API key/model and see earlier warnings.",
                           description)

    themes = [t for t in expansion.get("mtg_themes", []) if t]
    enriched = " ".join([description] + expansion.get("concepts", []) + themes)

    scores = _score_colors(enriched)
    for theme in themes:
        for c in THEME_COLOR_HINTS.get(theme, ""):
            scores[c] += 1.5
    colors = _pick_colors(scores)
    archetype = _pick_archetype(enriched, colors, themes)

    terms = _derive_oracle_terms(enriched)
    for theme in themes:
        for t in THEME_SEARCH_TERMS.get(theme, []):
            if t not in terms:
                terms.append(t)
    terms = terms[:10]

    ctypes = [ct for ct in CREATURE_TYPES if ct in enriched.lower()]
    return DeckParameters(
        description=description,
        colors=colors,
        color_scores={k: round(v, 1) for k, v in scores.items()},
        archetype=archetype,
        oracle_terms=terms,
        creature_types=ctypes,
        set_names=set_names,
        set_codes=set_codes,
        commander_name=commander_name,
        reference_cards=reference_cards,
        reference_sources=reference_sources,
        expansion=expansion,
        reasoning=_reason(description, colors, archetype, terms, set_names, expansion, reference_cards),
        source="heuristic",
    )


def _try_llm(description):
    """Optional Anthropic enrichment. Silently no-ops without an API key."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import requests
        prompt = ("You are a Magic: The Gathering deckbuilding expert. Given a "
                  "theme, output ONLY JSON with keys: colors (array of "
                  "W/U/B/R/G), archetype (one of aggro, midrange, control, "
                  "tokens, aristocrats, ramp, spellslinger, voltron, lifegain), "
                  "oracle_terms (array of up to 8 lowercase words to search card "
                  "text for on-theme cards), creature_types (array), reasoning "
                  "(2 sentences). Reason from the colour pie; do not copy any "
                  "existing decklist. Theme: " + description)
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                  "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            logger.warning("LLM returned no JSON object for %r: %.200s", description, text)
            return None
        data = json.loads(match.group(0))
        return DeckParameters(
            description=description,
            colors=[c for c in data.get("colors", []) if c in "WUBRG"] or ["R"],
            color_scores={},
            archetype=data.get("archetype", "midrange"),
            oracle_terms=data.get("oracle_terms", [])[:8],
            creature_types=data.get("creature_types", []),
            reasoning="(LLM) " + data.get("reasoning", ""),
            source="llm",
        )
    except Exception as exc:
        logger.warning("LLM interpretation error for %r: %s: %s",
                       description, type(exc).__name__, exc)
        return None

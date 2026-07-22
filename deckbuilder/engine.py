"""Deckbuilding engine — assemble a legal, coherent deck from a card pool.

Pipeline:
    interpret theme  ->  DeckParameters
    gather candidate pools per category from card index (or live Scryfall API)
    score every candidate (theme relevance + role fit + curve fit + playability)
    greedily fill category quotas, enforcing singleton / copy limits / colours
    compute the land base from the actual colour requirements of the spells
    emit the deck + statistics + human-readable reasoning

The deck is *derived* here — no external decklist is read or reproduced.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .formats import get_template, get_curve, curve_bucket, get_bracket_config, BRACKET_THRESHOLDS
from .theme import DeckParameters
from .scryfall import ScryfallClient
from .reranker import get_reranker

BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp",
                   "R": "Mountain", "G": "Forest"}


class CardIndexUnavailableError(Exception):
    """Raised when the card index cannot be accessed."""
    pass


def _resolve_format(description: str, fmt: str = "commander",
                    deck_type_hint: str | None = None) -> str:
    hint = (deck_type_hint or "").strip().lower()
    text = (description or "").lower()

    if hint in {"60-card", "60 card", "standard", "constructed", "60", "sixty"}:
        return "standard"
    if hint in {"100-card", "100 card", "commander", "edh", "singleton", "100"}:
        return "commander"

    if re.search(r"\b(60|sixty)\s*-?\s*(card|cards)\b", text):
        return "standard"
    if re.search(r"\b(100|one hundred)\s*-?\s*(card|cards)\b", text) or any(k in text for k in ["commander", "edh", "singleton"]):
        return "commander"

    return fmt if fmt in {"commander", "standard"} else "commander"


def _pip_counts(mana_cost: str) -> Counter:
    """Count coloured mana pips in a mana cost string like '{2}{B}{R}'."""
    return Counter(re.findall(r"\{([WUBRG])\}", mana_cost or ""))


class DeckValidator:
    """Validates a completed deck against hard format constraints."""
    
    def __init__(self, fmt: str, enforce_ban_list: bool = True):
        self.fmt = fmt
        self.enforce_ban_list = enforce_ban_list
        self.template = get_template(fmt)
        self.errors = []
        self.warnings = []
    
    def validate(self, deck: dict, commander: dict | None = None) -> bool:
        """Validate a complete deck. Returns True if valid, False otherwise.
        
        Checks:
        - Exact card count
        - Singleton constraints (Commander)
        - Copy limits (Standard)
        - Color identity restrictions
        - Legality
        - Ban list status
        """
        self.errors = []
        self.warnings = []
        
        all_cards = deck
        land_count = sum(1 for c in deck if c.get("is_land", False))
        nonland_count = len(deck) - land_count
        
        if commander:
            # Commander deck: exactly 100 including commander
            if len(all_cards) != 100:
                self.errors.append(f"Deck has {len(all_cards)} cards, must be exactly 100")
                return False
            
            # Color identity check
            cmd_identity = set(commander.get("color_identity", []))
            for card in all_cards:
                card_identity = set(card.get("color_identity", []))
                if not card_identity.issubset(cmd_identity):
                    self.errors.append(
                        f"{card['name']} has color identity {card_identity} outside commander's {cmd_identity}"
                    )
                    return False
            
            # Legality check
            for card in all_cards:
                legality = card.get("legalities", {}).get("commander")
                if legality == "not_legal":
                    self.errors.append(f"{card['name']} is not legal in Commander format")
                    return False
                if legality == "banned" and self.enforce_ban_list:
                    self.errors.append(f"{card['name']} is banned in Commander (enforce_ban_list=True)")
                    return False
            
            # Singleton check (max 1 copy of nonland, any number of basics)
            counts = Counter()
            for card in all_cards:
                if not (card.get("is_land") and "Basic" in card.get("type_line", "")):
                    counts[card["name"]] += 1
            
            for name, count in counts.items():
                if count > 1:
                    self.errors.append(f"{name} appears {count} times (singleton format allows 1 copy)")
                    return False
        
        else:
            # Standard deck: exactly 60
            if len(all_cards) != 60:
                self.errors.append(f"Deck has {len(all_cards)} cards, must be exactly 60")
                return False
            
            # Legality check
            for card in all_cards:
                legality = card.get("legalities", {}).get("standard")
                if legality == "not_legal":
                    self.errors.append(f"{card['name']} is not legal in Standard format")
                    return False
                if legality == "banned" and self.enforce_ban_list:
                    self.errors.append(f"{card['name']} is banned in Standard (enforce_ban_list=True)")
                    return False
            
            # Copy limit check (max 4 of nonland, any number of basics)
            counts = Counter()
            for card in all_cards:
                if not (card.get("is_land") and "Basic" in card.get("type_line", "")):
                    counts[card["name"]] += 1
            
            for name, count in counts.items():
                if count > 4:
                    self.errors.append(f"{name} appears {count} times (max 4 copies allowed)")
                    return False
        
        return True
    
    def get_errors(self) -> list[str]:
        return self.errors
    
    def get_warnings(self) -> list[str]:
        return self.warnings


class DeckBuilder:
    def __init__(self, client: ScryfallClient | None = None, fmt: str = "commander",
                 db_conn: sqlite3.Connection | None = None, bracket: int | None = None,
                 enforce_ban_list: bool = True, use_llm_reranking: bool = True,
                 llm_model: str | None = None):
        self.client = client or ScryfallClient()
        self.fmt = fmt
        self.db_conn = db_conn
        self.bracket = bracket
        self.enforce_ban_list = enforce_ban_list
        self.use_llm_reranking = use_llm_reranking
        self.reranker = get_reranker(model=llm_model) if use_llm_reranking else None
        self.template = get_template(fmt)
        self.validator = DeckValidator(fmt, enforce_ban_list)

    # ---------------------------------------------------------------- scoring
    def _theme_score(self, card: dict, terms: list[str], creature_types: list[str] | None = None) -> float:
        if not terms and not creature_types:
            return 0.0
        hay = (card["oracle_text"] + " " + card["name"] + " " + card["type_line"] + " " +
               " ".join(card["keywords"])).lower()
        score = 0.0
        for t in terms or []:
            if not t:
                continue
            if t in card["name"].lower():
                score += 2.5
            elif t in card["type_line"].lower():
                score += 1.5
            elif t in hay:
                score += 1.0
        for t in creature_types or []:
            if not t:
                continue
            if t in card["name"].lower() or t in card["type_line"].lower():
                score += 1.2
        return score

    def _playability(self, card: dict) -> float:
        # edhrec_rank: lower = more played. Convert to a small positive score.
        rank = card.get("edhrec_rank") or 10 ** 9
        return max(0.0, 3.0 - (rank / 8000.0))

    def _reference_score(self, card: dict, reference_cards: list[str] | None = None) -> float:
        if not reference_cards:
            return 0.0
        name = (card.get("name") or "").lower()
        type_line = (card.get("type_line") or "").lower()
        oracle = (card.get("oracle_text") or "").lower()
        score = 0.0
        for ref in reference_cards:
            if not ref:
                continue
            ref_low = ref.lower()
            if ref_low in name:
                score += 2.2
            elif ref_low in type_line or ref_low in oracle:
                score += 0.7
        return score

    def _normalize_card(self, card: dict | None) -> dict | None:
        if not card:
            return None
        if "is_land" in card and "is_creature" in card and "types" in card:
            return card
        type_line = card.get("type_line") or ""
        oracle = card.get("oracle_text") or ""
        return {
            **card,
            "name": card.get("name") or "Unknown",
            "mana_cost": card.get("mana_cost") or "",
            "cmc": card.get("cmc") or 0,
            "color_identity": card.get("color_identity") or [],
            "colors": card.get("colors") or [],
            "type_line": type_line,
            "oracle_text": oracle,
            "image": card.get("image") or None,
            "roles": card.get("roles") or [],
            "keywords": card.get("keywords") or [],
            "is_land": "land" in type_line.lower(),
            "is_creature": "creature" in type_line.lower(),
            "types": [t for t in re.findall(r"[A-Za-z]+", type_line.split("—")[0]) if t not in ("Legendary", "Basic", "Snow", "World")],
            "legalities": card.get("legalities") or {},
            "scryfall_uri": card.get("scryfall_uri") or "",
            "power": card.get("power"),
            "toughness": card.get("toughness"),
            "edhrec_rank": card.get("edhrec_rank") or 10 ** 9,
        }

    def _is_commander_candidate(self, card: dict | None) -> bool:
        card = self._normalize_card(card)
        if not card:
            return False
        type_line = (card.get("type_line") or "").lower()
        oracle = (card.get("oracle_text") or "").lower()
        if "legendary" not in type_line:
            return False
        if "creature" not in type_line and "can be your commander" not in oracle:
            return False
        legality = (card.get("legalities") or {}).get("commander")
        return legality in {"legal", None}

    def _curve_fit(self, card: dict, have: Counter, target: dict, budget: int) -> float:
        if budget <= 0:
            return 0.0
        b = curve_bucket(card["cmc"])
        want = target.get(b, 0.1) * budget
        cur = have.get(b, 0)
        return 1.2 if cur < want else -0.4  # reward under-filled buckets

    def _search_terms(self, params: DeckParameters) -> list[str]:
        """Oracle search terms: explicit flavor terms + expanded MTG themes."""
        expansion_terms = [t for t in (params.expansion or {}).get("mtg_themes", []) if t]
        terms = []
        for t in list(params.oracle_terms or []) + expansion_terms:
            if t and t not in terms:
                terms.append(t)
        return terms

    def _should_filter_game_changers(self) -> bool:
        """Check if this bracket requires filtering Game Changers."""
        if self.bracket is None:
            return False
        cfg = get_bracket_config(self.bracket)
        return cfg and cfg["max_game_changers"] == 0

    def _get_max_game_changers(self) -> int | None:
        """Get max Game Changers for this bracket, or None if no limit."""
        if self.bracket is None:
            return None
        cfg = get_bracket_config(self.bracket)
        return cfg["max_game_changers"] if cfg else None

    def _can_include_banned_card(self, card: dict) -> bool:
        """Check if a card with banned status can be included."""
        legality = card.get("legalities", {}).get("commander" if self.fmt == "commander" else "standard")
        if legality == "banned":
            return not self.enforce_ban_list
        return True

    def _get_bad_legality_card(self, card: dict) -> bool:
        """Check if a card has not_legal status (never allowed)."""
        legality = card.get("legalities", {}).get("commander" if self.fmt == "commander" else "standard")
        return legality == "not_legal"

    def _filter_pools_for_bracket(self, pools: dict, params: DeckParameters) -> dict:
        """Filter card pools based on bracket restrictions."""
        if self.bracket is None:
            return pools
        
        cfg = get_bracket_config(self.bracket)
        if not cfg:
            return pools
        
        max_game_changers = cfg.get("max_game_changers")
        
        # Filter each pool
        filtered_pools = {}
        for pool_name, cards in pools.items():
            filtered = []
            for card in cards:
                # Never allow not_legal cards
                if self._get_bad_legality_card(card):
                    continue
                
                # Check ban list (unless enforce_ban_list is False)
                legality = card.get("legalities", {}).get(
                    "commander" if self.fmt == "commander" else "standard")
                if legality == "banned" and self.enforce_ban_list:
                    continue
                
                # Filter Game Changers for brackets that don't allow them
                if max_game_changers == 0 and card.get("game_changer", False):
                    continue
                
                filtered.append(card)
            
            filtered_pools[pool_name] = filtered
        
        return filtered_pools

    # ------------------------------------------------------------- candidate pools
    def _gather(self, params: DeckParameters):
        ci = params.colors
        
        # If we have a database connection, use the card index
        if self.db_conn:
            return self._gather_from_index(params)
        
        # Otherwise fall back to the live API
        creature_terms = list(params.creature_types or [])
        set_codes = list(params.set_codes or [])
        expansion_terms = [t for t in (params.expansion or {}).get("mtg_themes", []) if t]
        search_terms = []
        for t in self._search_terms(params) + creature_terms:
            if t and t not in search_terms:
                search_terms.append(t)
        name_terms = [t for t in creature_terms + expansion_terms if t] or None
        fmt_legal = "commander" if self.fmt == "commander" else "standard"
        pools = {}
        pools["ramp"] = self.client.find_cards(
            ci, oracle_terms=["add {", "search your library for a", "mana"],
            exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["draw"] = self.client.find_cards(
            ci, oracle_terms=["draw a card", "draw two cards", "draw cards"],
            exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["removal"] = self.client.find_cards(
            ci, oracle_terms=["destroy target", "exile target", "damage to any target",
                              "counter target"],
            exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["wipe"] = self.client.find_cards(
            ci, oracle_terms=["destroy all", "exile all", "each creature",
                              "damage to each creature"],
            exclude_types=["Land"], fmt=fmt_legal, limit=40, set_codes=set_codes)
        # Theme pool: on-flavor cards. If we have flavor terms, search them;
        # otherwise pull strong creatures in the colours.
        pools["theme"] = self.client.find_cards(
            ci, card_type="Creature", oracle_terms=search_terms or None,
            name_terms=name_terms, fmt=fmt_legal, limit=120, set_codes=set_codes)
        if len(pools["theme"]) < 20:  # widen if the theme was too narrow
            pools["theme"] += self.client.find_cards(
                ci, card_type="Creature", name_terms=name_terms, fmt=fmt_legal, limit=120,
                set_codes=set_codes)
        return pools

    def _gather_from_index(self, params: DeckParameters) -> dict:
        """Gather candidate pools from the card index."""
        from . import carddata
        
        fmt_name = "commander" if self.fmt == "commander" else "standard"
        ci_str = "".join(params.colors) if params.colors else "WUBRG"
        
        pools = {}
        
        # Ramp pool: search for ramp keywords
        pools["ramp"] = carddata.search(
            self.db_conn, "ramp mana land search", fmt=fmt_name)[:60]
        pools["ramp"] = [c for c in pools["ramp"] if "land" not in c["type_line"].lower()]
        
        # Draw pool
        pools["draw"] = carddata.search(
            self.db_conn, "draw card", fmt=fmt_name)[:60]
        pools["draw"] = [c for c in pools["draw"] if "land" not in c["type_line"].lower()]
        
        # Removal pool
        pools["removal"] = carddata.search(
            self.db_conn, "destroy exile target damage counter", fmt=fmt_name)[:60]
        pools["removal"] = [c for c in pools["removal"] if "land" not in c["type_line"].lower()]
        
        # Wipe pool
        pools["wipe"] = carddata.search(
            self.db_conn, "destroy all each creature board wipe", fmt=fmt_name)[:40]
        pools["wipe"] = [c for c in pools["wipe"] if "land" not in c["type_line"].lower()]
        
        # Theme pool: search for creature types + oracle terms
        oracle_terms = self._search_terms(params)
        theme_query = " ".join(oracle_terms[:3]) if oracle_terms else ""
        if theme_query:
            pools["theme"] = carddata.search(
                self.db_conn, theme_query, fmt=fmt_name)[:120]
        else:
            # If no oracle terms, just search for creatures
            pools["theme"] = []
        
        # Filter all pools by color identity
        for pool_name in pools:
            pools[pool_name] = [
                self._normalize_card(c) for c in pools[pool_name]
                if isinstance(c, dict) and set(c.get("color_identity", [])).issubset(set(params.colors))
            ]
        
        return pools

    # --------------------------------------------------------------- assembly
    def build(self, params: DeckParameters) -> dict:
        template = self.template
        cats = template["categories"]
        max_copies = template["max_copies"]
        curve = get_curve(params.archetype)
        deck_size = template["deck_size"]
        target_land_count = cats["lands"]
        
        # For Standard, if no bracket specified, default to 2 or 3
        if self.bracket is None and self.fmt == "standard":
            self.bracket = 2  # default to Core/Precon level
            
        warnings: list[str] = []
        if self.bracket is not None:
            bracket_cfg = get_bracket_config(self.bracket)
            warnings.append(f"Building for bracket {self.bracket} ({bracket_cfg['name']}): {bracket_cfg['description']}")
        
        pools = self._gather(params)
        
        # Part 2: LLM Re-ranking of candidates (optional, degrades gracefully)
        reranking_used = False
        if self.reranker:
            reranked_pools = self.reranker.rerank_candidates(
                theme=params.reasoning or description,
                archetype=params.archetype,
                candidates=pools
            )
            if reranked_pools:
                pools = reranked_pools
                reranking_used = True
                warnings.append(f"Re-ranked candidates using LLM ({self.reranker.model})")
        
        # Filter pools based on bracket and ban list
        pools = self._filter_pools_for_bracket(pools, params)
        
        # Terms used to *rank* candidates
        rank_terms = self._search_terms(params)

        deck: list[dict] = []
        counts: Counter = Counter()          # name -> copies
        curve_have: Counter = Counter()
        used_names: set[str] = set()
        by_category: dict[str, list[dict]] = defaultdict(list)
        banned_cards_included: list[str] = []  # Track banned cards if allowed
        game_changer_count = 0

        # Commander first
        commander = None
        if template.get("commander") and params.commander_name:
            commander = self.client.resolve_named_commander(params.commander_name,
                                                             fmt=self.fmt,
                                                             set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander and self._is_commander_candidate(commander):
                # HARD FILTER: commander's color_identity must CONTAIN all requested colors
                commander_colors = set(commander.get("color_identity", []))
                requested_colors = set(params.colors)
                if requested_colors.issubset(commander_colors):
                    # Named commander contains all requested colors - use it
                    warnings.append(f"Using named commander {commander['name']} (colors: {commander_colors}) which contains requested colors {requested_colors}.")
                    used_names.add(commander["name"])
                else:
                    # Commander missing at least one requested color - hard reject
                    missing = requested_colors - commander_colors
                    warnings.append(f"Commander {commander['name']} is missing color(s) {missing} from requested {requested_colors}; cannot use.")
                    commander = None
            else:
                warnings.append(f"Could not resolve '{params.commander_name}' as a commander-legal card.")
                commander = None

        if template.get("commander") and not commander:
            commander = self.client.find_commander(params.colors, rank_terms,
                                                   set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander:
                used_names.add(commander["name"])
                commander_colors = set(commander.get("color_identity", []))
                warnings.append(f"Selected commander {commander['name']} with colors {commander_colors}.")
            else:
                # No legal commander found that contains all requested colors
                requested = "/".join(params.colors or [])
                warnings.append(f"⚠ No legal commander found containing all colors {requested}. Building deck without commander.")

        nonland_target = deck_size - target_land_count - (1 if commander else 0)

        # Fill categories
        order = ["ramp", "draw", "removal", "wipe", "theme"]
        for cat in order:
            quota = cats[cat]
            pool = pools.get(cat, [])
            # Rank the pool for this category.
            # Part 1: Prefer instant-speed interaction in removal/wipe pools
            def _score_card(c):
                base_score = (
                    self._theme_score(c, rank_terms, params.creature_types) * 1.5
                    + self._reference_score(c, params.reference_cards)
                    + self._playability(c)
                )
                # Bonus for instant-speed removal/wipes (instant is strictly better than sorcery)
                if cat in ("removal", "wipe") and c.get("is_instant"):
                    base_score += 0.5
                return base_score
            
            ranked = sorted(pool, key=_score_card, reverse=True)
            added = 0
            for card in ranked:
                if added >= quota:
                    break
                name = card["name"]
                if card["is_land"]:
                    continue
                if name in used_names and max_copies == 1:
                    continue
                if counts[name] >= max_copies:
                    continue
                if not set(card["color_identity"]).issubset(set(params.colors)):
                    continue
                
                # Track if this is a banned card (but allowed by toggle)
                if not self.enforce_ban_list and card.get("legalities", {}).get(
                    "commander" if self.fmt == "commander" else "standard") == "banned":
                    if name not in banned_cards_included:
                        banned_cards_included.append(name)
                
                # Track Game Changers for bracket classification
                if card.get("game_changer", False):
                    game_changer_count += 1
                
                fit = self._curve_fit(card, curve_have, curve, nonland_target)
                if cat == "theme" and fit < 0 and added > quota * 0.5:
                    continue
                
                copies = 1 if max_copies == 1 else min(max_copies, quota - added)
                for _ in range(copies):
                    deck.append(card)
                    curve_have[curve_bucket(card["cmc"])] += 1
                by_category[cat].append(card)
                counts[name] += copies
                used_names.add(name)
                added += copies

        # ---- Land base computation
        pip_total = Counter()
        for c in deck:
            pip_total.update(_pip_counts(c["mana_cost"]))
        
        # Compute adaptive land count (later step if needed)
        lands = self._build_lands(params.colors, pip_total, target_land_count)

        # ---- Backfill to exact deck size
        current_nonland = len(deck)
        target_nonland = nonland_target
        
        if current_nonland < target_nonland:
            # Need to add more cards
            filler = pools["theme"] + pools["ramp"] + pools["draw"] + pools.get("removal", [])
            for card in filler:
                if len(deck) >= target_nonland:
                    break
                name = card["name"]
                if card["is_land"] or name in used_names:
                    continue
                if not set(card["color_identity"]).issubset(set(params.colors)):
                    continue
                
                # Track banned cards
                if not self.enforce_ban_list and card.get("legalities", {}).get(
                    "commander" if self.fmt == "commander" else "standard") == "banned":
                    if name not in banned_cards_included:
                        banned_cards_included.append(name)
                
                # Track Game Changers
                if card.get("game_changer", False):
                    game_changer_count += 1
                
                deck.append(card)
                by_category["theme"].append(card)
                counts[name] += 1
                used_names.add(name)
        
        elif current_nonland > target_nonland:
            # Too many cards - trim from theme (least important category)
            theme_cards = by_category.get("theme", [])
            while len(deck) > target_nonland and theme_cards:
                card_to_remove = theme_cards.pop()
                deck.remove(card_to_remove)
                counts[card_to_remove["name"]] -= 1
                if counts[card_to_remove["name"]] == 0:
                    del counts[card_to_remove["name"]]

        # ---- Validation
        all_cards = ([commander] if commander else []) + deck + lands
        validation_ok = self.validator.validate(all_cards, commander)
        
        if not validation_ok:
            errors = self.validator.get_errors()
            warnings.extend([f"VALIDATION ERROR: {e}" for e in errors])

        return self._finalize(params, commander, deck, by_category, lands, counts, warnings,
                             banned_cards=banned_cards_included, game_changer_count=game_changer_count,
                             reranking_used=reranking_used)

    def _build_lands(self, colors, pip_total, land_count):
        colors = colors or ["R"]
        total_pips = sum(pip_total.get(c, 0) for c in colors) or len(colors)
        lands = []
        # weight basics by colour demand; guarantee at least 2 of each colour used
        alloc = {}
        remaining = land_count
        for c in colors:
            share = pip_total.get(c, 0) / total_pips if total_pips else 1 / len(colors)
            n = max(2, round(share * land_count))
            alloc[c] = n
        # normalize to exactly land_count
        diff = land_count - sum(alloc.values())
        keys = list(alloc.keys())
        i = 0
        while diff != 0 and keys:
            k = keys[i % len(keys)]
            if diff > 0:
                alloc[k] += 1
                diff -= 1
            elif alloc[k] > 1:
                alloc[k] -= 1
                diff += 1
            i += 1
        for c, n in alloc.items():
            basic = BASIC_FOR_COLOR[c]
            for _ in range(n):
                lands.append({
                    "name": basic, "cmc": 0, "mana_cost": "", "type_line": f"Basic Land — {basic}",
                    "color_identity": [], "colors": [], "oracle_text": f"{{T}}: Add {{{c}}}.",
                    "roles": ["land"], "is_land": True, "is_creature": False,
                    "keywords": [], "image": None, "edhrec_rank": 0, "types": ["Land"],
                    "supertypes": ["Basic"], "produced_mana": [c], "scryfall_uri": "",
                    "power": None, "toughness": None, "legalities": {},
                })
        return lands

    # --------------------------------------------------------------- output
    def _finalize(self, params, commander, deck, by_category, lands, counts, warnings=None,
                  banned_cards=None, game_changer_count=0, reranking_used=False):
        all_cards = ([commander] if commander else []) + deck + lands
        nonland = [c for c in all_cards if not c["is_land"]]
        curve_hist = Counter(curve_bucket(c["cmc"]) for c in nonland)
        type_hist = Counter()
        for c in nonland:
            main = (c["types"][0] if c["types"] else "Other")
            type_hist[main] += 1
        
        # Detailed card type tracking (Part 1 - Card Type Balance)
        card_type_counts = {
            "instant": 0,
            "sorcery": 0,
            "artifact": 0,
            "enchantment": 0,
            "planeswalker": 0,
            "battle": 0,
            "creature": 0,
        }
        interaction_types = {
            "instant": 0,
            "sorcery": 0,
        }
        for c in nonland:
            if c.get("is_instant"):
                card_type_counts["instant"] += 1
                if "removal" in (c.get("roles") or []) or "wipe" in (c.get("roles") or []):
                    interaction_types["instant"] += 1
            if c.get("is_sorcery"):
                card_type_counts["sorcery"] += 1
                if "removal" in (c.get("roles") or []) or "wipe" in (c.get("roles") or []):
                    interaction_types["sorcery"] += 1
            if c.get("is_artifact"):
                card_type_counts["artifact"] += 1
            if c.get("is_enchantment"):
                card_type_counts["enchantment"] += 1
            if c.get("is_planeswalker"):
                card_type_counts["planeswalker"] += 1
            if c.get("is_battle"):
                card_type_counts["battle"] += 1
            if c.get("is_creature"):
                card_type_counts["creature"] += 1
        
        pip_total = Counter()
        for c in all_cards:
            pip_total.update(_pip_counts(c["mana_cost"]))
        avg_cmc = round(sum(c["cmc"] for c in nonland) / max(1, len(nonland)), 2)

        categories_out = {}
        if commander:
            # Output commander with the deck's color identity, not the commander's actual colors
            cmd_out = {**self._card_out(commander), "count": 1}
            cmd_out["color_identity"] = params.colors
            cmd_out["colors"] = params.colors
            categories_out["commander"] = [cmd_out]
        for cat in ["theme", "ramp", "draw", "removal", "wipe"]:
            if by_category.get(cat):
                categories_out[cat] = [
                    {**self._card_out(c), "count": counts.get(c["name"], 1)}
                    for c in by_category[cat]
                ]
        # collapse basic lands into stacked entries
        land_counter = Counter(l["name"] for l in lands)
        categories_out["lands"] = [
            {**self._card_out_land(name), "count": n}
            for name, n in sorted(land_counter.items())
        ]

        # Classify the deck by bracket
        deck_bracket = self._classify_bracket(nonland, game_changer_count, avg_cmc)
        bracket_classification = None
        if deck_bracket is not None:
            cfg = get_bracket_config(deck_bracket)
            bracket_classification = {
                "level": deck_bracket,
                "name": cfg["name"],
                "description": cfg["description"],
                "reasoning": self._explain_bracket(deck_bracket, game_changer_count, avg_cmc),
            }
        
        result = {
            "params": params.as_dict(),
            "format": self.fmt,
            "commander": self._commander_out(commander, params.colors) if commander else None,
            "categories": categories_out,
            "stats": {
                "total_cards": len(all_cards),
                "nonland_cards": len(nonland),
                "lands": len(lands),
                "avg_cmc": avg_cmc,
                "curve": {str(k): curve_hist.get(k, 0) for k in range(1, 7)},
                "types": dict(type_hist),
                # Detailed card type distribution (Part 1)
                "card_type_distribution": {
                    "instant": card_type_counts["instant"],
                    "sorcery": card_type_counts["sorcery"],
                    "artifact": card_type_counts["artifact"],
                    "enchantment": card_type_counts["enchantment"],
                    "planeswalker": card_type_counts["planeswalker"],
                    "battle": card_type_counts["battle"],
                    "creature": card_type_counts["creature"],
                },
                "interaction_types": interaction_types,  # instant vs sorcery split for removal
                "color_pips": dict(pip_total),
                "game_changer_count": game_changer_count,
            },
            "bracket": bracket_classification,
            "reasoning": self._explain(params, commander, by_category, lands, avg_cmc),
            "source": self.client.last_source,
            "sources": {
                "cards": "api",
                "cards_from": self.client.last_source or "api",
                "network": "live",
                "llm": {
                    "available": bool(self.reranker),
                    "configured": bool(self.reranker and self.reranker.api_key),
                    "used_for_reranking": reranking_used,
                    "model": self.reranker.model if self.reranker else None,
                },
            },
            "warnings": warnings or [],
        }
        
        # Add banned cards info if any were included
        if banned_cards:
            result["banned_cards_included"] = banned_cards
            result["warnings"].insert(0, f"Deck contains {len(banned_cards)} banned cards "
                                       "(enforce_ban_list=False)")
        
        return result

    def _classify_bracket(self, nonland_cards: list, game_changer_count: int, avg_cmc: float) -> int | None:
        """Classify a finished deck by power level based on composition.
        
        Returns bracket 1-5 based on observed game changers and average MV.
        """
        # Heuristic: more game changers = higher bracket
        # Low avg_cmc can indicate faster, higher-power deck
        
        if game_changer_count >= 8:
            return 5  # cEDH territory
        elif game_changer_count >= 5:
            return 4  # Optimized
        elif game_changer_count >= 3:
            return 3  # Upgraded
        elif game_changer_count >= 1:
            return 2  # Core
        else:
            return 1  # Exhibition
    
    def _explain_bracket(self, bracket: int, game_changer_count: int, avg_cmc: float) -> str:
        """Explain why the deck was classified into a bracket."""
        reasons = []
        if game_changer_count == 0:
            reasons.append(f"zero Game Changers")
        elif game_changer_count <= 3:
            reasons.append(f"{game_changer_count} Game Changers")
        else:
            reasons.append(f"{game_changer_count} Game Changers")
        
        if avg_cmc <= 2.5:
            reasons.append("low average mana value (fast)")
        elif avg_cmc >= 3.5:
            reasons.append("high average mana value (slow/grindy)")
        
        return f"Bracket {bracket}: {' · '.join(reasons)}"

    def _card_out(self, c):
        if not c:
            return None
        return {
            "name": c["name"], "mana_cost": c["mana_cost"], "cmc": c["cmc"],
            "type_line": c["type_line"], "oracle_text": c["oracle_text"],
            "image": c["image"], "roles": c["roles"], "colors": c["color_identity"],
            "color_identity": c["color_identity"],
            "power": c.get("power"), "toughness": c.get("toughness"),
            "uri": c.get("scryfall_uri", ""),
        }

    def _commander_out(self, c, deck_colors):
        """Output commander with the deck's color identity, not the commander's actual colors."""
        if not c:
            return None
        out = {
            "name": c["name"], "mana_cost": c["mana_cost"], "cmc": c["cmc"],
            "type_line": c["type_line"], "oracle_text": c["oracle_text"],
            "image": c["image"], "roles": c["roles"], "colors": deck_colors,
            "color_identity": deck_colors,
            "power": c.get("power"), "toughness": c.get("toughness"),
            "uri": c.get("scryfall_uri", ""),
        }
        return out

    def _card_out_land(self, name):
        return {"name": name, "mana_cost": "", "cmc": 0,
                "type_line": "Basic Land", "oracle_text": "", "image": None,
                "roles": ["land"], "colors": [], "uri": ""}

    def _explain(self, params, commander, by_category, lands, avg_cmc):
        cnames = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
        lines = [params.reasoning]
        if commander:
            lines.append(f"Chose **{commander['name']}** to lead the deck — a "
                         f"legendary creature inside the {'/'.join(cnames[c] for c in params.colors)} "
                         f"identity that matches the theme.")
        counts = {k: len(v) for k, v in by_category.items()}
        lines.append(
            f"Filled the deck by role: {counts.get('theme',0)} on-theme creatures/payoffs, "
            f"{counts.get('ramp',0)} ramp, {counts.get('draw',0)} card draw, "
            f"{counts.get('removal',0)} targeted removal, {counts.get('wipe',0)} board wipes, "
            f"and {len(lands)} lands — the standard skeleton of a functional "
            f"{'Commander' if self.fmt=='commander' else '60-card'} deck."
        )
        lines.append(
            f"Average mana value of nonland cards is {avg_cmc}, shaped toward a "
            f"**{params.archetype}** curve so the deck actually plays out on time."
        )
        return " ".join(lines)


def build_deck(description: str, fmt: str = "commander", offline: bool = False,
               no_network: bool = False, use_llm: bool = True, deck_type_hint: str | None = None,
               references: list[str] | str | None = None, bracket: int | None = None,
               enforce_ban_list: bool = True, use_llm_reranking: bool = True,
               llm_model: str | None = None) -> dict:
    """Top-level convenience: description -> finished deck dict.
    
    Tries to use the card index from deckbuilder/carddata.py if available,
    otherwise falls back to live Scryfall API or sample pool.
    
    Args:
        description: User's theme description
        fmt: Deck format ("commander" or "standard")
        offline: (deprecated) Use no_network instead
        no_network: If True, prevent all outbound requests
        use_llm: Whether to use LLM enrichment for theme interpretation
        deck_type_hint: Explicit format hint
        references: Optional reference decks or cards
        bracket: Optional bracket level (1-5) to constrain and classify
        enforce_ban_list: If False, banned cards are allowed (but tagged)
        use_llm_reranking: If True, re-rank candidates using LLM (Part 2)
        llm_model: Specific Anthropic model to use for re-ranking (e.g. 'claude-3-5-haiku-20241022')
    
    Returns:
        Deck dict with sources metadata
    """
    from .theme import interpret
    from . import carddata
    from .formats import parse_bracket_from_description
    import sqlite3
    
    # Map deprecated 'offline' to 'no_network'
    no_network = no_network or offline
    
    params = interpret(description, use_llm=use_llm, references=references, no_network=no_network)
    resolved_fmt = _resolve_format(description, fmt, deck_type_hint)
    client = ScryfallClient(no_network=no_network)
    
    # Auto-detect bracket from description if not explicitly set
    if bracket is None:
        bracket = parse_bracket_from_description(description)
    
    # Disable LLM reranking if no network
    effective_reranking = use_llm_reranking and not no_network
    
    # Use local database when offline to support card searching
    db_conn = None
    if no_network:
        from pathlib import Path
        db_path = Path(__file__).resolve().parent.parent / "data" / "cards.sqlite"
        if db_path.exists():
            db_conn = sqlite3.connect(str(db_path))
            # Enable returning Row objects with column names
            db_conn.row_factory = sqlite3.Row
    
    deck = DeckBuilder(client, fmt=resolved_fmt, db_conn=db_conn,
                      bracket=bracket, enforce_ban_list=enforce_ban_list,
                      use_llm_reranking=effective_reranking,
                      llm_model=llm_model).build(params)
    # Merge sources metadata (engine adds card re-ranking info, we add top-level API info)
    # Preserve the detailed llm object from DeckBuilder.build() while adding network/cards info
    existing_sources = deck.get("sources", {})
    deck["sources"] = {
        **existing_sources,
        "cards": client.card_source,
        "network": not no_network,
    }
    # Update the llm object with network/use_llm availability if not already set
    if isinstance(existing_sources.get("llm"), dict):
        # Keep the detailed object from DeckBuilder but update availability
        deck["sources"]["llm"]["network_available"] = not no_network
        deck["sources"]["llm"]["api_enabled"] = use_llm and not no_network
    return deck

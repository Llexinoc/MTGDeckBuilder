"""Deckbuilding engine — assemble a legal, coherent deck from a card pool.

Pipeline:
    interpret theme  ->  DeckParameters
    gather candidate pools per category from Scryfall (color-identity + flavor)
    score every candidate (theme relevance + role fit + curve fit + playability)
    greedily fill category quotas, enforcing singleton / copy limits / colours
    compute the land base from the actual colour requirements of the spells
    emit the deck + statistics + human-readable reasoning

The deck is *derived* here — no external decklist is read or reproduced.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .formats import get_template, get_curve, curve_bucket
from .theme import DeckParameters
from .scryfall import ScryfallClient

BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp",
                   "R": "Mountain", "G": "Forest"}


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


class DeckBuilder:
    def __init__(self, client: ScryfallClient | None = None, fmt: str = "commander"):
        self.client = client or ScryfallClient()
        self.fmt = fmt
        self.template = get_template(fmt)

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

    # ------------------------------------------------------------- candidate pools
    def _gather(self, params: DeckParameters):
        ci = params.colors
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

    # --------------------------------------------------------------- assembly
    def build(self, params: DeckParameters) -> dict:
        template = self.template
        cats = template["categories"]
        max_copies = template["max_copies"]
        curve = get_curve(params.archetype)
        nonland_budget = template["deck_size"] - cats["lands"]

        warnings: list[str] = []
        pools = self._gather(params)
        # Terms used to *rank* candidates. Includes the expanded themes so the
        # functional pools (ramp/draw/removal) also lean on-theme — previously
        # those 31 slots were identical for any prompt with the same colours.
        rank_terms = self._search_terms(params)

        deck: list[dict] = []
        counts: Counter = Counter()          # name -> copies (for limits)
        curve_have: Counter = Counter()
        used_names: set[str] = set()
        by_category: dict[str, list[dict]] = defaultdict(list)

        # Commander first (Commander format only).
        commander = None
        if template.get("commander") and params.commander_name:
            commander = self.client.resolve_named_commander(params.commander_name,
                                                             fmt=self.fmt,
                                                             set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander and self._is_commander_candidate(commander):
                params.colors = list(commander.get("color_identity", []) or params.colors)
                warnings.append(f"Using named commander {commander['name']} to define the deck colors.")
                used_names.add(commander["name"])
            else:
                warnings.append(f"Could not resolve '{params.commander_name}' as a commander-legal card; falling back to auto-selection.")
                commander = None

        if template.get("commander") and not commander:
            commander = self.client.find_commander(params.colors, rank_terms,
                                                   set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander:
                used_names.add(commander["name"])

        order = ["ramp", "draw", "removal", "wipe", "theme"]
        for cat in order:
            quota = cats[cat]
            pool = pools.get(cat, [])
            # Rank the pool for this category.
            ranked = sorted(
                pool,
                key=lambda c: (
                    self._theme_score(c, rank_terms, params.creature_types) * 1.5
                    + self._reference_score(c, params.reference_cards)
                    + self._playability(c)
                ),
                reverse=True,
            )
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
                # enforce colour identity (belt & suspenders — API already filters)
                if not set(card["color_identity"]).issubset(set(params.colors)):
                    continue
                # curve awareness for the big theme bucket
                fit = self._curve_fit(card, curve_have, curve, nonland_budget)
                if cat == "theme" and fit < 0 and added > quota * 0.5:
                    continue
                # In non-singleton formats, run multiples of strong cards.
                copies = 1 if max_copies == 1 else min(max_copies, quota - added)
                for _ in range(copies):
                    deck.append(card)
                    curve_have[curve_bucket(card["cmc"])] += 1
                by_category[cat].append(card)  # unique entry; copies tracked below
                counts[name] += copies
                used_names.add(name)
                added += copies

        # ---- Land base: distribute basics by the colour pips actually used.
        pip_total = Counter()
        for c in deck:
            pip_total.update(_pip_counts(c["mana_cost"]))
        land_count = cats["lands"]
        lands = self._build_lands(params.colors, pip_total, land_count)

        # ---- Backfill if any category came up short (keeps the deck legal size).
        target_nonland = template["deck_size"] - land_count - (1 if commander else 0)
        current_nonland = len(deck)
        if current_nonland < target_nonland:
            filler = pools["theme"] + pools["ramp"] + pools["draw"]
            for card in filler:
                if current_nonland >= target_nonland:
                    break
                name = card["name"]
                if card["is_land"] or name in used_names:
                    continue
                if not set(card["color_identity"]).issubset(set(params.colors)):
                    continue
                deck.append(card)
                by_category["theme"].append(card)
                counts[name] += 1
                used_names.add(name)
                current_nonland += 1

        return self._finalize(params, commander, deck, by_category, lands, counts, warnings)

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
    def _finalize(self, params, commander, deck, by_category, lands, counts, warnings=None):
        all_cards = ([commander] if commander else []) + deck + lands
        nonland = [c for c in all_cards if not c["is_land"]]
        curve_hist = Counter(curve_bucket(c["cmc"]) for c in nonland)
        type_hist = Counter()
        for c in nonland:
            main = (c["types"][0] if c["types"] else "Other")
            type_hist[main] += 1
        pip_total = Counter()
        for c in all_cards:
            pip_total.update(_pip_counts(c["mana_cost"]))
        avg_cmc = round(sum(c["cmc"] for c in nonland) / max(1, len(nonland)), 2)

        categories_out = {}
        if commander:
            categories_out["commander"] = [{**self._card_out(commander), "count": 1}]
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

        return {
            "params": params.as_dict(),
            "format": self.fmt,
            "commander": self._card_out(commander) if commander else None,
            "categories": categories_out,
            "stats": {
                "total_cards": len(all_cards),
                "nonland_cards": len(nonland),
                "lands": len(lands),
                "avg_cmc": avg_cmc,
                "curve": {str(k): curve_hist.get(k, 0) for k in range(1, 7)},
                "types": dict(type_hist),
                "color_pips": dict(pip_total),
            },
            "reasoning": self._explain(params, commander, by_category, lands, avg_cmc),
            "source": self.client.last_source,
            "warnings": warnings or [],
        }

    def _card_out(self, c):
        if not c:
            return None
        return {
            "name": c["name"], "mana_cost": c["mana_cost"], "cmc": c["cmc"],
            "type_line": c["type_line"], "oracle_text": c["oracle_text"],
            "image": c["image"], "roles": c["roles"], "colors": c["color_identity"],
            "power": c.get("power"), "toughness": c.get("toughness"),
            "uri": c.get("scryfall_uri", ""),
        }

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
               use_llm: bool = True, deck_type_hint: str | None = None,
               references: list[str] | str | None = None) -> dict:
    """Top-level convenience: description -> finished deck dict."""
    from .theme import interpret
    params = interpret(description, use_llm=use_llm, references=references)
    resolved_fmt = _resolve_format(description, fmt, deck_type_hint)
    client = ScryfallClient(offline=offline)
    return DeckBuilder(client, fmt=resolved_fmt).build(params)

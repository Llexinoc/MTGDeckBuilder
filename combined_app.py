"""Single-file merge of the MTG Theme Deckbuilder core modules.

This replicates the core functionality of `deckbuilder/*.py` in one file
so i can run or inspect the logic without the package layout.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

try:
    import requests
except Exception:
    requests = None

from flask import Flask, jsonify, render_template, request

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

# ----------------- formats.py content -----------------
FORMAT_TEMPLATES = {
    "commander": {
        "deck_size": 100,
        "singleton": True,
        "max_copies": 1,
        "commander": True,
        "categories": {
            "lands": 36,
            "ramp": 10,
            "draw": 10,
            "removal": 8,
            "wipe": 3,
            "theme": 32,
        },
    },
    "standard": {
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

# ----------------- expand.py content (minimal copy) -----------------
PROMPT_SYNONYMS = {"iron man": ["armor", "machine", "suit", "weapon"], "red rising": ["spaceship", "rebellion", "war"]}
DEFAULT_THEME_MAP = {
    "iron": ["artifact", "equipment"],
    "man": ["legendary", "voltron"],
    "rebellion": ["tokens", "aggro"],
    "war": ["aggro", "tokens"],
}

def _themes_for(word: str) -> list[str]:
    if word in DEFAULT_THEME_MAP:
        return DEFAULT_THEME_MAP[word]
    if word.endswith("s") and word[:-1] in DEFAULT_THEME_MAP:
        return DEFAULT_THEME_MAP[word[:-1]]
    return []

def expand_query(query: str, use_llm: bool = True) -> dict:
    cleaned = (query or "").strip()
    if not cleaned:
        return {"query": "", "concepts": [], "mtg_themes": []}
    base_words = [cleaned.lower()]
    if re.search(r"\s", cleaned):
        base_words.extend([w for w in re.split(r"[^a-zA-Z0-9]+", cleaned.lower()) if w])
    for phrase, synonyms in PROMPT_SYNONYMS.items():
        if phrase in cleaned.lower():
            base_words.extend(synonyms)
    concepts = []
    for item in base_words:
        word = re.sub(r"[^a-z0-9]+", " ", str(item).lower()).strip()
        if word and word not in concepts:
            concepts.append(word)
    mtg_themes = []
    for concept in concepts:
        for theme in _themes_for(concept):
            if theme not in mtg_themes:
                mtg_themes.append(theme)
    return {"query": cleaned, "concepts": concepts[:30], "mtg_themes": mtg_themes[:20]}

# ----------------- scryfall.py content (condensed) -----------------
DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_DIR = DATA_DIR / "cache"
SAMPLE_FILE = DATA_DIR / "sample_cards.json"

WUBRG = ["W", "U", "B", "R", "G"]

def detect_roles(type_line: str, oracle: str) -> list[str]:
    t = (type_line or "").lower()
    o = (oracle or "").lower()
    roles: list[str] = []
    if "land" in t:
        roles.append("land")
    if any(p in o for p in ["add {", "search your library for a", "add one mana", "adds an additional", "put a land card"]):
        if not ("land" in t and "add {" in o):
            roles.append("ramp")
    if "draw" in o and "card" in o:
        roles.append("draw")
    if any(p in o for p in ["destroy all", "exile all", "each creature"]):
        roles.append("wipe")
    if any(p in o for p in ["destroy target", "exile target", "counter target", "deals damage to target"]):
        roles.append("removal")
    if "creature" in t and "land" not in t:
        roles.append("creature")
    return list(dict.fromkeys(roles))

def _image_from(raw: dict) -> str | None:
    imgs = raw.get("image_uris")
    if imgs:
        return imgs.get("normal") or imgs.get("large") or imgs.get("small")
    faces = raw.get("card_faces")
    if faces and isinstance(faces, list):
        f0 = faces[0].get("image_uris") or {}
        return f0.get("normal") or f0.get("large")
    return None

def normalize(raw: dict) -> dict:
    type_line = raw.get("type_line", "") or ""
    oracle = raw.get("oracle_text", "") or ""
    if not oracle and raw.get("card_faces"):
        oracle = " // ".join(f.get("oracle_text", "") for f in raw["card_faces"])
    types = re.findall(r"[A-Za-z]+", type_line.split("—")[0])
    return {
        "name": raw.get("name", "Unknown"),
        "mana_cost": raw.get("mana_cost", "") or "",
        "cmc": float(raw.get("cmc", 0) or 0),
        "colors": raw.get("colors", []) or [],
        "color_identity": raw.get("color_identity", []) or [],
        "type_line": type_line,
        "types": [t for t in types if t not in ("Legendary", "Basic", "Snow", "World")],
        "supertypes": [t for t in types if t in ("Legendary", "Basic", "Snow")],
        "oracle_text": oracle,
        "keywords": raw.get("keywords", []) or [],
        "power": raw.get("power"),
        "toughness": raw.get("toughness"),
        "image": _image_from(raw),
        "edhrec_rank": raw.get("edhrec_rank", 10 ** 9),
        "produced_mana": raw.get("produced_mana", []) or [],
        "legalities": raw.get("legalities", {}) or {},
        "scryfall_uri": raw.get("scryfall_uri", ""),
        "roles": detect_roles(type_line, oracle),
        "is_land": "Land" in type_line,
        "is_creature": "Creature" in type_line,
        "is_legendary": "Legendary" in type_line,
    }

def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"

def _cached_get(url: str, params: dict) -> dict | None:
    key = url + json.dumps(params, sort_keys=True)
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) < 60 * 60 * 24:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if requests is None:
        return None
    time.sleep(0.12)
    resp = requests.get(url, params=params, timeout=20)
    if resp.status_code == 429:
        raise RuntimeError("Scryfall rate limit hit (429). Back off and retry.")
    if resp.status_code == 404:
        return {"object": "list", "data": [], "total_cards": 0, "has_more": False}
    resp.raise_for_status()
    data = resp.json()
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
    return data

class ScryfallClient:
    def __init__(self, offline: bool = False):
        self.offline = offline
        self._sample: list[dict] | None = None
        self.last_source = "live"

    def _load_sample(self) -> list[dict]:
        if self._sample is None:
            try:
                raw = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
                self._sample = [normalize(c) for c in raw]
            except Exception:
                self._sample = []
        return self._sample

    def _offline_find(self, color_identity, card_type, oracle_terms,
                      name_terms, exclude_types, max_cmc, limit) -> list[dict]:
        ci = set(color_identity)
        out = []
        required_types = [t.lower() for t in re.split(r"\s+", str(card_type or "").strip()) if t.strip()]
        for c in self._load_sample():
            if not set(c["color_identity"]).issubset(ci):
                continue
            if required_types and not all(req in c["type_line"].lower() for req in required_types):
                continue
            if exclude_types and any(ex.lower() in c["type_line"].lower() for ex in exclude_types):
                continue
            if max_cmc is not None and c["cmc"] > max_cmc:
                continue
            if oracle_terms or name_terms:
                hay = (c["oracle_text"] + " " + c["name"]).lower()
                if not any(t.lower() in hay for t in list(oracle_terms or []) + list(name_terms or [])):
                    continue
            out.append(c)
        out.sort(key=lambda c: c["edhrec_rank"])
        return out[:limit]

    def find_cards(self, color_identity: list[str], card_type: str | None = None,
                   oracle_terms: Iterable[str] | None = None, name_terms: Iterable[str] | None = None,
                   exclude_types: Iterable[str] | None = None, fmt: str = "commander",
                   max_cmc: int | None = None, order: str = "edhrec", limit: int = 120,
                   set_codes: Iterable[str] | None = None) -> list[dict]:
        oracle_terms = list(oracle_terms or [])
        name_terms = list(name_terms or [])
        exclude_types = list(exclude_types or [])
        if self.offline:
            self.last_source = "offline"
            return self._offline_find(color_identity, card_type, oracle_terms,
                                      name_terms, exclude_types, max_cmc, limit)
        query = build_query(color_identity, card_type, oracle_terms, name_terms,
                            exclude_types, fmt, max_cmc, set_codes)
        params = {"q": query, "order": order, "unique": "cards", "dir": "asc"}
        try:
            collected: list[dict] = []
            data = _cached_get(f"https://api.scryfall.com/cards/search", params)
            if data is None:
                raise RuntimeError("no-network")
            collected.extend(data.get("data", []))
            if data.get("has_more") and len(collected) < limit and data.get("next_page"):
                nxt = _cached_get(data["next_page"], {})
                if nxt:
                    collected.extend(nxt.get("data", []))
            if collected:
                self.last_source = "live"
                return [normalize(c) for c in collected[:limit]]
            self.last_source = "live"
            return [normalize(c) for c in collected[:limit]]
        except Exception:
            self.offline = True
            self.last_source = "offline"
            return self._offline_find(color_identity, card_type, oracle_terms,
                                      name_terms, exclude_types, max_cmc, limit)

    def resolve_set_code(self, set_name: str | None) -> str | None:
        if not set_name:
            return None
        norm = set_name.strip().lower()
        if not norm:
            return None
        if self.offline or requests is None:
            return None
        try:
            data = _cached_get("https://api.scryfall.com/sets", {})
            if not data:
                return None
            for item in data.get("data", []):
                name = (item.get("name") or "").lower()
                code = (item.get("code") or "").lower()
                if norm == name or norm == code or norm in name or name in norm:
                    return item.get("code")
        except Exception:
            return None
        return None

    def _is_commander_legal(self, card: dict | None) -> bool:
        if not card:
            return False
        type_line = (card.get("type_line") or "").lower()
        oracle = (card.get("oracle_text") or "").lower()
        if "legendary" not in type_line:
            return False
        if "creature" not in type_line and "can be your commander" not in oracle:
            return False
        legality = (card.get("legalities") or {}).get("commander")
        return legality == "legal"

    def resolve_named_commander(self, name, fmt="commander", set_codes=None):
        name = (name or "").strip()
        if not name:
            return None
        if self.offline:
            self.last_source = "offline"
            return None
        params = {"fuzzy": name}
        try:
            data = _cached_get("https://api.scryfall.com/cards/named", params)
            if not data:
                return None
            card = normalize(data)
            if self._is_commander_legal(card):
                self.last_source = "live"
                return card
        except Exception:
            pass
        return None

    def find_commander(self, color_identity, theme_terms, fmt="commander", set_codes=None):
        cands = self.find_cards(color_identity, card_type="Legendary Creature",
                                oracle_terms=theme_terms or None, fmt=fmt, order="edhrec", limit=40,
                                set_codes=set_codes)
        if not cands:
            cands = self.find_cards(color_identity, card_type="Legendary Creature",
                                    fmt=fmt, order="edhrec", limit=40, set_codes=set_codes)
        cands = [c for c in cands if self._is_commander_legal(c)]
        want = set(color_identity)
        cands.sort(key=lambda c: (-(len(set(c["color_identity"]) & want)), c["edhrec_rank"]))
        return cands[0] if cands else None

# ----------------- theme.py content (condensed) -----------------
COLOR_NAMES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
ARCHETYPES = {"aggro": ["aggress", "fast"], "aristocrats": ["sacrifice"], "tokens": ["army"], "control": ["control"], "ramp": ["ramp"]}
THEME_COLOR_HINTS = {"equipment": "WR", "tokens": "WG", "aristocrats": "B", "aggro": "R"}
THEME_SEARCH_TERMS = {"equipment": ["equipment"], "tokens": ["create"], "aristocrats": ["sacrifice"], "aggro": ["haste"]}
FLAVOR_TERMS = {"rebel": ["rebel", "revolt"]}
CREATURE_TYPES = ["soldier", "warrior", "goblin"]

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
    for color, words in {
        "W": ["order", "law"],
        "U": ["knowledge"],
        "B": ["power", "death"],
        "R": ["rebel", "war"],
        "G": ["nature", "ramp"],
    }.items():
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

def interpret(description, use_llm=True, references=None):
    expansion = expand_query(description, use_llm=use_llm)
    set_names = []
    set_codes = []
    commander_name = None
    reference_cards = []
    reference_sources = []
    themes = [t for t in expansion.get("mtg_themes", []) if t]
    enriched = " ".join([description] + expansion.get("concepts", []) + themes)
    scores = _score_colors(enriched)
    colors = _pick_colors(scores)
    archetype = "aggro" if "R" in colors else "midrange"
    terms = _derive_oracle_terms(enriched)
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
        reasoning="Mapped theme to colours and archetype",
        source="heuristic",
    )

# ----------------- engine.py content (condensed) -----------------
BASIC_FOR_COLOR = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}

def _resolve_format(description: str, fmt: str = "commander", deck_type_hint: str | None = None) -> str:
    hint = (deck_type_hint or "").strip().lower()
    text = (description or "").lower()
    if hint in {"60-card", "standard"}:
        return "standard"
    if hint in {"100-card", "commander"}:
        return "commander"
    if re.search(r"\b(60|sixty)\s*-?\s*(card|cards)\b", text):
        return "standard"
    if re.search(r"\b(100|one hundred)\s*-?\s*(card|cards)\b", text) or any(k in text for k in ["commander", "edh", "singleton"]):
        return "commander"
    return fmt if fmt in {"commander", "standard"} else "commander"

def _pip_counts(mana_cost: str) -> Counter:
    return Counter(re.findall(r"\{([WUBRG])\}", mana_cost or ""))

class DeckBuilder:
    def __init__(self, client: ScryfallClient | None = None, fmt: str = "commander"):
        self.client = client or ScryfallClient()
        self.fmt = fmt
        self.template = get_template(fmt)

    def _normalize_card(self, card: dict | None) -> dict | None:
        if not card:
            return None
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

    def _search_terms(self, params: DeckParameters) -> list[str]:
        expansion_terms = [t for t in (params.expansion or {}).get("mtg_themes", []) if t]
        terms = []
        for t in list(params.oracle_terms or []) + expansion_terms:
            if t and t not in terms:
                terms.append(t)
        return terms

    def _gather(self, params: DeckParameters):
        ci = params.colors
        creature_terms = list(params.creature_types or [])
        set_codes = list(params.set_codes or [])
        search_terms = []
        for t in self._search_terms(params) + creature_terms:
            if t and t not in search_terms:
                search_terms.append(t)
        name_terms = [t for t in creature_terms if t] or None
        fmt_legal = "commander" if self.fmt == "commander" else "standard"
        pools = {}
        pools["ramp"] = self.client.find_cards(ci, oracle_terms=["add {", "search your library for a", "mana"], exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["draw"] = self.client.find_cards(ci, oracle_terms=["draw a card", "draw two cards", "draw cards"], exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["removal"] = self.client.find_cards(ci, oracle_terms=["destroy target", "exile target", "damage to any target", "counter target"], exclude_types=["Land"], fmt=fmt_legal, limit=60, set_codes=set_codes)
        pools["wipe"] = self.client.find_cards(ci, oracle_terms=["destroy all", "exile all", "each creature", "damage to each creature"], exclude_types=["Land"], fmt=fmt_legal, limit=40, set_codes=set_codes)
        pools["theme"] = self.client.find_cards(ci, card_type="Creature", oracle_terms=search_terms or None, name_terms=name_terms, fmt=fmt_legal, limit=120, set_codes=set_codes)
        if len(pools["theme"]) < 20:
            pools["theme"] += self.client.find_cards(ci, card_type="Creature", name_terms=name_terms, fmt=fmt_legal, limit=120, set_codes=set_codes)
        return pools

    def build(self, params: DeckParameters) -> dict:
        template = self.template
        cats = template["categories"]
        max_copies = template["max_copies"]
        curve = get_curve(params.archetype)
        nonland_budget = template["deck_size"] - cats["lands"]
        warnings: list[str] = []
        pools = self._gather(params)
        rank_terms = self._search_terms(params)
        deck: list[dict] = []
        counts: Counter = Counter()
        curve_have: Counter = Counter()
        used_names: set[str] = set()
        by_category: dict[str, list[dict]] = defaultdict(list)
        commander = None
        if template.get("commander") and params.commander_name:
            commander = self.client.resolve_named_commander(params.commander_name, fmt=self.fmt, set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander and self._is_commander_candidate(commander):
                params.colors = list(commander.get("color_identity", []) or params.colors)
                used_names.add(commander["name"])
            else:
                commander = None
        if template.get("commander") and not commander:
            commander = self.client.find_commander(params.colors, rank_terms, set_codes=list(params.set_codes or []))
            commander = self._normalize_card(commander)
            if commander:
                used_names.add(commander["name"])
        order = ["ramp", "draw", "removal", "wipe", "theme"]
        for cat in order:
            quota = cats[cat]
            pool = pools.get(cat, [])
            ranked = sorted(pool, key=lambda c: (0.0 + 0.0 + (c.get("edhrec_rank") or 10**9)), reverse=False)
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
                copies = 1 if max_copies == 1 else min(max_copies, quota - added)
                for _ in range(copies):
                    deck.append(card)
                by_category[cat].append(card)
                counts[name] += copies
                used_names.add(name)
                added += copies
        pip_total = Counter()
        for c in deck:
            pip_total.update(_pip_counts(c["mana_cost"]))
        land_count = cats["lands"]
        lands = self._build_lands(params.colors, pip_total, land_count)
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
        alloc = {}
        for c in colors:
            share = pip_total.get(c, 0) / total_pips if total_pips else 1 / len(colors)
            n = max(2, round(share * land_count))
            alloc[c] = n
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
        return {"name": c["name"], "mana_cost": c["mana_cost"], "cmc": c["cmc"], "type_line": c["type_line"], "oracle_text": c["oracle_text"], "image": c["image"], "roles": c["roles"], "colors": c["color_identity"], "power": c.get("power"), "toughness": c.get("toughness"), "uri": c.get("scryfall_uri", "")}

    def _card_out_land(self, name):
        return {"name": name, "mana_cost": "", "cmc": 0, "type_line": "Basic Land", "oracle_text": "", "image": None, "roles": ["land"], "colors": [], "uri": ""}

    def _explain(self, params, commander, by_category, lands, avg_cmc):
        lines = [params.reasoning]
        if commander:
            lines.append(f"Chose {commander['name']} to lead the deck.")
        counts = {k: len(v) for k, v in by_category.items()}
        lines.append(f"Filled the deck by role: {counts.get('theme',0)} theme, {counts.get('ramp',0)} ramp, {len(lands)} lands.")
        lines.append(f"Average mana value of nonland cards is {avg_cmc}.")
        return " ".join(lines)

def build_deck(description: str, fmt: str = "commander", offline: bool = False, use_llm: bool = True, deck_type_hint: str | None = None, references: list[str] | str | None = None) -> dict:
    params = interpret(description, use_llm=use_llm, references=references)
    resolved_fmt = _resolve_format(description, fmt, deck_type_hint)
    client = ScryfallClient(offline=offline)
    return DeckBuilder(client, fmt=resolved_fmt).build(params)

# ----------------- Flask app (same endpoints as original) -----------------
app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY"))})

@app.route("/api/build", methods=["POST"])
def api_build():
    data = request.get_json(force=True, silent=True) or {}
    description = (data.get("description") or "").strip()
    fmt = data.get("format", "commander")
    deck_type_hint = (data.get("deck_type_hint") or data.get("deck_type") or "").strip()
    offline = bool(data.get("offline", False))
    references = data.get("references") or data.get("reference_cards") or []
    if not description:
        return jsonify({"error": "Please enter a theme or description."}), 400
    try:
        deck = build_deck(description, fmt=fmt, offline=offline, use_llm=True, deck_type_hint=deck_type_hint, references=references)
        return jsonify(deck)
    except Exception as exc:
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=True)

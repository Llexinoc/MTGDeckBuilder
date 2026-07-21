"""Scryfall data access + card normalization.

Responsibilities:
  * Query the live Scryfall API (rate-limited, cached, correct headers).
  * Fall back to a bundled offline card pool when there is no network.
  * Normalize raw Scryfall JSON into a compact Card dict the engine understands.
  * Tag each card with functional "roles" (ramp / draw / removal / wipe ...)
    so the deckbuilding engine can fill category quotas.

Nothing here reads or reproduces user-authored decklists. We only fetch
individual card records and reason about them ourselves.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterable

try:
    import requests
except ImportError:  # requests is optional for the pure-offline path
    requests = None

logger = logging.getLogger(__name__)

# Exceptions
class ScryfallUnavailable(Exception):
    """Raised when Scryfall API is unreachable after retries."""
    pass

API_BASE = "https://api.scryfall.com"
# Scryfall REQUIRES a descriptive User-Agent and an Accept header.
HEADERS = {
    "User-Agent": "MTGThemeDeckbuilder/1.0 (educational project)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}
REQUEST_DELAY = 0.12  # seconds between calls -> well under Scryfall's 10 req/s
CACHE_TTL = 60 * 60 * 24  # cache responses for 24h, as Scryfall requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
SAMPLE_FILE = DATA_DIR / "sample_cards.json"

WUBRG = ["W", "U", "B", "R", "G"]
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


# --------------------------------------------------------------------------- #
# Role detection — what does a card *do*?
# --------------------------------------------------------------------------- #
def detect_roles(type_line: str, oracle: str) -> list[str]:
    """Heuristically classify a card's function from its text."""
    t = (type_line or "").lower()
    o = (oracle or "").lower()
    roles: list[str] = []

    if "land" in t:
        roles.append("land")

    # Ramp: makes or fetches extra mana / lands.
    if any(p in o for p in [
        "add {", "search your library for a", "add one mana", "adds an additional",
        "put a land card", "untap target land",
    ]) and "land" in o or "add {c}" in o or re.search(r"add \{[wubrgc]", o):
        if "land" in t and "add {" in o:
            pass  # basic lands aren't "ramp"
        else:
            roles.append("ramp")
    if any(p in o for p in ["search your library for a basic land", "search your library for a land",
                            "search your library for up to two"]):
        if "ramp" not in roles:
            roles.append("ramp")

    # Card draw / advantage.
    if "draw" in o and "card" in o and "draws a card" not in o.replace("you draw", ""):
        roles.append("draw")
    elif "draw a card" in o or "draw two cards" in o or "draw three cards" in o:
        roles.append("draw")

    # Board wipe.
    if any(p in o for p in [
        "destroy all", "exile all", "each creature", "all creatures get -",
        "deals damage to each creature", "destroy each",
    ]):
        roles.append("wipe")

    # Targeted removal / interaction.
    if any(p in o for p in [
        "destroy target", "exile target", "counter target", "deals damage to target",
        "target creature gets -", "target player sacrifices", "return target",
        "fight", "damage to any target",
    ]):
        roles.append("removal")

    if "creature" in t and "land" not in t:
        roles.append("creature")

    return list(dict.fromkeys(roles))  # dedupe, keep order


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
    """Turn a raw Scryfall (or sample) record into a compact Card dict."""
    # Handle card_faces for double-faced cards
    card_faces = raw.get("card_faces", [])
    
    # Get type_line: top-level first, then join from faces
    type_line = raw.get("type_line", "") or ""
    if not type_line and card_faces:
        type_line = " // ".join(
            f.get("type_line", "") for f in card_faces if f.get("type_line")
        )
    
    # Get oracle_text: top-level first, then join from faces
    oracle = raw.get("oracle_text", "") or ""
    if not oracle and card_faces:
        oracle = " // ".join(
            f.get("oracle_text", "") for f in card_faces if f.get("oracle_text")
        )
    
    # Get mana_cost: top-level first, then concatenate from faces
    mana_cost = raw.get("mana_cost", "") or ""
    if not mana_cost and card_faces:
        mana_cost = "".join(
            f.get("mana_cost", "") for f in card_faces if f.get("mana_cost")
        )
    
    types = re.findall(r"[A-Za-z]+", type_line.split("—")[0])
    return {
        "name": raw.get("name", "Unknown"),
        "mana_cost": mana_cost,
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


# --------------------------------------------------------------------------- #
# Query construction for the live API
# --------------------------------------------------------------------------- #
def build_query(
    color_identity: list[str],
    card_type: str | None = None,
    oracle_terms: Iterable[str] | None = None,
    name_terms: Iterable[str] | None = None,
    exclude_types: Iterable[str] | None = None,
    fmt: str = "commander",
    max_cmc: int | None = None,
    set_codes: Iterable[str] | None = None,
) -> str:
    parts: list[str] = []
    ci = "".join(c for c in color_identity if c in WUBRG)
    if ci:
        parts.append(f"id<={ci}")
    else:
        parts.append("id:c")  # colorless
    if card_type:
        for token in re.split(r"\s+", str(card_type).strip()):
            token = token.strip().lower()
            if token:
                parts.append(f"t:{token}")
    for ex in exclude_types or []:
        parts.append(f"-t:{ex}")
    ors = []
    for term in oracle_terms or []:
        cleaned = term.strip().replace('"', '')
        if cleaned:
            ors.append(f'o:{cleaned}')
    for term in name_terms or []:
        cleaned = term.strip().replace('"', '')
        if cleaned:
            ors.append(f'name:{cleaned}')
    if ors:
        parts.append("(" + " OR ".join(ors) + ")")
    if max_cmc is not None:
        parts.append(f"cmc<={max_cmc}")
    if set_codes:
        codes = [c for c in set_codes if c]
        if len(codes) == 1:
            parts.append(f"set:{codes[0]}")
        else:
            parts.append("(" + " OR ".join(f"set:{c}" for c in codes) + ")")
    if fmt:
        parts.append(f"legal:{fmt}")
    # Quality/consistency filters — paper cards, no silver-border/joke cards.
    parts.append("game:paper")
    parts.append("-is:funny")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# HTTP with caching + rate limiting
# --------------------------------------------------------------------------- #
def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def _cached_get(url: str, params: dict, no_network: bool = False) -> dict | None:
    """Fetch from cache or HTTP with retry logic and no_network support.
    
    Args:
        url: The API endpoint URL
        params: Query parameters
        no_network: If True, prevent any network requests (disk cache only)
    
    Returns:
        Parsed JSON response, or None if unavailable
    
    Raises:
        ScryfallUnavailable: If max retries exhausted on network errors
    """
    key = url + json.dumps(params, sort_keys=True)
    path = _cache_path(key)
    
    # Check cache first (always allowed, even with no_network)
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # If no_network or no requests library, return None (caller handles graceful fallback)
    if no_network:
        logger.info(f"Blocked network request to {url} (no_network=True)")
        return None
    
    if requests is None:
        return None
    
    # Retry logic: 429 errors get 3 attempts, connection errors get 2 attempts
    backoff_schedule = [1, 2, 4]  # seconds
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
            
            # Success
            if resp.status_code == 200:
                data = resp.json()
                try:
                    path.write_text(json.dumps(data), encoding="utf-8")
                except Exception:
                    pass
                return data
            
            # 404 -> return empty result, not an error
            if resp.status_code == 404:
                return {"object": "list", "data": [], "total_cards": 0, "has_more": False}
            
            # 429 rate limit -> retry with backoff
            if resp.status_code == 429:
                if attempt < max_attempts - 1:
                    # Honor Retry-After header if present
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_seconds = int(retry_after)
                        except ValueError:
                            wait_seconds = backoff_schedule[attempt]
                    else:
                        wait_seconds = backoff_schedule[attempt]
                    
                    logger.warning(
                        f"Scryfall 429 (attempt {attempt + 1}/{max_attempts}), "
                        f"retry after {wait_seconds}s: {url}"
                    )
                    time.sleep(wait_seconds)
                    continue
                else:
                    # Exhausted retries
                    raise ScryfallUnavailable(
                        f"Scryfall rate limit (429) after {max_attempts} attempts"
                    )
            
            # Other HTTP errors
            resp.raise_for_status()
        
        except (requests.Timeout, requests.ConnectionError) as e:
            # Connection errors -> 2 retries max
            if attempt < min(1, max_attempts - 1):
                wait_seconds = backoff_schedule[attempt]
                logger.warning(
                    f"{type(e).__name__} (attempt {attempt + 1}/2), "
                    f"retry after {wait_seconds}s: {url}"
                )
                time.sleep(wait_seconds)
                continue
            else:
                raise ScryfallUnavailable(f"Scryfall unreachable: {e}")
    
    return None


class ScryfallClient:
    """Finds cards matching structured criteria, live or offline."""

    def __init__(self, offline: bool = False, no_network: bool = False):
        """Initialize Scryfall client.
        
        Args:
            offline: (deprecated) Falls back to bundled sample pool
            no_network: Hard guarantee of zero outbound requests
        """
        # Map deprecated 'offline' param to 'no_network'
        self.no_network = no_network or offline
        self._sample: list[dict] | None = None
        self.last_source = "live"
        self.card_source = "unknown"  # Will be set to "api", "index", or "sample"

    # -- offline pool -------------------------------------------------------- #
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

    # -- public API ---------------------------------------------------------- #
    def find_cards(
        self,
        color_identity: list[str],
        card_type: str | None = None,
        oracle_terms: Iterable[str] | None = None,
        name_terms: Iterable[str] | None = None,
        exclude_types: Iterable[str] | None = None,
        fmt: str = "commander",
        max_cmc: int | None = None,
        order: str = "edhrec",
        limit: int = 120,
        set_codes: Iterable[str] | None = None,
    ) -> list[dict]:
        """Return normalized cards matching the criteria (best/most-played first).

        `order=edhrec` sorts by how commonly a card *sees play* — a quality
        signal about the individual card, not a copy of any specific deck.
        """
        oracle_terms = list(oracle_terms or [])
        name_terms = list(name_terms or [])
        exclude_types = list(exclude_types or [])

        query = build_query(color_identity, card_type, oracle_terms, name_terms,
                            exclude_types, fmt, max_cmc, set_codes)
        params = {"q": query, "order": order, "unique": "cards", "dir": "asc"}
        try:
            collected: list[dict] = []
            data = _cached_get(f"{API_BASE}/cards/search", params, no_network=self.no_network)
            if data is None:  # no network + not cached -> offline fallback
                self.card_source = "sample"
                self.last_source = "offline"
                return self._offline_find(color_identity, card_type, oracle_terms,
                                          name_terms, exclude_types, max_cmc, limit)
            collected.extend(data.get("data", []))
            # one extra page is plenty for our category pools
            if data.get("has_more") and len(collected) < limit and data.get("next_page"):
                nxt = _cached_get(data["next_page"], {}, no_network=self.no_network)
                if nxt:
                    collected.extend(nxt.get("data", []))
            if collected:
                self.card_source = "api"
                self.last_source = "live"
                return [normalize(c) for c in collected[:limit]]

            if set_codes:
                fallback_query = build_query(color_identity, card_type, oracle_terms, name_terms,
                                             exclude_types, fmt, max_cmc, None)
                fallback_params = {"q": fallback_query, "order": order, "unique": "cards", "dir": "asc"}
                fallback_data = _cached_get(f"{API_BASE}/cards/search", fallback_params, 
                                           no_network=self.no_network)
                if fallback_data:
                    collected.extend(fallback_data.get("data", []))
            self.card_source = "api" if collected else "sample"
            self.last_source = "live" if collected else "offline"
            return [normalize(c) for c in collected[:limit]]
        except ScryfallUnavailable:
            # On network errors, fall back to sample pool
            logger.warning(f"Scryfall unavailable, falling back to sample pool")
            self.card_source = "sample"
            self.last_source = "offline"
            return self._offline_find(color_identity, card_type, oracle_terms,
                                      name_terms, exclude_types, max_cmc, limit)
        except Exception as e:
            # Other errors -> graceful degrade to sample pool
            logger.warning(f"Error querying Scryfall: {e}, falling back to sample pool")
            self.card_source = "sample"
            self.last_source = "offline"
            return self._offline_find(color_identity, card_type, oracle_terms,
                                      name_terms, exclude_types, max_cmc, limit)

    def resolve_set_code(self, set_name: str | None) -> str | None:
        if not set_name:
            return None
        norm = set_name.strip().lower()
        if not norm:
            return None
        if norm in SET_ALIASES:
            return SET_ALIASES[norm]
        for alias, code in SET_ALIASES.items():
            if alias in norm or norm in alias:
                return code
        if self.no_network or requests is None:
            logger.debug(f"Skipped set resolution for '{set_name}' (no_network={self.no_network})")
            return None
        try:
            data = _cached_get(f"{API_BASE}/sets", {}, no_network=False)
            if not data:
                return None
            for item in data.get("data", []):
                name = (item.get("name") or "").lower()
                code = (item.get("code") or "").lower()
                if norm == name or norm == code or norm in name or name in norm:
                    return item.get("code")
        except ScryfallUnavailable:
            logger.warning(f"Could not resolve set '{set_name}' (Scryfall unavailable)")
            return None
        except Exception as e:
            logger.warning(f"Error resolving set '{set_name}': {e}")
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
        """Resolve a user-specified commander name via Scryfall's fuzzy card API."""
        name = (name or "").strip()
        if not name:
            return None
        if self.no_network:
            logger.debug(f"Skipped commander resolution for '{name}' (no_network=True)")
            return None
        params = {"fuzzy": name}
        try:
            data = _cached_get(f"{API_BASE}/cards/named", params, no_network=False)
            if not data:
                return None
            card = normalize(data)
            if self._is_commander_legal(card):
                self.last_source = "live"
                return card
        except ScryfallUnavailable:
            logger.warning(f"Could not resolve commander '{name}' (Scryfall unavailable)")
            return None
        except Exception as e:
            logger.warning(f"Error resolving commander '{name}': {e}")
            pass
        return None

    def find_commander(self, color_identity, theme_terms, fmt="commander", set_codes=None):
        """Find a legendary creature to lead the deck, matching colors/theme."""
        cands = self.find_cards(
            color_identity, card_type="Legendary Creature",
            oracle_terms=theme_terms or None, fmt=fmt, order="edhrec", limit=40,
            set_codes=set_codes,
        )
        if not cands:
            cands = self.find_cards(color_identity, card_type="Legendary Creature",
                                    fmt=fmt, order="edhrec", limit=40,
                                    set_codes=set_codes)
        cands = [c for c in cands if self._is_commander_legal(c)]
        # Prefer a commander whose identity uses all requested colors.
        want = set(color_identity)
        cands.sort(key=lambda c: (-(len(set(c["color_identity"]) & want)), c["edhrec_rank"]))
        return cands[0] if cands else None

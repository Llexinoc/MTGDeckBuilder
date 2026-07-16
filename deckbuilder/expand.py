"""Semantic keyword expansion for short prompts.

This module expands a short user query into related concepts using Datamuse,
optionally enriches them with an LLM, maps them to MTG themes/mechanics, and
uses those themes to bias deckbuilding toward relevant cards.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = DATA_DIR / "cache"
EXPAND_CACHE_DIR = CACHE_DIR / "expand"
EXPAND_CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "MTGThemeDeckbuilder/1.0 (educational project)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}

PROMPT_SYNONYMS = {
    "iron man": ["armor", "machine", "suit", "weapon"],
    "red rising": ["spaceship", "rebellion", "war"],
}

DEFAULT_THEME_MAP = {
    "iron": ["artifact", "equipment"],
    "man": ["legendary", "voltron"],
    "armor": ["equipment"],
    "suit": ["equipment"],
    "machine": ["artifact", "equipment"],
    "weapon": ["equipment"],
    "spaceship": ["vehicle", "artifact"],
    "rebellion": ["tokens", "aggro"],
    "war": ["aggro", "tokens"],
    "revolt": ["aggro", "tokens"],
    "robot": ["artifact", "equipment"],
    "pilot": ["vehicle", "artifact"],
    "hero": ["legendary", "voltron"],
    "iron man": ["artifact", "equipment", "legendary"],
    "shield": ["equipment"],
    "flight": ["flying"],
    "power": ["ramp", "tokens"],
    "sacrifice": ["aristocrats"],
    "death": ["aristocrats"],
    "magic": ["spellslinger"],
    "storm": ["spellslinger"],
    "nature": ["ramp"],
    "beast": ["tribal"],
    "dragon": ["tribal"],
    "demon": ["tribal"],
    "angel": ["tribal"],
    "goblin": ["tribal", "aggro"],
    "elf": ["tribal"],
    "wizard": ["tribal", "spellslinger"],
    "zombie": ["tribal", "aristocrats"],
    "cat": ["tribal"],
    "dog": ["tribal"],
    "dinosaur": ["tribal"],
    "pirate": ["tribal"],
    "ninja": ["tribal"],
    "samurai": ["tribal", "equipment"],
    "knight": ["tribal", "equipment"],
    "mech": ["artifact", "vehicle"],
    "space": ["artifact", "vehicle"],
    "ship": ["vehicle"],
    "cyber": ["artifact"],
    "hacker": ["artifact"],
    "token": ["tokens"],
    "equipment": ["equipment"],
    "vehicle": ["vehicle"],
    "artifact": ["artifact"],
}


def _themes_for(word: str) -> list[str]:
    """Look a concept up in the theme map, tolerating simple plurals."""
    if word in DEFAULT_THEME_MAP:
        return DEFAULT_THEME_MAP[word]
    if word.endswith("s") and word[:-1] in DEFAULT_THEME_MAP:
        return DEFAULT_THEME_MAP[word[:-1]]
    return []


def _cache_path(key: str) -> Path:
    safe = re.sub(r"[^a-z0-9._-]+", "_", key.lower()).strip("_") or "query"
    return EXPAND_CACHE_DIR / f"{safe}.json"


def _load_cached(key: str):
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) < 60 * 60 * 24:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cache(key: str, payload):
    try:
        _cache_path(key).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def _datamuse_expand(query: str) -> list[str]:
    if not query or requests is None:
        return []
    key = f"datamuse:{query.strip().lower()}"
    cached = _load_cached(key)
    if cached is not None:
        return cached
    try:
        url = f"https://api.datamuse.com/words?ml={requests.utils.quote(query)}&max=30"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json() or []
        words = [w.get("word", "") for w in data if isinstance(w, dict) and w.get("word")]
        words = [w for w in words if re.fullmatch(r"[a-z]+", w)]
        _save_cache(key, words[:20])
        return words[:20]
    except Exception:
        return []


def _llm_expand(query: str) -> list[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or requests is None:
        return []
    try:
        prompt = (
            "Return 10 concise MTG-relevant concepts for this prompt. "
            "Respond as a JSON array of lowercase words or short phrases. "
            f"Prompt: {query}"
        )
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
                "max_tokens": 250,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json().get("content", [{}])[0].get("text", "")
        # The model sometimes wraps the array in prose — extract it.
        match = re.search(r"\[.*\]", text, re.S)
        data = json.loads(match.group(0) if match else text)
        if isinstance(data, list):
            return [str(x).strip().lower() for x in data if str(x).strip()]
        logger.warning("LLM expansion returned non-list for %r: %.200s", query, text)
    except Exception as exc:
        logger.warning("LLM expansion error for %r: %s: %s",
                       query, type(exc).__name__, exc)
        return []
    return []


def expand_query(query: str, use_llm: bool = True) -> dict:
    """Expand a short query into related concepts and MTG themes."""
    cleaned = (query or "").strip()
    if not cleaned:
        return {"query": "", "concepts": [], "mtg_themes": []}

    base_words = [cleaned.lower()]
    if re.search(r"\s", cleaned):
        base_words.extend([w for w in re.split(r"[^a-zA-Z0-9]+", cleaned.lower()) if w])
    for phrase, synonyms in PROMPT_SYNONYMS.items():
        if phrase in cleaned.lower():
            base_words.extend(synonyms)
    datamuse_words = _datamuse_expand(cleaned)
    llm_words = _llm_expand(cleaned) if use_llm else []

    concepts = []
    for item in base_words + datamuse_words + llm_words:
        word = re.sub(r"[^a-z0-9]+", " ", str(item).lower()).strip()
        if word and word not in concepts:
            concepts.append(word)

    mtg_themes = []
    for concept in concepts:
        for theme in _themes_for(concept):
            if theme not in mtg_themes:
                mtg_themes.append(theme)
    for word in llm_words:
        if word and word not in mtg_themes:
            mtg_themes.append(word)

    return {
        "query": cleaned,
        "concepts": concepts[:30],
        "mtg_themes": mtg_themes[:20],
    }


def map_to_mtg(words: Iterable[str]) -> list[str]:
    """Map related words to MTG mechanics/types/themes."""
    themes = []
    for word in words:
        clean = re.sub(r"[^a-z0-9]+", " ", str(word).lower()).strip()
        if not clean:
            continue
        for theme in _themes_for(clean):
            if theme not in themes:
                themes.append(theme)
    return themes

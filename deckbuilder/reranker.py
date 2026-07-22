"""LLM re-ranking of card candidates for better thematic fit.

Part 2 implementation: Use Claude API to score candidate cards on thematic
and mechanical fit, re-ranking them before final selection. Falls back to
FTS ordering on any failure.

Constraints:
- Single API call per build (batches all candidates)
- Model scores only, never decides deck composition
- Graceful degradation (no API key, failed calls, no network)
- Validate responses against candidate set
- Cache by theme + candidate set to avoid re-paying
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class LLMReranker:
    """Score and re-rank card candidates using Claude API."""
    
    def __init__(self, model: str | None = None, api_key: str | None = None):
        """Initialize the reranker.
        
        Args:
            model: Anthropic model ID (e.g. 'claude-3-5-haiku-20241022').
                   Defaults to ANTHROPIC_MODEL env var or falls back to Haiku.
            api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
        """
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.cache = {}  # Simple in-memory cache
        self.calls_made = 0
        
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set; LLM re-ranking will be disabled")
    
    def rerank_candidates(
        self,
        theme: str,
        archetype: str,
        candidates: dict[str, list[dict]]
    ) -> dict[str, list[dict]] | None:
        """Re-rank candidates using LLM.
        
        Args:
            theme: User's theme description
            archetype: Resolved archetype (e.g. "midrange", "combo")
            candidates: Dict of pool_name -> list of card dicts
                       Each card must have: name, type_line, mana_cost, oracle_text
        
        Returns:
            Reranked candidates (same structure), or None if re-ranking failed/disabled.
            Falls back to original order on error.
        
        Score output should be JSON:
            {
                "scores": {
                    "card_name": {"thematic_fit": 0.8, "mechanical_fit": 0.7}
                }
            }
        """
        if not self.api_key:
            logger.debug("Re-ranking disabled (no API key)")
            return None
        
        # Generate cache key from theme + candidate hashes
        cache_key = self._cache_key(theme, archetype, candidates)
        if cache_key in self.cache:
            logger.debug(f"Re-ranking cache hit for theme '{theme[:40]}...'")
            return self.cache[cache_key]
        
        # Prepare compact candidate list for the model
        compact_candidates = self._prepare_compact_list(candidates)
        
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic library not installed; re-ranking disabled")
            return None
        
        client = anthropic.Anthropic(api_key=self.api_key)
        
        # Build the prompt
        prompt = self._build_prompt(theme, archetype, compact_candidates)
        
        try:
            logger.debug(f"Making API call to {self.model} for re-ranking")
            message = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            self.calls_made += 1
            response_text = message.content[0].text
        except Exception as e:
            logger.warning(f"Re-ranking API call failed: {e}; falling back to FTS order")
            return None
        
        # Parse and validate the response
        reranked = self._parse_and_apply_scores(response_text, candidates)
        if reranked is None:
            logger.warning("Failed to parse re-ranking response; falling back to FTS order")
            return None
        
        # Cache the result
        self.cache[cache_key] = reranked
        logger.debug(f"Re-ranking successful; cached for future use")
        return reranked
    
    def _cache_key(self, theme: str, archetype: str, candidates: dict) -> str:
        """Generate cache key from theme and candidate set."""
        # Hash all candidate names to create a stable key
        all_names = []
        for pool_cards in candidates.values():
            all_names.extend(c.get("name", "") for c in pool_cards)
        all_names_str = "|".join(sorted(set(all_names)))
        
        combined = f"{theme}||{archetype}||{all_names_str}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _prepare_compact_list(self, candidates: dict[str, list[dict]]) -> list[dict]:
        """Prepare a compact list of candidates for the model.
        
        Includes: name, type_line, mana_cost, oracle_text (nothing else).
        """
        compact = []
        for pool_name, cards in candidates.items():
            for card in cards:
                compact.append({
                    "name": card.get("name", "Unknown"),
                    "type_line": card.get("type_line", ""),
                    "mana_cost": card.get("mana_cost", ""),
                    "oracle_text": card.get("oracle_text", ""),
                })
        return compact
    
    def _build_prompt(self, theme: str, archetype: str, candidates: list[dict]) -> str:
        """Build the prompt for Claude to score candidates."""
        candidates_json = json.dumps(candidates, indent=2)
        
        return f"""You are scoring Magic: The Gathering cards for thematic and mechanical fit.

Theme: {theme}
Archetype: {archetype}

Below is a list of candidate cards. Score each on:
- **Thematic fit** (0.0–1.0): How well does this card fit the stated theme?
- **Mechanical fit** (0.0–1.0): How well does this card support the archetype?

Return ONLY valid JSON with this structure (no markdown, no extra text):
{{
    "scores": {{
        "Card Name": {{"thematic_fit": 0.8, "mechanical_fit": 0.75}},
        ...
    }}
}}

Candidate cards:
{candidates_json}

Score each card. Return ONLY the JSON object."""
    
    def _parse_and_apply_scores(
        self, response_text: str, original_candidates: dict[str, list[dict]]
    ) -> dict[str, list[dict]] | None:
        """Parse model response and apply scores to re-rank candidates.
        
        Returns re-ranked candidates (same structure) or None on parse failure.
        Validates that scored cards exist in the candidate set (discards hallucinations).
        """
        try:
            # Extract JSON from response (may have spurious whitespace)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Strip markdown code fence if present
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse re-ranking JSON: {e}")
            return None
        
        scores_dict = data.get("scores", {})
        if not scores_dict:
            logger.warning("Re-ranking response missing 'scores' key")
            return None
        
        # Build a map of card name -> score
        card_scores = {}
        for name, score_data in scores_dict.items():
            if isinstance(score_data, dict):
                thematic = score_data.get("thematic_fit", 0.5)
                mechanical = score_data.get("mechanical_fit", 0.5)
                card_scores[name] = (thematic + mechanical) / 2.0
        
        # Apply scores: re-rank each pool, discarding hallucinated cards
        reranked = {}
        for pool_name, cards in original_candidates.items():
            # Build set of valid card names (canonicalize to lowercase for matching)
            valid_names = {c.get("name", "").lower(): c for c in cards}
            
            # Sort by score, keeping only valid cards
            scored_cards = []
            for card in cards:
                card_name = card.get("name", "")
                card_name_lower = card_name.lower()
                
                # Check if model scored this card (exact match or case-insensitive)
                score = None
                for score_name, score_value in card_scores.items():
                    if score_name.lower() == card_name_lower:
                        score = score_value
                        break
                
                # If not scored by model, use a default low score
                if score is None:
                    score = 0.4  # Default for unscored cards (penalize hallucination-prone models)
                
                scored_cards.append((score, card))
            
            # Re-rank by score
            scored_cards.sort(key=lambda x: x[0], reverse=True)
            reranked[pool_name] = [card for _, card in scored_cards]
        
        return reranked


def get_reranker(model: str | None = None) -> LLMReranker:
    """Factory for creating a reranker instance."""
    return LLMReranker(model=model)

"""End-to-end tests for the deckbuilding pipeline.

These run fully OFFLINE against the bundled sample pool, so they exercise the
theme interpreter + engine without any network. They assert the *deckbuilding
rules* hold: colour identity, singleton, land base, curve, and legality.

Run:  python -m pytest tests/ -q      (or)      python tests/test_engine.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deckbuilder.theme as theme_module
import requests
from deckbuilder.theme import interpret
from deckbuilder.engine import build_deck, DeckBuilder
from deckbuilder.scryfall import ScryfallClient, detect_roles, build_query
from deckbuilder.expand import expand_query
from deckbuilder.theme import _extract_reference_cards


class StubCommanderClient(ScryfallClient):
    def __init__(self, commander_card=None, fallback=None):
        super().__init__(offline=True)
        self.commander_card = commander_card
        self.fallback = fallback

    def resolve_named_commander(self, name, fmt="commander", set_codes=None):
        return self.commander_card

    def find_commander(self, color_identity, theme_terms, fmt="commander", set_codes=None):
        return self.fallback


def _all_cards(deck):
    out = []
    for cat, cards in deck["categories"].items():
        for c in cards:
            out.extend([c] * c.get("count", 1))
    return out


def test_theme_colors_red_rising():
    p = interpret("A Red Rising rebellion rising up in brutal war against a "
                  "ruthless ruling hierarchy. Ambition, sacrifice, revolt.",
                  use_llm=False)
    # Rebellion/war -> Red should be present; ruthless ambition/sacrifice -> Black.
    assert "R" in p.colors, p.colors
    assert p.archetype in ("aggro", "aristocrats", "tokens", "midrange")
    assert any(t in p.oracle_terms for t in ["rebel", "revolt", "sacrifice", "soldier"])
    print("theme(red rising) ->", p.colors, p.archetype, p.oracle_terms)


def test_theme_colors_control():
    p = interpret("A patient blue-white control deck that outsmarts opponents "
                  "and denies their plans.", use_llm=False)
    assert "U" in p.colors and "W" in p.colors
    assert p.archetype == "control"
    print("theme(control) ->", p.colors, p.archetype)


def test_role_detection():
    assert "ramp" in detect_roles("Sorcery", "Search your library for a basic land card.")
    assert "draw" in detect_roles("Sorcery", "Draw two cards.")
    assert "removal" in detect_roles("Instant", "Destroy target creature.")
    assert "wipe" in detect_roles("Sorcery", "Destroy all creatures.")


def test_set_hint_is_parsed_from_prompt():
    params = interpret("Build me a red aggro deck from Modern Horizons 3 with fast creatures and burn.", use_llm=False)
    assert any("modern horizons" in s.lower() for s in params.set_names)


def test_semantic_expansion_enriches_short_prompts():
    result = expand_query("Iron Man", use_llm=False)
    assert result["concepts"]
    assert any(term in result["concepts"] for term in ["armor", "suit", "machine", "weapon"])
    assert "equipment" in result["mtg_themes"]


def test_commander_deck_is_legal():
    deck = build_deck("A swarm of goblins overrunning the board with reckless "
                      "fire and endless tokens.", fmt="commander",
                      offline=True, use_llm=False)
    colors = set(deck["params"]["colors"])
    cards = _all_cards(deck)

    # Colour identity: every card must fit the chosen identity.
    for c in cards:
        assert set(c["colors"]).issubset(colors), f"{c['name']} breaks colour id"

    # Singleton: no nonland card appears more than once (basics excepted).
    names = [c["name"] for c in cards if "Basic Land" not in c["type_line"]
             and c["type_line"] != "Basic Land"]
    from collections import Counter
    dupes = [n for n, k in Counter(names).items() if k > 1]
    assert not dupes, f"singleton violated: {dupes}"

    # There must be a real land base, and the deck should still be legal.
    assert deck["stats"]["lands"] >= 30
    print("commander deck:", deck["stats"]["total_cards"], "cards,",
          deck["stats"]["lands"], "lands, avg cmc", deck["stats"]["avg_cmc"])


def test_standard_deck_runs_multiples():
    deck = build_deck("Aggressive red goblins that attack fast and burn the "
                      "opponent out.", fmt="standard", offline=True, use_llm=False)
    # 60-card format should allow up to 4 copies of a card.
    maxcount = max((c.get("count", 1) for cat in deck["categories"].values()
                    for c in cat), default=1)
    assert maxcount > 1, "expected multiples in a 60-card deck"
    assert 20 <= deck["stats"]["lands"] <= 26
    print("standard deck:", deck["stats"]["total_cards"], "cards, max copies", maxcount)


def test_stats_are_consistent():
    deck = build_deck("A dark aristocrats cult sacrificing its own for power.",
                      fmt="commander", offline=True, use_llm=False)
    cards = _all_cards(deck)
    assert deck["stats"]["total_cards"] == len(cards)
    assert deck["stats"]["nonland_cards"] + deck["stats"]["lands"] == len(cards)
    print("stats consistent:", deck["stats"]["total_cards"])


def test_explicit_60_card_hint_sets_standard_format():
    deck = build_deck("Build me a 60-card red aggro deck with fast creatures and burn.",
                      fmt="commander", offline=True, use_llm=False,
                      deck_type_hint="60-card")
    assert deck["format"] == "standard"
    print("60-card hint ->", deck["format"])


def test_explicit_commander_hint_sets_commander_format():
    deck = build_deck("Build me a 100-card commander deck with a tribal theme.",
                      fmt="standard", offline=True, use_llm=False,
                      deck_type_hint="commander")
    assert deck["format"] == "commander"
    print("commander hint ->", deck["format"])


def test_different_prompts_produce_different_decks():
    """Regression: short prompts used to collapse to identical mono-red decks."""
    a = build_deck("Iron Man", fmt="commander", offline=True, use_llm=False)
    b = build_deck("Red Rising", fmt="commander", offline=True, use_llm=False)
    pa, pb = a["params"], b["params"]
    assert (pa["colors"], pa["archetype"], pa["oracle_terms"]) != \
           (pb["colors"], pb["archetype"], pb["oracle_terms"]), \
        "two unrelated prompts produced identical deck parameters"
    names_a = {c["name"] for cat in a["categories"].values() for c in cat}
    names_b = {c["name"] for cat in b["categories"].values() for c in cat}
    assert names_a != names_b, "two unrelated prompts produced identical decklists"
    print("prompt differentiation:",
          pa["colors"], pa["archetype"], "vs", pb["colors"], pb["archetype"])


def test_build_query_splits_type_words():
    query = build_query(["U"], card_type="Legendary Creature")
    assert "t:legendary" in query
    assert "t:creature" in query
    assert "t:Legendary Creature" not in query
    assert "t:Creature" not in query


def test_offline_type_filter_matches_legendary_artifact_creature():
    client = ScryfallClient(offline=True)
    sample_card = {
        "name": "Test Commander",
        "mana_cost": "{2}{U}",
        "cmc": 3,
        "colors": ["U"],
        "color_identity": ["U"],
        "type_line": "Legendary Artifact Creature",
        "oracle_text": "This card can be your commander.",
        "keywords": [],
        "power": "2",
        "toughness": "2",
        "image_uris": {},
        "edhrec_rank": 1,
        "produced_mana": [],
        "legalities": {"commander": "legal"},
        "scryfall_uri": "https://example.com",
    }
    client._sample = [sample_card]
    matches = client._offline_find(["U"], "Legendary Creature", [], [], [], None, 10)
    assert matches and matches[0]["name"] == "Test Commander"


def test_named_commander_sets_deck_colors():
    params = interpret("Use Iron Man as my commander", use_llm=False)
    commander_card = {
        "name": "Iron Man, Titan of Innovation",
        "mana_cost": "{2}{U}{R}",
        "cmc": 4,
        "colors": ["U", "R"],
        "color_identity": ["U", "R"],
        "type_line": "Legendary Artifact Creature",
        "oracle_text": "This card can be your commander.",
        "keywords": [],
        "power": "3",
        "toughness": "3",
        "image_uris": {},
        "edhrec_rank": 1,
        "produced_mana": [],
        "legalities": {"commander": "legal"},
        "scryfall_uri": "https://example.com",
    }
    deck = DeckBuilder(StubCommanderClient(commander_card=commander_card, fallback=commander_card), fmt="commander").build(params)
    assert deck["params"]["colors"] == ["U", "R"]
    assert deck["commander"]["name"] == "Iron Man, Titan of Innovation"


def test_unknown_named_commander_yields_warning_and_fallback():
    params = interpret("Use Definitely Not A Real Commander as my commander", use_llm=False)
    fallback_card = {
        "name": "Fallback Commander",
        "mana_cost": "{2}{W}",
        "cmc": 3,
        "colors": ["W"],
        "color_identity": ["W"],
        "type_line": "Legendary Creature",
        "oracle_text": "This card can be your commander.",
        "keywords": [],
        "power": "2",
        "toughness": "2",
        "image_uris": {},
        "edhrec_rank": 1,
        "produced_mana": [],
        "legalities": {"commander": "legal"},
        "scryfall_uri": "https://example.com",
    }
    deck = DeckBuilder(StubCommanderClient(commander_card=None, fallback=fallback_card), fmt="commander").build(params)
    assert deck["warnings"]
    assert any("resolve" in w.lower() or "fallback" in w.lower() for w in deck["warnings"])
    assert deck["commander"]["name"] == "Fallback Commander"


def test_reference_cards_are_parsed_from_text():
    refs = _extract_reference_cards(["1 Lightning Bolt", "2 Counterspell", "https://www.moxfield.com/decks/example"])
    assert "Lightning Bolt" in refs
    assert "Counterspell" in refs


def test_reference_cards_boost_matching_cards():
    builder = DeckBuilder(fmt="commander")
    card = {"name": "Lightning Bolt", "mana_cost": "{R}", "cmc": 1, "type_line": "Instant", "oracle_text": "Deal 3 damage to any target.", "keywords": [], "color_identity": ["R"], "colors": ["R"], "roles": [], "image": None, "edhrec_rank": 1, "is_land": False, "is_creature": False, "types": ["Instant"], "legalities": {}, "scryfall_uri": "", "power": None, "toughness": None}
    score = builder._reference_score(card, ["Lightning Bolt", "Counterspell"])
    assert score > 0


def test_reference_urls_are_parsed_from_page(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse('<div data-name="Lightning Bolt"></div><div class="card-name">Counterspell</div>'))
    refs = theme_module._extract_reference_cards(["https://www.moxfield.com/decks/example"])
    assert "Lightning Bolt" in refs
    assert "Counterspell" in refs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} tests passed.")
    sys.exit(1 if failed else 0)

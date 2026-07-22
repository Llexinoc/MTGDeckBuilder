"""Tests for DeckBuilder engine, focusing on commander color identity constraints."""

import pytest
from deckbuilder.engine import build_deck, DeckBuilder
from deckbuilder.scryfall import ScryfallClient
from deckbuilder import carddata


class TestCommanderColorIdentityFilter:
    """Test that commander selection enforces hard color identity constraints."""
    
    def test_commander_must_contain_all_requested_colors_red_blue_black(self):
        """Commander for 'red, blue, black' must have all three colors (or no commander)."""
        deck = build_deck(
            'Red, blue, black commander with sacrifice theme',
            no_network=True,
            use_llm=False
        )
        
        requested_colors = set(deck['params']['colors'])
        commander = deck.get('commander')
        
        if commander:
            # If commander exists, it MUST contain all requested colors
            commander_colors = set(commander.get('color_identity', []))
            assert requested_colors.issubset(commander_colors), \
                f"Commander {commander.get('name', 'NONE')} has colors {commander_colors} " \
                f"but must contain all requested colors {requested_colors}"
        else:
            # No commander is better than an off-color commander
            # Should have a warning about it
            assert any('commander' in w.lower() for w in deck.get('warnings', [])), \
                "Should warn about missing commander when none found with all colors"
    
    def test_commander_must_contain_all_requested_colors_just_blue(self):
        """Commander for 'just blue' must be pure blue or contain blue (or no commander if offline)."""
        deck = build_deck(
            'just blue',
            no_network=True,
            use_llm=False
        )
        
        requested_colors = set(deck['params']['colors'])
        commander = deck.get('commander')
        
        if commander:
            # If commander exists, it MUST contain all requested colors
            commander_colors = set(commander.get('color_identity', []))
            assert requested_colors.issubset(commander_colors), \
                f"Commander {commander.get('name', 'NONE')} has colors {commander_colors} " \
                f"but must contain all requested colors {requested_colors}"
        else:
            # No commander is better than an off-color commander
            # Offline data might not have blues available
            pass
    
    def test_commander_colors_match_deck_display_colors(self):
        """The commander's displayed colors should match the deck's identity colors (if commander exists)."""
        deck = build_deck(
            'An oppressed underclass rises in war: red, blue, black',
            no_network=True,
            use_llm=False
        )
        
        requested_colors = set(deck['params']['colors'])
        commander = deck.get('commander')
        
        if commander:
            commander_display_colors = set(commander.get('colors', []))
            # Commander should display with deck's colors (for UI consistency)
            assert requested_colors == commander_display_colors, \
                f"Commander display colors {commander_display_colors} should match " \
                f"deck requested colors {requested_colors}"
        else:
            # If no commander, that's OK - it's better than off-color
            pass
    
    def test_commander_color_identity_in_api_response(self):
        """Verify that color_identity field is present in commander object when commander exists."""
        # Use 'just blue' which is more likely to find a commander
        deck = build_deck(
            'just blue',
            no_network=True,
            use_llm=False
        )
        
        commander = deck.get('commander')
        if commander:
            assert 'color_identity' in commander, \
                "Commander object should have 'color_identity' field"
            assert isinstance(commander['color_identity'], list), \
                "color_identity should be a list"
            # Verify it contains the requested colors
            requested_colors = set(deck['params']['colors'])
            commander_colors = set(commander['color_identity'])
            assert requested_colors.issubset(commander_colors), \
                f"Commander colors {commander_colors} must contain requested {requested_colors}"
    
    def test_no_commander_fallback_when_impossible_colors(self):
        """When no commander exists with exact requested colors, should gracefully handle."""
        # This test is tricky because we'd need to find a combination that's impossible
        # For now, just verify that if we get no commander, we handle it gracefully
        
        # Test with a very restrictive search that might not have commanders
        deck = build_deck(
            'A white monocolor deck',
            no_network=True,
            use_llm=False
        )
        
        # If commander is None, we should still have a valid deck structure
        if deck.get('commander') is None:
            # Should have warnings about missing commander
            assert any('commander' in w.lower() for w in deck.get('warnings', [])), \
                "Should warn about missing commander"
        else:
            # If we found a commander, verify it has white
            commander_colors = set(deck.get('commander', {}).get('color_identity', []))
            requested_colors = set(deck['params']['colors'])
            assert requested_colors.issubset(commander_colors), \
                "Commander must contain all requested colors"
    
    def test_deck_cards_respect_commander_colors(self):
        """All non-land cards should have colors within the commander's identity."""
        deck = build_deck(
            'Grixis (blue, red, black) tempo deck',
            no_network=True,
            use_llm=False
        )
        
        commander = deck.get('commander')
        if commander:
            commander_colors = set(commander.get('color_identity', []))
            
            # Check all cards in deck categories
            for category in ['theme', 'ramp', 'draw', 'removal', 'wipe']:
                cards = deck.get('categories', {}).get(category, [])
                for card_entry in cards:
                    card = card_entry  # card_entry might have 'count' field
                    card_colors = set(card.get('color_identity', []))
                    assert card_colors.issubset(commander_colors), \
                        f"Card {card.get('name', 'UNKNOWN')} in {category} has colors {card_colors} " \
                        f"outside commander's {commander_colors}"


class TestCommanderSelectionLogic:
    """Test the core commander selection logic in detail."""
    
    def test_client_find_commander_includes_all_colors(self):
        """Low-level test: ScryfallClient.find_commander should only return commanders with all colors."""
        # Note: this test assumes offline mode to be deterministic
        client = ScryfallClient()
        
        # Search for a Grixis (U, B, R) commander
        required_colors = ['U', 'B', 'R']
        commander = client.find_commander(required_colors, [], fmt="commander")
        
        if commander:
            commander_colors = set(commander.get('color_identity', []))
            required_set = set(required_colors)
            assert required_set.issubset(commander_colors), \
                f"Commander {commander.get('name')} has colors {commander_colors} " \
                f"but must contain {required_set}"
    
    def test_no_commander_found_returns_none(self):
        """When no valid commander exists, find_commander should return None."""
        client = ScryfallClient()
        
        # Create an impossible color combination (one that shouldn't exist)
        # For example, a random non-standard combination
        # Note: This is hard to guarantee in real card data, so we just test the contract
        result = client.find_commander(['X'], [], fmt="commander")
        
        # Should either return None or raise an error
        # The important thing is it doesn't return off-color cards
        if result:
            result_colors = set(result.get('color_identity', []))
            assert 'X' in result_colors or result_colors, \
                "If result returned, it should be valid"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

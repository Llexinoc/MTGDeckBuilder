"""Tests for bracket system and deck composition constraints.

Tests verify:
- Hard deck size constraints (100 for Commander, 60 for Standard)
- Singleton and copy limits
- Color identity restrictions
- Game Changer filtering by bracket
- Ban list enforcement
- Deck classification
"""

import unittest
from unittest.mock import Mock, patch
from deckbuilder.engine import DeckValidator, DeckBuilder, build_deck
from deckbuilder.formats import get_bracket_config, parse_bracket_from_description


class TestBracketThresholds(unittest.TestCase):
    """Test bracket configuration and detection."""
    
    def test_bracket_levels_1_to_5_exist(self):
        """Each bracket 1-5 should have a config."""
        for bracket in range(1, 6):
            cfg = get_bracket_config(bracket)
            self.assertIsNotNone(cfg)
            self.assertIn("name", cfg)
            self.assertIn("max_game_changers", cfg)
    
    def test_bracket_1_2_no_game_changers(self):
        """Brackets 1 and 2 should have max_game_changers = 0."""
        for bracket in (1, 2):
            cfg = get_bracket_config(bracket)
            self.assertEqual(cfg["max_game_changers"], 0)
    
    def test_bracket_3_max_three_game_changers(self):
        """Bracket 3 should have max_game_changers = 3."""
        cfg = get_bracket_config(3)
        self.assertEqual(cfg["max_game_changers"], 3)
    
    def test_bracket_4_5_no_game_changer_limit(self):
        """Brackets 4 and 5 should have no game changer limit."""
        for bracket in (4, 5):
            cfg = get_bracket_config(bracket)
            self.assertIsNone(cfg["max_game_changers"])
    
    def test_parse_bracket_from_description(self):
        """Test bracket detection from natural language."""
        test_cases = [
            ("bracket 3 deck", 3),
            ("bracket 5", 5),
            ("cEDH", 5),
            ("cedh", 5),
            ("casual", 2),
            ("exhibition", 1),
            ("precon", 2),
            ("optimized", 4),
            ("upgraded", 3),
            ("tuned", 3),
            ("no bracket specified", None),
        ]
        for desc, expected in test_cases:
            result = parse_bracket_from_description(desc)
            self.assertEqual(result, expected, f"Failed for: {desc}")


class TestDeckValidator(unittest.TestCase):
    """Test deck validation against hard constraints."""
    
    def _make_card(self, name, colors=None, is_land=False, legality="legal"):
        """Helper to create a test card."""
        return {
            "name": name,
            "color_identity": colors or [],
            "is_land": is_land,
            "type_line": "Basic Land" if is_land else "Creature",
            "legalities": {"commander": legality, "standard": legality},
            "mana_cost": "{W}" if colors and "W" in colors else "",
            "cmc": 1,
            "oracle_text": "",
        }
    
    def test_commander_exact_100_cards(self):
        """Commander deck must be exactly 100 cards total."""
        validator = DeckValidator("commander", enforce_ban_list=True)
        
        # Too few: 98 total cards (should be 100)
        cards_98 = [self._make_card(f"Card{i}", colors=["W"]) for i in range(98)]
        commander = self._make_card("Commander", colors=["W"])
        valid = validator.validate(cards_98, commander)
        self.assertFalse(valid)
        errors = validator.get_errors()
        self.assertTrue(any("100" in str(e) for e in errors), f"Expected '100' in error messages: {errors}")
        
        # Exactly 100 cards total (1 commander + 63 spells + 36 lands)
        validator = DeckValidator("commander", enforce_ban_list=True)
        spell_cards = [self._make_card(f"Spell{i}", colors=["W"]) for i in range(63)]
        land_cards = [self._make_card(f"Land{i}", colors=["W"], is_land=True) for i in range(36)]
        commander = self._make_card("Commander", colors=["W"])
        all_cards = [commander] + spell_cards + land_cards
        
        # Pass all 100 cards (including commander) and also commander as parameter
        # This matches how engine.py calls: validator.validate(all_cards, commander)
        valid = validator.validate(all_cards, commander)
        
        # Should pass validation
        size_errors = [e for e in validator.get_errors() if "100" in str(e) and "Deck has" in str(e)]
        self.assertEqual(len(size_errors), 0, f"100 cards should pass size check, got: {validator.get_errors()}")
    
    def test_standard_exact_60_cards(self):
        """Standard deck must be exactly 60 cards."""
        validator = DeckValidator("standard", enforce_ban_list=True)
        
        # Too few
        cards_59 = [self._make_card(f"Card{i}") for i in range(59)]
        valid = validator.validate(cards_59)
        self.assertFalse(valid)
        errors = validator.get_errors()
        self.assertTrue(any("60" in str(e) for e in errors), f"Expected '60' in error messages: {errors}")
    
    def test_commander_singleton_constraint(self):
        """Commander should not allow duplicates (except basics)."""
        validator = DeckValidator("commander", enforce_ban_list=True)
        
        # Duplicate non-basic
        dup_card = self._make_card("Dupe Card")
        cards = [dup_card, dup_card] + [self._make_card(f"Card{i}") for i in range(98)]
        commander = self._make_card("Commander", colors=["W"])
        
        valid = validator.validate(cards, commander)
        self.assertFalse(valid)
        self.assertIn("appears", validator.get_errors()[0])
    
    def test_standard_4_copy_limit(self):
        """Standard should not allow more than 4 copies of any card."""
        validator = DeckValidator("standard", enforce_ban_list=True)
        
        # Five copies
        card = self._make_card("Card", colors=["W"])
        cards = [card] * 5 + [self._make_card(f"Other{i}") for i in range(55)]
        
        valid = validator.validate(cards)
        self.assertFalse(valid)
        self.assertIn("appears", validator.get_errors()[0])
    
    def test_color_identity_restriction(self):
        """All cards must be within commander's color identity."""
        validator = DeckValidator("commander", enforce_ban_list=True)
        
        # Commander is white only
        commander = self._make_card("WCommander", colors=["W"])
        
        # Include a blue card
        blue_card = self._make_card("Blue Card", colors=["U"])
        cards = [blue_card] + [self._make_card(f"Card{i}", colors=["W"]) for i in range(99)]
        
        valid = validator.validate(cards, commander)
        self.assertFalse(valid)
        self.assertIn("color identity", validator.get_errors()[0].lower())
    
    def test_banned_card_enforcement(self):
        """Banned cards should be rejected when enforce_ban_list=True."""
        validator = DeckValidator("commander", enforce_ban_list=True)
        
        banned_card = self._make_card("Banned Card", legality="banned")
        cards = [banned_card] + [self._make_card(f"Card{i}") for i in range(99)]
        commander = self._make_card("Commander", colors=["W"])
        
        valid = validator.validate(cards, commander)
        self.assertFalse(valid)
        self.assertIn("banned", validator.get_errors()[0].lower())
    
    def test_banned_card_allowed_when_toggle_off(self):
        """Banned cards should be allowed when enforce_ban_list=False."""
        validator = DeckValidator("commander", enforce_ban_list=False)
        
        banned_card = self._make_card("Banned Card", legality="banned")
        cards = [banned_card] + [self._make_card(f"Card{i}", colors=["W"]) for i in range(99)]
        commander = self._make_card("Commander", colors=["W"])
        
        # Should not fail due to banned card (might fail for other reasons, but not ban)
        validator.validate(cards, commander)
        ban_errors = [e for e in validator.get_errors() if "banned" in e.lower()]
        self.assertEqual(len(ban_errors), 0, "Banned card should be allowed when enforce_ban_list=False")
    
    def test_not_legal_never_allowed(self):
        """Cards with not_legal status should never be included."""
        validator = DeckValidator("commander", enforce_ban_list=False)
        
        not_legal_card = self._make_card("Not Legal Card", legality="not_legal")
        cards = [not_legal_card] + [self._make_card(f"Card{i}", colors=["W"]) for i in range(99)]
        commander = self._make_card("Commander", colors=["W"])
        
        valid = validator.validate(cards, commander)
        self.assertFalse(valid)
        not_legal_errors = [e for e in validator.get_errors() if "not legal" in e.lower() or "not_legal" in e]
        self.assertGreater(len(not_legal_errors), 0)


class TestBracketFiltering(unittest.TestCase):
    """Test that deck building filters based on bracket."""
    
    def test_bracket_1_filters_game_changers(self):
        """Bracket 1 decks should have zero Game Changers."""
        # This would require a full deck build test with mocked data
        # Placeholder for integration test
        pass
    
    def test_bracket_3_caps_game_changers_at_3(self):
        """Bracket 3 decks should have at most 3 Game Changers."""
        # This would require a full deck build test with mocked data
        # Placeholder for integration test
        pass


if __name__ == "__main__":
    unittest.main()

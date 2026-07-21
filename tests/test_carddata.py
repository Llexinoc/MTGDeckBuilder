"""Tests for the Scryfall card data layer.

Uses a synthetic JSONL.GZ fixture to test filtering, deduplication,
MDFC handling, and color identity constraints without hitting live Scryfall.
"""

import gzip
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from deckbuilder.carddata import (
    BulkDataFetcher,
    _build_db,
    _extract_card_faces_text,
    _is_castable,
    by_name,
    process_card,
    search,
    within_identity,
)


@pytest.fixture
def synthetic_fixture() -> Path:
    """Create a synthetic gzipped JSONL fixture for testing."""
    cards = [
        # 1. Legendary creature (castable, can be commander)
        {
            "oracle_id": "11111111-1111-1111-1111-111111111111",
            "name": "Test Legend",
            "mana_cost": "{1}{W}",
            "cmc": 2,
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Whenever a creature enters the battlefield under your control, you gain 1 life.",
            "power": "2",
            "toughness": "3",
            "color_identity": ["W"],
            "colors": ["W"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2023-01-01",
            "edhrec_rank": 1000,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {"normal": "http://example.com/1.jpg"},
            "scryfall_uri": "http://scryfall.com/1",
            "prices": {"usd": "1.50"},
            "card_faces": [],
        },
        # 2. Same card, different printing (duplicate)
        {
            "oracle_id": "11111111-1111-1111-1111-111111111111",
            "name": "Test Legend",
            "mana_cost": "{1}{W}",
            "cmc": 2,
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Whenever a creature enters the battlefield under your control, you gain 1 life.",
            "power": "2",
            "toughness": "3",
            "color_identity": ["W"],
            "colors": ["W"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2022-01-01",  # Older printing
            "edhrec_rank": 1000,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "digital": True,  # Digital version - should be deprioritized
            "image_uris": {"normal": "http://example.com/1-digital.jpg"},
            "scryfall_uri": "http://scryfall.com/1-digital",
            "prices": {"usd": "1.00"},
            "card_faces": [],
        },
        # 3. Non-English printing (should be filtered)
        {
            "oracle_id": "11111111-1111-1111-1111-111111111111",
            "name": "Test Legend",
            "mana_cost": "{1}{W}",
            "cmc": 2,
            "type_line": "Legendary Creature — Human Cleric",
            "oracle_text": "Whenever a creature enters the battlefield under your control, you gain 1 life.",
            "power": "2",
            "toughness": "3",
            "color_identity": ["W"],
            "colors": ["W"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2024-01-01",  # Most recent, but non-English
            "edhrec_rank": 1000,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "de",  # German - should be filtered
            "oversized": False,
            "image_uris": {"normal": "http://example.com/1-de.jpg"},
            "scryfall_uri": "http://scryfall.com/1-de",
            "prices": {"usd": "1.50"},
            "card_faces": [],
        },
        # 4. Token (should be filtered)
        {
            "oracle_id": "22222222-2222-2222-2222-222222222222",
            "name": "Goblin Token",
            "mana_cost": "",
            "cmc": 0,
            "type_line": "Token Creature — Goblin",
            "oracle_text": "",
            "power": "1",
            "toughness": "1",
            "color_identity": ["R"],
            "colors": ["R"],
            "set": "TST",
            "rarity": "common",
            "released_at": "2023-01-01",
            "edhrec_rank": None,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "token",  # Token layout - should be filtered
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {},
            "scryfall_uri": "http://scryfall.com/2",
            "prices": {},
            "card_faces": [],
        },
        # 5. Emblem (should be filtered)
        {
            "oracle_id": "33333333-3333-3333-3333-333333333333",
            "name": "Emblem",
            "mana_cost": "",
            "cmc": 0,
            "type_line": "Emblem",
            "oracle_text": "You get an emblem.",
            "color_identity": [],
            "colors": [],
            "set": "TST",
            "rarity": "common",
            "released_at": "2023-01-01",
            "edhrec_rank": None,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "emblem",  # Emblem layout - should be filtered
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {},
            "scryfall_uri": "http://scryfall.com/3",
            "prices": {},
            "card_faces": [],
        },
        # 6. Oversized (should be filtered)
        {
            "oracle_id": "44444444-4444-4444-4444-444444444444",
            "name": "Oversized Card",
            "mana_cost": "{5}",
            "cmc": 5,
            "type_line": "Creature — Giant",
            "oracle_text": "This is oversized.",
            "power": "10",
            "toughness": "10",
            "color_identity": ["G"],
            "colors": ["G"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2023-01-01",
            "edhrec_rank": None,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": True,  # Oversized - should be filtered
            "image_uris": {},
            "scryfall_uri": "http://scryfall.com/4",
            "prices": {},
            "card_faces": [],
        },
        # 7. Reversible card with no oracle_id (should be filtered)
        {
            "oracle_id": None,  # Missing oracle_id - should be filtered
            "name": "Reversible Card",
            "mana_cost": "{3}{U}",
            "cmc": 4,
            "type_line": "Creature — Wizard",
            "oracle_text": "This is a reversible card duplicate.",
            "power": "2",
            "toughness": "2",
            "color_identity": ["U"],
            "colors": ["U"],
            "set": "TST",
            "rarity": "common",
            "released_at": "2023-01-01",
            "edhrec_rank": None,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {},
            "scryfall_uri": "http://scryfall.com/5",
            "prices": {},
            "card_faces": [],
        },
        # 8. MDFC with text only on faces (should join text)
        {
            "oracle_id": "55555555-5555-5555-5555-555555555555",
            "name": "Modal Creature",
            "mana_cost": None,  # No top-level cost; it's on faces
            "cmc": 0,
            "type_line": None,  # No top-level type; it's on faces
            "oracle_text": None,  # No top-level text; it's on faces
            "color_identity": ["B", "R"],
            "colors": ["B", "R"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2023-01-01",
            "edhrec_rank": 5000,
            "legalities": {"commander": "legal", "standard": None},
            "layout": "modal_dfc",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {},
            "scryfall_uri": "http://scryfall.com/6",
            "prices": {},
            "card_faces": [
                {
                    "name": "Modal Side A",
                    "mana_cost": "{1}{B}",
                    "type_line": "Creature — Zombie",
                    "oracle_text": "When this enters the battlefield, create a 2/2 black Zombie token.",
                },
                {
                    "name": "Modal Side B",
                    "mana_cost": "{2}{R}",
                    "type_line": "Creature — Elemental",
                    "oracle_text": "Haste. {T}: This deals 2 damage to any target.",
                },
            ],
        },
        # 9. Non-legendary creature (cannot be commander)
        {
            "oracle_id": "66666666-6666-6666-6666-666666666666",
            "name": "Regular Creature",
            "mana_cost": "{2}{U}",
            "cmc": 3,
            "type_line": "Creature — Wizard",
            "oracle_text": "Flying.",
            "power": "1",
            "toughness": "3",
            "color_identity": ["U"],
            "colors": ["U"],
            "set": "TST",
            "rarity": "common",
            "released_at": "2023-01-01",
            "edhrec_rank": 500,
            "legalities": {"commander": "legal", "standard": "legal"},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {"normal": "http://example.com/6.jpg"},
            "scryfall_uri": "http://scryfall.com/6",
            "prices": {"usd": "0.25"},
            "card_faces": [],
        },
        # 10. Card with "can be your commander" in rules text
        {
            "oracle_id": "77777777-7777-7777-7777-777777777777",
            "name": "Secret Legend",
            "mana_cost": "{3}{G}",
            "cmc": 4,
            "type_line": "Creature — Elf Druid",
            "oracle_text": "Secret Legend can be your commander. {T}: Add {G}.",
            "power": "2",
            "toughness": "2",
            "color_identity": ["G"],
            "colors": ["G"],
            "set": "TST",
            "rarity": "rare",
            "released_at": "2023-01-01",
            "edhrec_rank": 8000,
            "legalities": {"commander": "legal", "standard": None},
            "layout": "normal",
            "set_type": "expansion",
            "lang": "en",
            "oversized": False,
            "image_uris": {"normal": "http://example.com/7.jpg"},
            "scryfall_uri": "http://scryfall.com/7",
            "prices": {"usd": "2.00"},
            "card_faces": [],
        },
    ]

    # Write to gzipped JSONL
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl.gz", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
        for card in cards:
            f.write(json.dumps(card) + "\n")

    return tmp_path


@pytest.fixture
def test_db(synthetic_fixture) -> Path:
    """Build a test database from the synthetic fixture."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp_db_path = Path(tmp_db.name)
    tmp_db.close()

    # Use all_cards mode to test deduplication
    _build_db(tmp_db_path, synthetic_fixture, "all_cards", "2023-01-01T00:00:00Z")
    return tmp_db_path


class TestCastableFilters:
    """Test that non-castable cards are properly filtered."""

    def test_non_english_filtered(self, synthetic_fixture):
        """Non-English cards should be filtered."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        german_card = next(c for c in cards if c.get("lang") == "de")
        assert not _is_castable(german_card)

    def test_token_filtered(self, synthetic_fixture):
        """Tokens should be filtered."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        token = next(c for c in cards if c.get("layout") == "token")
        assert not _is_castable(token)

    def test_emblem_filtered(self, synthetic_fixture):
        """Emblems should be filtered."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        emblem = next(c for c in cards if c.get("layout") == "emblem")
        assert not _is_castable(emblem)

    def test_oversized_filtered(self, synthetic_fixture):
        """Oversized cards should be filtered."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        oversized = next(c for c in cards if c.get("oversized"))
        assert not _is_castable(oversized)

    def test_no_oracle_id_filtered(self, synthetic_fixture):
        """Cards without oracle_id should be filtered."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        no_id = next(c for c in cards if c.get("oracle_id") is None)
        assert not _is_castable(no_id)

    def test_real_card_castable(self, synthetic_fixture):
        """Real cards should pass the castable filter."""
        cards = [json.loads(line.strip()) for line in gzip.open(synthetic_fixture, "rt")]
        legend = next(c for c in cards if c.get("name") == "Test Legend" and c.get("lang") == "en")
        assert _is_castable(legend)


class TestDuplicateCollapse:
    """Test that duplicate printings are properly collapsed."""

    def test_duplicate_collapses_to_preferred(self, test_db):
        """Multiple printings of same card should collapse to non-digital, most recent."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        
        rows = conn.execute("SELECT * FROM cards WHERE name = 'Test Legend'").fetchall()
        conn.close()

        assert len(rows) == 1, "Should have exactly one row (deduplicated)"
        card = dict(rows[0])
        assert card["released_at"] == "2023-01-01", "Should prefer most recent"


class TestMDFCTextJoining:
    """Test that MDFC text is properly joined from card_faces."""

    def test_mdfc_oracle_text_joined(self):
        """MDFC text should be joined with ' // '."""
        mdfc_card = {
            "name": "Test MDFC",
            "mana_cost": None,
            "type_line": None,
            "oracle_text": None,
            "card_faces": [
                {
                    "mana_cost": "{1}{B}",
                    "type_line": "Creature — Zombie",
                    "oracle_text": "Text A",
                },
                {
                    "mana_cost": "{2}{R}",
                    "type_line": "Creature — Elemental",
                    "oracle_text": "Text B",
                },
            ],
        }

        oracle, mana, type_line = _extract_card_faces_text(mdfc_card)
        assert oracle == "Text A // Text B"
        assert mana == "{1}{B}{2}{R}"
        assert type_line == "Creature — Zombie // Creature — Elemental"

    def test_mdfc_in_database(self, test_db):
        """MDFC card in database should have joined text."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row

        row = conn.execute("SELECT * FROM cards WHERE name = 'Modal Creature'").fetchone()
        conn.close()

        assert row is not None
        assert " // " in row["oracle_text"], "MDFC text should be joined"
        assert "When this enters" in row["oracle_text"]
        assert "Haste" in row["oracle_text"]


class TestCommanderDetection:
    """Test that commander-eligible cards are properly detected."""

    def test_legendary_creature_is_commander(self, test_db):
        """Legendary creatures should be marked as can_be_commander."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM cards WHERE name = 'Test Legend'"
        ).fetchone()
        conn.close()

        assert row["can_be_commander"] == 1

    def test_can_be_commander_text_detected(self, test_db):
        """Cards with 'can be your commander' text should be detected."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM cards WHERE name = 'Secret Legend'"
        ).fetchone()
        conn.close()

        assert row["can_be_commander"] == 1

    def test_regular_creature_not_commander(self, test_db):
        """Non-legendary creatures should not be marked as can_be_commander."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM cards WHERE name = 'Regular Creature'"
        ).fetchone()
        conn.close()

        assert row["can_be_commander"] == 0


class TestIndexStatus:
    """Test overall index content and structure."""

    def test_only_castable_cards_in_index(self, test_db):
        """Only castable cards should be in the final index."""
        conn = sqlite3.connect(test_db)
        count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        conn.close()

        # From fixture: 10 cards total
        # Filtered: token, emblem, oversized, no oracle_id, 2 duplicates of legend (same oracle_id)
        # Remaining: legend (1), regular creature (1), MDFC (1), secret legend (1) = 4
        assert count == 4, f"Expected 4 castable cards, got {count}"

    def test_fts5_index_built(self, test_db):
        """FTS5 virtual table should be populated."""
        conn = sqlite3.connect(test_db)
        rows = conn.execute("SELECT COUNT(*) FROM cards_fts").fetchone()[0]
        conn.close()

        assert rows == 4, "FTS5 index should have all castable cards"

    def test_legality_columns_populated(self, test_db):
        """Legality columns should be populated correctly."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT * FROM cards WHERE legal_commander = 1"
        ).fetchall()
        conn.close()

        assert len(rows) > 0, "Should have commander-legal cards"


class TestSearchAPI:
    """Test the public search API."""

    def test_search_by_text(self, test_db):
        """Search should find cards by oracle text."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        results = search(conn, "Haste", fmt="commander")
        conn.close()

        assert len(results) > 0, "Should find cards with 'Haste' in text"
        assert any("Modal" in r["name"] for r in results), "Should include MDFC"

    def test_by_name_lookup(self, test_db):
        """by_name should find cards by exact name."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        card = by_name(conn, "Test Legend")
        conn.close()

        assert card is not None
        assert card["name"] == "Test Legend"

    def test_within_identity_filters_colors(self, test_db):
        """within_identity should filter by color subset."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        
        # White identity: should find White cards
        white_cards = within_identity(conn, "W", fmt="commander")
        white_names = {c["name"] for c in white_cards}
        assert "Test Legend" in white_names
        
        # Blue identity: should find Blue cards
        blue_cards = within_identity(conn, "U", fmt="commander")
        blue_names = {c["name"] for c in blue_cards}
        assert "Regular Creature" in blue_names
        
        conn.close()

    def test_color_identity_json_parsing(self, test_db):
        """Color identity should be parsed from JSON storage."""
        conn = sqlite3.connect(test_db)
        conn.row_factory = sqlite3.Row
        card = by_name(conn, "Modal Creature")
        conn.close()

        assert isinstance(card["color_identity"], list)
        assert set(card["color_identity"]) == {"B", "R"}

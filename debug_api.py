#!/usr/bin/env python3
"""Debug Scryfall API responses."""

from deckbuilder.scryfall import ScryfallClient, normalize, _cached_get

client = ScryfallClient(offline=False)

# Try searching for theme cards
theme_cards = client.find_cards(
    ["R", "W", "B"],
    card_type="Creature",
    oracle_terms=["rebel", "revolt"],
    fmt="commander",
    limit=5
)

print("Theme cards found:")
for card in theme_cards:
    print(f"  {card['name']}: image={card.get('image', 'MISSING')}")

# Try searching for draw cards
draw_cards = client.find_cards(
    ["R", "W", "B"],
    oracle_terms=["draw a card"],
    fmt="commander",
    limit=5
)

print("\nDraw cards found:")
for card in draw_cards:
    print(f"  {card['name']}: image={card.get('image', 'MISSING')}")

# Direct search result
print("\n\nDirect Scryfall search for Faithless Looting:")
query_result = _cached_get(
    "https://api.scryfall.com/cards/search",
    {"q": 'name:"Faithless Looting"', "unique": "cards"}
)
if query_result and query_result.get("data"):
    raw_card = query_result["data"][0]
    normalized = normalize(raw_card)
    print(f"Raw image_uris: {raw_card.get('image_uris')}")
    print(f"Normalized image: {normalized.get('image')}")

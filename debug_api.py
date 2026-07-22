#!/usr/bin/env python3
"""Debug the API response."""

from deckbuilder.scryfall import _cached_get, API_BASE, build_query

# Test the raw query
query = build_query(['R', 'B', 'U'], card_type='Legendary Creature', fmt='commander')
print(f"Query: {query}")

params = {"q": query, "order": "edhrec", "unique": "cards", "dir": "asc"}
data = _cached_get(f"{API_BASE}/cards/search", params, no_network=False)

if data and data.get("data"):
    print(f"\nFound {len(data['data'])} raw cards")
    print("\nFirst 20 cards:")
    for i, card in enumerate(data['data'][:20]):
        ci = card.get('color_identity', [])
        print(f"  {i+1}. {card.get('name')}: {ci}")
else:
    print("No data returned")


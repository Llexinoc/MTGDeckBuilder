#!/usr/bin/env python3
"""Check for Grixis (R+B+U) commanders."""

from deckbuilder.scryfall import _cached_get, API_BASE, build_query

# Get all legendary creatures that could have R, B, U
query = build_query(['R', 'B', 'U'], card_type='Legendary Creature', fmt='commander')
params = {"q": query, "order": "edhrec", "unique": "cards", "dir": "asc"}
url = f"{API_BASE}/cards/search"

data = _cached_get(url, params, no_network=False)

if data:
    cards = data.get('data', [])
    
    # Look for cards that have ALL THREE colors R, B, U
    grixis = [c for c in cards if all(color in c.get('color_identity', []) for color in ['R', 'B', 'U'])]
    print(f"Cards with ALL three colors R, B, U: {len(grixis)}")
    if grixis:
        for card in grixis[:10]:
            print(f"  {card.get('name')}: {card.get('color_identity')}")
    else:
        print("None found in first 175 results!")
        
        # Check the full total
        print(f"\nTotal matches for query: {data.get('total_cards', 'unknown')}")
        print("The multicolor R+B+U commanders might be further down the list")

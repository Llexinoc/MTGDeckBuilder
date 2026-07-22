#!/usr/bin/env python3
"""Check the actual API response more carefully."""

from deckbuilder.scryfall import _cached_get, API_BASE, build_query

# Check what query is being built
query = build_query(['R', 'B', 'U'], card_type='Legendary Creature', fmt='commander')
print(f"Query string: {query}")

# Get the raw response
params = {"q": query, "order": "edhrec", "unique": "cards", "dir": "asc"}
url = f"{API_BASE}/cards/search"
print(f"URL: {url}")
print(f"Params: {params}\n")

data = _cached_get(url, params, no_network=False)

if data:
    print(f"Response has {len(data.get('data', []))} cards")
    print(f"Total available matches: {data.get('total_cards', 'unknown')}")
    
    # Look for multicolor cards
    multicolor = [c for c in data.get('data', []) if len(c.get('color_identity', [])) > 1]
    print(f"\nMulticolor cards in response: {len(multicolor)}")
    if multicolor:
        print("First 5 multicolor:")
        for card in multicolor[:5]:
            print(f"  {card.get('name')}: {card.get('color_identity')}")
    else:
        print("NO MULTICOLOR CARDS FOUND IN RESPONSE!")
else:
    print("No response from API")

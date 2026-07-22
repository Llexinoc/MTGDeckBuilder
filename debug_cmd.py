#!/usr/bin/env python3
"""Debug find_commander."""

from deckbuilder.scryfall import ScryfallClient

client = ScryfallClient(no_network=False)

# Manually do what find_commander does
cands = client.find_cards(
    ['R', 'B', 'U'], card_type="Legendary Creature",
    oracle_terms=['rebel', 'revolt', 'uprising'], fmt="commander", order="edhrec", limit=120,
)

print(f"After find_cards with theme terms: {len(cands)} cards")
if cands:
    for i, card in enumerate(cands[:5]):
        print(f"  {i+1}. {card.get('name')}: {card.get('color_identity')}")

if not cands:
    print("No cards with theme terms, trying without...")
    cands = client.find_cards(
        ['R', 'B', 'U'], card_type="Legendary Creature",
        fmt="commander", order="edhrec", limit=120,
    )
    print(f"After find_cards without theme terms: {len(cands)} cards")
    if cands:
        print("First 5 cards:")
        for i, card in enumerate(cands[:5]):
            print(f"  {i+1}. {card.get('name')}: {card.get('color_identity')}")

# Now filter by hard constraint
print("\nFiltering by hard constraint (want R, B, U in card identity)...")
want = set(['R', 'B', 'U'])
filtered = [c for c in cands if want.issubset(set(c.get("color_identity", [])))]
print(f"After filtering: {len(filtered)} cards")
if filtered:
    for i, card in enumerate(filtered[:5]):
        print(f"  {i+1}. {card.get('name')}: {card.get('color_identity')}")

#!/usr/bin/env python3
"""Test card searches."""

from deckbuilder.scryfall import ScryfallClient

client = ScryfallClient(no_network=False)

# Test finding theme creatures for R/B/U WITHOUT oracle terms
print("=== Testing R/B/U Legendary creatures (no oracle terms) ===")
cards = client.find_cards(['R', 'B', 'U'], card_type='Legendary Creature', limit=10)
print(f"Found {len(cards)} cards")
for card in cards[:5]:
    print(f"  {card.get('name')}: {card.get('color_identity')}")

print("\n=== Testing R/B/U with oracle terms ===")
cards2 = client.find_cards(['R', 'B', 'U'], oracle_terms=['rebel', 'revolt'], limit=10)
print(f"Found {len(cards2)} cards with oracle terms")
for card in cards2[:5]:
    print(f"  {card.get('name')}: {card.get('color_identity')}")

print("\n=== Testing monocolor red with oracle terms ===")
cards_red = client.find_cards(['R'], oracle_terms=['rebel', 'revolt'], limit=5)
print(f"Found {len(cards_red)} red cards")
for card in cards_red[:3]:
    print(f"  {card.get('name')}: {card.get('color_identity')}")


#!/usr/bin/env python3
"""Test find_cards for Grixis commanders."""

from deckbuilder.scryfall import ScryfallClient

client = ScryfallClient(no_network=False)
cards = client.find_cards(['R', 'B', 'U'], card_type='Legendary Creature', limit=40)
print(f'Found {len(cards)} legendary creatures with R, B, U')
for i, card in enumerate(cards):
    print(f"  {card.get('name')}: {card.get('color_identity')}")
    # Check if it has all three colors
    has_all = {'R', 'B', 'U'}.issubset(set(card.get('color_identity', [])))
    print(f"    Has all R, B, U: {has_all}")
    if i >= 9:
        break

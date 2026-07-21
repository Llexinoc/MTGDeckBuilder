#!/usr/bin/env python3
"""Quick test to see what the API returns."""

from deckbuilder.engine import build_deck

deck = build_deck("A Red Rising rebellion", fmt="commander", offline=False)

# Check a theme card
if deck["categories"].get("theme"):
    card = deck["categories"]["theme"][0]
    print(f"First theme card: {card['name']}")
    print(f"Has 'image' key: {'image' in card}")
    print(f"Image value: {card.get('image')}")
    print(f"Image type: {type(card.get('image'))}")
    print(f"\nFull card dict keys: {list(card.keys())}")
    print(f"\nFull card dict: {card}")

# Check commander
if deck["commander"]:
    cmd = deck["commander"]
    print(f"\n\nCommander: {cmd['name']}")
    print(f"Has 'image' key: {'image' in cmd}")
    print(f"Image value: {cmd.get('image')}")
    print(f"Image type: {type(cmd.get('image'))}")

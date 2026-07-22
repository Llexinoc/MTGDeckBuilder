#!/usr/bin/env python3
from deckbuilder.engine import build_deck
import json

test_desc = "A Red Rising rebellion: an oppressed underclass rises in brutal war against a ruthless, rigid hierarchy. Ambition, sacrifice, and revolt. Blue, Black, Red Commander."

print("Testing deck build with colors in description...")
print(f"Description: {test_desc}\n")

deck = build_deck(test_desc, fmt='commander', no_network=True, use_llm=False)

print(f"Colors in params: {deck['params']['colors']}")
print(f"Archetype: {deck['params']['archetype']}")
print(f"\nFull JSON response (first 1000 chars):")
print(json.dumps(deck, indent=2, default=str)[:1000])

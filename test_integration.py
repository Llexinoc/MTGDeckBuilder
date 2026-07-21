#!/usr/bin/env python
"""Integration test for network layer improvements."""

import json
from deckbuilder.engine import build_deck

print("=" * 60)
print("Network Layer Integration Tests")
print("=" * 60)

# Test 1: no_network=True should work
print("\n✓ Test 1: Building deck with no_network=True...")
deck = build_deck("Red aggro", no_network=True)
print(f"  - Deck built successfully")
print(f"  - Sources: {json.dumps(deck['sources'], indent=4)}")
assert deck["sources"]["network"] is False
assert deck["sources"]["cards"] in ["sample", "index"]
print(f"  - Commander: {deck['commander']['name'] if deck['commander'] else 'None'}")
print(f"  - Card categories: {list(deck['categories'].keys())}")

# Test 2: offline=True (deprecated) should still work  
print("\n✓ Test 2: Building deck with offline=True (deprecated)...")
deck2 = build_deck("Blue control", offline=True)
print(f"  - Deck built successfully")
print(f"  - Sources: {json.dumps(deck2['sources'], indent=4)}")
assert deck2["sources"]["network"] is False
print(f"  - Backward compatibility: offline parameter still works")

# Test 3: Network flag reporting
print("\n✓ Test 3: Network availability reporting...")
print(f"  - no_network=True reports network=False: {deck['sources']['network'] is False}")
print(f"  - Card source with no_network: {deck['sources']['cards']}")
print(f"  - LLM flag: {deck['sources']['llm']}")

# Test 4: Response structure
print("\n✓ Test 4: Response structure validation...")
assert "sources" in deck
assert "cards" in deck["sources"]
assert "network" in deck["sources"]
assert "llm" in deck["sources"]
print(f"  - All expected 'sources' keys present")
print(f"  - sources.cards = {deck['sources']['cards']}")
print(f"  - sources.network = {deck['sources']['network']}")
print(f"  - sources.llm = {deck['sources']['llm']}")

print("\n" + "=" * 60)
print("✓ All integration tests PASSED!")
print("=" * 60)

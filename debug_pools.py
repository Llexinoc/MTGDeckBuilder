#!/usr/bin/env python
"""Debug pool gathering."""
from deckbuilder.engine import DeckBuilder
from deckbuilder import carddata
from deckbuilder.theme import DeckParameters

# Connect to card index using the proper function
db_conn = carddata.connect()

# Build for bracket 2
builder = DeckBuilder(fmt="commander", db_conn=db_conn, bracket=2, enforce_ban_list=True)

params = DeckParameters(
    description="A simple green elves deck",
    archetype="ramp",
    colors=["G"],
    oracle_terms=["elf", "lord", "creature"],
    creature_types=["Elf"],
    reference_cards=[],
    commander_name=None,
    set_codes=set()
)

# Gather pools
pools = builder._gather(params)

print("Pool sizes before filtering:")
for pool_name, cards in pools.items():
    print(f"  {pool_name}: {len(cards)} cards")

# Check for game changers
print("\nGame changers in each pool (before filtering):")
for pool_name, cards in pools.items():
    game_changers = [c for c in cards if c.get("game_changer", False)]
    print(f"  {pool_name}: {len(game_changers)} game changers")

# Filter for bracket 2
filtered_pools = builder._filter_pools_for_bracket(pools, params)

print("\nPool sizes after bracket filtering:")
for pool_name, cards in filtered_pools.items():
    print(f"  {pool_name}: {len(cards)} cards")

# Check for game changers after filtering
print("\nGame changers in each pool (after filtering):")
for pool_name, cards in filtered_pools.items():
    game_changers = [c for c in cards if c.get("game_changer", False)]
    print(f"  {pool_name}: {len(game_changers)} game changers")

db_conn.close()

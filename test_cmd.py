#!/usr/bin/env python3
"""Test find_commander with the fix."""

from deckbuilder.scryfall import ScryfallClient

client = ScryfallClient(no_network=False)
cmd = client.find_commander(['R', 'B', 'U'], ['rebel', 'revolt', 'uprising'])
if cmd:
    print(f"Found: {cmd.get('name')} - {cmd.get('color_identity')}")
else:
    print("No commander found")

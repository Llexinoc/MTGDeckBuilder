#!/usr/bin/env python3
from deckbuilder.theme import interpret
from deckbuilder.expand import expand_query

desc = "just blue"
print(f"Testing: '{desc}'\n")

# Check expansion
expansion = expand_query(desc, use_llm=False, no_network=True)
print(f"Expansion themes: {expansion.get('mtg_themes', [])}")
print(f"Expansion concepts: {expansion.get('concepts', [])}\n")

# Check full interpretation
params = interpret(desc, use_llm=False, no_network=True)
print(f"Colors detected: {params.colors}")
print(f"Archetype: {params.archetype}")
print(f"Color scores: {params.color_scores}")

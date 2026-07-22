#!/usr/bin/env python3
from deckbuilder.theme import interpret, _extract_explicit_colors, _score_colors

test_cases = [
    "just blue",
    "blue only",
    "a blue deck",
    "red black then blue",
    "red and black and blue",
]

print("=== Color Detection Debug ===\n")

for desc in test_cases:
    print(f"Description: '{desc}'")
    explicit = _extract_explicit_colors(desc)
    print(f"  Explicit colors: {explicit}")
    
    scores = _score_colors(desc)
    print(f"  Scores: {sorted(scores.items(), key=lambda x: x[1], reverse=True)}")
    
    params = interpret(desc, use_llm=False, no_network=True)
    print(f"  Result: {params.colors}")
    print()

#!/usr/bin/env python3
"""Inspect the actual API response structure."""
import requests
import json

response = requests.post('http://127.0.0.1:5000/api/build', json={
    'description': 'A red aggressive burn deck with creatures and spells',
    'format': 'commander',
    'enforce_ban_list': True
})

if response.status_code == 200:
    deck = response.json()
    print("=" * 70)
    print("API RESPONSE STRUCTURE")
    print("=" * 70)
    print(json.dumps(deck, indent=2, default=str)[:3000])
    print("\n... (truncated)")
    print("\n" + "=" * 70)
    print("TOP-LEVEL KEYS:")
    print("=" * 70)
    for key in sorted(deck.keys()):
        value_type = type(deck[key]).__name__
        if isinstance(deck[key], (list, dict)):
            print(f"  {key}: {value_type} ({len(deck[key])} items)")
        else:
            print(f"  {key}: {value_type}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)

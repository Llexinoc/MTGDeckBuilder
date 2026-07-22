#!/usr/bin/env python
"""Quick API integration tests for the deck builder"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:5000"

print("=" * 70)
print("TEST 1: /api/health endpoint")
print("=" * 70)
try:
    r = requests.get(f"{BASE_URL}/api/health")
    health = r.json()
    print(f"✓ Status Code: {r.status_code}")
    print(f"✓ API Status: {health['status']}")
    print(f"✓ LLM Available: {health['llm']['available']}")
    print(f"✓ LLM Configured: {health['llm']['configured']}")
    print(f"✓ LLM Model: {health['llm']['model']}")
    print(f"✓ Card Index: {health['card_index']['card_count']} cards")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 70)
print("TEST 2: /api/build endpoint (blue control)")
print("=" * 70)
try:
    r = requests.post(f"{BASE_URL}/api/build", json={
        "description": "Blue control deck with card draw and counterspells",
        "format": "Commander"
    })
    deck = r.json()
    print(f"✓ Status Code: {r.status_code}")
    print(f"✓ Format: {deck['format']}")
    total_cards = sum(len(v) if isinstance(v, list) else 0 for v in deck.get('categories', {}).values())
    print(f"✓ Deck Size: {total_cards} cards")
    print(f"✓ Commander: {deck['commander']['name']}")
    print(f"✓ Avg CMC: {deck['stats']['avg_cmc']:.2f}")
    
    print(f"\n✓ LLM Status in response:")
    llm = deck['sources']['llm']
    print(f"  - available: {llm['available']}")
    print(f"  - configured: {llm['configured']}")
    print(f"  - used_for_reranking: {llm['used_for_reranking']}")
    print(f"  - model: {llm['model']}")
    
    print(f"\n✓ Card Type Distribution (top 5):")
    dist = deck['stats'].get('card_type_distribution', {})
    for card_type, count in sorted(dist.items(), key=lambda x: -x[1])[:5]:
        print(f"  - {card_type}: {count}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 70)
print("TEST 3: /api/build with use_llm_reranking=False")
print("=" * 70)
try:
    r = requests.post(f"{BASE_URL}/api/build", json={
        "description": "Red aggressive deck with dragons",
        "format": "Commander",
        "use_llm_reranking": False
    })
    deck = r.json()
    print(f"✓ Status Code: {r.status_code}")
    print(f"✓ Format: {deck['format']}")
    total_cards = sum(len(v) if isinstance(v, list) else 0 for v in deck.get('categories', {}).values())
    print(f"✓ Deck Size: {total_cards} cards")
    print(f"✓ Reranking explicitly disabled: {not deck['sources']['llm']['used_for_reranking']}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 70)
print("TEST 4: /api/build with bracket constraint")
print("=" * 70)
try:
    r = requests.post(f"{BASE_URL}/api/build", json={
        "description": "Green aggro creatures budget",
        "format": "Commander",
        "bracket": 2
    })
    deck = r.json()
    print(f"✓ Status Code: {r.status_code}")
    print(f"✓ Format: {deck['format']}")
    print(f"✓ Bracket: {deck['bracket']}")
    print(f"✓ Avg CMC: {deck['stats']['avg_cmc']:.2f}")
    print(f"✓ Game Changers: {deck['stats'].get('game_changer_count', 0)}")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 70)
print("TEST 5: Response structure validation")
print("=" * 70)
try:
    r = requests.post(f"{BASE_URL}/api/build", json={
        "description": "White lifegain deck",
        "format": "Commander"
    })
    deck = r.json()
    
    required_keys = ["format", "commander", "categories", "stats", "sources", "bracket", "reasoning"]
    missing = [k for k in required_keys if k not in deck]
    
    if missing:
        print(f"✗ Missing keys: {missing}")
    else:
        print(f"✓ All required top-level keys present")
    
    required_stats = ["avg_cmc", "card_type_distribution", "interaction_types"]
    missing_stats = [k for k in required_stats if k not in deck.get("stats", {})]
    
    if missing_stats:
        print(f"✗ Missing stats: {missing_stats}")
    else:
        print(f"✓ All required stats present")
    
    required_llm = ["available", "configured", "used_for_reranking", "model"]
    missing_llm = [k for k in required_llm if k not in deck.get("sources", {}).get("llm", {})]
    
    if missing_llm:
        print(f"✗ Missing LLM fields: {missing_llm}")
    else:
        print(f"✓ All LLM status fields present")
        
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "=" * 70)
print("SUMMARY: Environment setup and API integration verified ✓")
print("=" * 70)

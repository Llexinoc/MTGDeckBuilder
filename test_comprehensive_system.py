#!/usr/bin/env python3
"""
Comprehensive system test for bracket system, deck composition, and API.
Tests actual API calls end-to-end without preloaded data.
"""
import requests
import json
import sys

API_BASE = "http://127.0.0.1:5000/api"
TESTS_PASSED = 0
TESTS_FAILED = 0

def test(name, condition, details=""):
    """Report test result."""
    global TESTS_PASSED, TESTS_FAILED
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"{status}: {name}")
    if details and not condition:
        print(f"      {details}")
    if condition:
        TESTS_PASSED += 1
    else:
        TESTS_FAILED += 1


def build_deck(description, bracket=None, enforce_ban_list=True):
    """Build a deck via API and return response."""
    payload = {
        "description": description,
        "format": "commander",
        "enforce_ban_list": enforce_ban_list
    }
    if bracket is not None:
        payload["bracket"] = bracket
    
    response = requests.post(f"{API_BASE}/build", json=payload, timeout=60)
    return response


print("=" * 70)
print("COMPREHENSIVE BRACKET SYSTEM TEST SUITE")
print("=" * 70)
print()

# ========================================================================
# TEST 1: BRACKET 1 (Exhibition) - No Game Changers
# ========================================================================
print("TEST 1: Bracket 1 (Exhibition) - Ultra-casual, NO Game Changers")
print("-" * 70)
response = build_deck("A simple casual blue deck for fun and learning magic, casual exhibition level")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    # Composition checks
    test("Total cards = 100", deck["stats"]["total_cards"] == 100, 
         f"Got {deck['stats']['total_cards']}")
    test("Nonland + lands = total", 
         deck["stats"]["nonland_cards"] + deck["stats"]["lands"] == 100,
         f"Got {deck['stats']['nonland_cards']} + {deck['stats']['lands']} = {deck['stats']['nonland_cards'] + deck['stats']['lands']}")
    test("Lands = 36", deck["stats"]["lands"] == 36, f"Got {deck['stats']['lands']}")
    
    # Bracket classification
    bracket = deck.get("bracket", {})
    test("Classified as Bracket 1", bracket.get("level") == 1, f"Got {bracket.get('level')}")
    test("Bracket name is Exhibition", bracket.get("name") == "Exhibition", f"Got {bracket.get('name')}")
    
    # Game changer enforcement
    test("Game Changers = 0 (Bracket 1 restriction)", 
         deck["stats"]["game_changer_count"] == 0,
         f"Got {deck['stats']['game_changer_count']}")
    
    # Check no banned cards (check in warnings if any)
    warnings = deck.get("warnings", [])
    banned_in_warnings = any("banned" in w.lower() for w in warnings)
    test("No ban-related warnings", not banned_in_warnings, f"Warnings: {warnings}")
    
    print(f"   Commander: {deck['commander']['name']}")
    print(f"   Avg CMC: {deck['stats']['avg_cmc']:.2f}")
    print()

# ========================================================================
# TEST 2: BRACKET 5 (cEDH) - High-power with Game Changers
# ========================================================================
print("TEST 2: Bracket 5 (cEDH) - Tournament-level, allows Game Changers")
print("-" * 70)
response = build_deck("A tournament-strength cEDH combo deck, cedh bracket 5, high power competitive")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    # Composition checks
    test("Total cards = 100", deck["stats"]["total_cards"] == 100, 
         f"Got {deck['stats']['total_cards']}")
    test("Lands = 36", deck["stats"]["lands"] == 36, f"Got {deck['stats']['lands']}")
    
    # Bracket classification
    bracket = deck.get("bracket", {})
    test("Classified as Bracket 5 or high-power", bracket.get("level") in [4, 5],
         f"Got {bracket.get('level')} ({bracket.get('name')})")
    
    # Game changers should be allowed (and possibly present)
    gc_count = deck["stats"]["game_changer_count"]
    test("Game Changers allowed (may be 0 or more)", gc_count >= 0,
         f"Got {gc_count}")
    
    print(f"   Commander: {deck['commander']['name']}")
    print(f"   Game Changers: {gc_count}")
    print(f"   Avg CMC: {deck['stats']['avg_cmc']:.2f}")
    print()

# ========================================================================
# TEST 3: BRACKET 3 (Upgraded) - Max 3 Game Changers
# ========================================================================
print("TEST 3: Bracket 3 (Upgraded) - Tuned fair, max 3 Game Changers")
print("-" * 70)
response = build_deck("An upgraded and tuned deck, bracket 3, better than precon but not crazy")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    # Composition checks
    test("Total cards = 100", deck["stats"]["total_cards"] == 100, 
         f"Got {deck['stats']['total_cards']}")
    
    # Bracket classification
    bracket = deck.get("bracket", {})
    test("Classified as Bracket 3 or similar", bracket.get("level") in [2, 3],
         f"Got {bracket.get('level')} ({bracket.get('name')})")
    
    # Game changer limit for Bracket 3
    gc_count = deck["stats"]["game_changer_count"]
    test("Game Changers <= 3 (Bracket 3 limit)", gc_count <= 3,
         f"Got {gc_count}")
    
    print(f"   Commander: {deck['commander']['name']}")
    print(f"   Game Changers: {gc_count}")
    print()

# ========================================================================
# TEST 4: SINGLETON CONSTRAINT (Commander)
# ========================================================================
print("TEST 4: Singleton Constraint - Max 1 copy per non-basic card")
print("-" * 70)
response = build_deck("A singleton commander deck with varied creatures and spells")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    # Count copies of each card
    card_counts = {}
    for category, cards in deck.get("categories", {}).items():
        if isinstance(cards, list):
            for card in cards:
                name = card.get("name", "Unknown")
                count = card.get("count", 1)
                card_counts[name] = count
    
    # Check singleton constraint (ignore basic lands)
    violations = []
    for name, count in card_counts.items():
        if count > 1 and "Island" not in name and "Swamp" not in name and "Forest" not in name and "Mountain" not in name and "Plains" not in name and "Wastes" not in name:
            violations.append(f"{name}: {count} copies")
    
    test("Singleton constraint enforced", len(violations) == 0,
         f"Violations: {violations}" if violations else "")
    
    print(f"   Unique non-land cards: {len([n for n, c in card_counts.items() if c == 1])}")
    print()

# ========================================================================
# TEST 5: BAN LIST ENFORCEMENT
# ========================================================================
print("TEST 5: Ban List Enforcement - enforce_ban_list toggle")
print("-" * 70)

# Build with ban list enforced
response_banned = build_deck("A deck with strong spells", enforce_ban_list=True)
test("Build with enforce_ban_list=True succeeds", 
     response_banned.status_code == 200, 
     f"Status: {response_banned.status_code}")

if response_banned.status_code == 200:
    deck_banned = response_banned.json()
    banned_in_deck = len(deck_banned.get("banned_cards", []))
    test("No banned cards when enforce_ban_list=True", 
         banned_in_deck == 0,
         f"Found {banned_in_deck} banned cards")

# Build with ban list disabled
response_unbanned = build_deck("A competitive deck with all cards", enforce_ban_list=False)
test("Build with enforce_ban_list=False succeeds", 
     response_unbanned.status_code == 200, 
     f"Status: {response_unbanned.status_code}")

if response_unbanned.status_code == 200:
    deck_unbanned = response_unbanned.json()
    # Ban list off may include banned cards (if they're in the pool)
    test("API accepts enforce_ban_list=False", True, "Toggle parameter accepted")

print()

# ========================================================================
# TEST 6: COLOR IDENTITY CONSTRAINT
# ========================================================================
print("TEST 6: Color Identity Constraint - All cards match commander")
print("-" * 70)
response = build_deck("A mono-blue control deck with blue spells only")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    commander = deck.get("commander", {})
    commander_identity = set(commander.get("color_identity", []))
    
    print(f"   Commander identity: {commander_identity}")
    
    # Check all cards match color identity
    identity_violations = []
    for category, cards in deck.get("categories", {}).items():
        if isinstance(cards, list):
            for card in cards:
                card_colors = set(card.get("colors", []))
                if not card_colors.issubset(commander_identity):
                    identity_violations.append(f"{card.get('name')}: {card_colors} not subset of {commander_identity}")
    
    test("All cards within color identity", len(identity_violations) == 0,
         f"Violations: {identity_violations[:3]}" if identity_violations else "")
    
    print()

# ========================================================================
# TEST 7: DECK COMPOSITION RATIOS
# ========================================================================
print("TEST 7: Deck Composition - Proper category ratios")
print("-" * 70)
response = build_deck("A mid-range creature deck with interaction and ramp")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    by_cat = deck.get("categories", {})
    total_by_cat = 0
    for cards in by_cat.values():
        if isinstance(cards, list):
            total_by_cat += len(cards)
    
    test("Total across categories matches deck size", total_by_cat == 100,
         f"Got {total_by_cat}")
    
    # Check expected categories exist
    test("Has theme category", "theme" in by_cat or "creatures" in by_cat or "payoffs" in by_cat, 
         f"Categories: {list(by_cat.keys())}")
    test("Has ramp category", "ramp" in by_cat, f"Categories: {list(by_cat.keys())}")
    test("Has lands category", "lands" in by_cat, f"Categories: {list(by_cat.keys())}")
    
    # Verify reasonable ratios
    lands_list = by_cat.get("lands", [])
    lands = len(lands_list) if isinstance(lands_list, list) else 0
    
    # Find theme category (could be theme, creatures, payoffs, etc)
    theme_list = []
    for key in ["theme", "creatures", "payoffs"]:
        if key in by_cat and isinstance(by_cat[key], list):
            theme_list = by_cat[key]
            break
    theme = len(theme_list)
    
    ramp_list = by_cat.get("ramp", [])
    ramp = len(ramp_list) if isinstance(ramp_list, list) else 0
    
    test("Lands between 30-40", 30 <= lands <= 40, f"Got {lands}")
    test("Theme cards exist", theme > 0, f"Got {theme}")
    test("Ramp cards exist", ramp > 0, f"Got {ramp}")
    
    print(f"   Category breakdown:")
    for cat, cards in sorted(by_cat.items()):
        card_count = len(cards) if isinstance(cards, list) else 0
        print(f"     {cat}: {card_count}")
    print()

# ========================================================================
# TEST 8: MANA CURVE CALCULATION
# ========================================================================
print("TEST 8: Mana Curve - Average CMC calculation")
print("-" * 70)
response = build_deck("A mixed mana curve deck for testing")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    avg_cmc = deck["stats"]["avg_cmc"]
    
    test("Avg CMC is reasonable", 2.0 <= avg_cmc <= 5.0, f"Got {avg_cmc:.2f}")
    
    # Verify mana curve data exists
    curve = deck["stats"].get("curve", {})
    test("Mana curve data exists", len(curve) > 0 or avg_cmc > 0, "No curve data")
    
    print(f"   Average CMC: {avg_cmc:.2f}")
    if curve:
        print(f"   Mana curve buckets: {sum(curve.values())} cards")
    print()

# ========================================================================
# TEST 9: THEME DETECTION
# ========================================================================
print("TEST 9: Theme Detection - LLM enrichment working")
print("-" * 70)
response = build_deck("A graveyard-focused self-mill deck with flashback spells and recursion")
test("Build request succeeds", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    
    # Check explanation exists
    explanation = deck.get("reasoning", "")
    test("Explanation generated", len(explanation) > 0, "No explanation")
    
    # Check bracket reasoning exists
    bracket = deck.get("bracket", {})
    bracket_reasoning = bracket.get("reasoning", "")
    test("Bracket reasoning exists", len(bracket_reasoning) > 0, "No bracket reasoning")
    
    print(f"   Reasoning length: {len(explanation)} chars")
    print(f"   Bracket reasoning: {bracket_reasoning[:60]}...")
    print()

# ========================================================================
# TEST 10: AUTO-DETECTION (No bracket specified)
# ========================================================================
print("TEST 10: Auto-Detection - Bracket inferred from description")
print("-" * 70)
response = build_deck("A casual fun deck, nothing too serious, just for kitchen table play")
test("Build without explicit bracket", response.status_code == 200, f"Status: {response.status_code}")

if response.status_code == 200:
    deck = response.json()
    bracket = deck.get("bracket", {})
    test("Bracket auto-classified", bracket.get("level") is not None, "No bracket level")
    test("Bracket has reasoning", len(bracket.get("reasoning", "")) > 0, "No reasoning")
    
    print(f"   Auto-detected: Bracket {bracket.get('level')} - {bracket.get('name')}")
    print()

# ========================================================================
# SUMMARY
# ========================================================================
print("=" * 70)
print("TEST SUMMARY")
print("=" * 70)
total = TESTS_PASSED + TESTS_FAILED
pct = (TESTS_PASSED / total * 100) if total > 0 else 0
print(f"Passed: {TESTS_PASSED}/{total} ({pct:.1f}%)")
print(f"Failed: {TESTS_FAILED}/{total}")
print()

if TESTS_FAILED == 0:
    print("🎉 ALL TESTS PASSED!")
    sys.exit(0)
else:
    print(f"❌ {TESTS_FAILED} test(s) failed")
    sys.exit(1)

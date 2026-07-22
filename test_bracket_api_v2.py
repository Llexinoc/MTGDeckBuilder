#!/usr/bin/env python
"""Test the bracket system via API."""
import requests
import json

url = 'http://127.0.0.1:5000/api/build'

# Test 1: Bracket 2 (casual/precon)
print("=" * 60)
print("TEST 1: Bracket 2 (Casual/Precon)")
print("=" * 60)
data = {
    'description': 'A casual Elves deck, precon power level, bracket 2',
    'format': 'commander',
    'bracket': 2,
    'enforce_ban_list': True
}

response = requests.post(url, json=data)
deck = response.json()
print(f'Commander: {deck.get("commander", {}).get("name", "N/A")}')
print(f'Total cards: {deck.get("stats", {}).get("total_cards", 0)}')
print(f'Nonland cards: {deck.get("stats", {}).get("nonland_cards", 0)}')
print(f'Bracket: {deck.get("bracket", {}).get("name", "N/A")} (Level {deck.get("bracket", {}).get("level", "N/A")})')
print(f'Bracket reasoning: {deck.get("bracket", {}).get("reasoning", "N/A")}')
print(f'Game changers: {deck.get("stats", {}).get("game_changer_count", 0)}')
print()

# Test 2: Bracket 5 (cEDH)
print("=" * 60)
print("TEST 2: Bracket 5 (cEDH/Tournament)")
print("=" * 60)
data = {
    'description': 'A high-power Blue control deck, tournament level, bracket 5',
    'format': 'commander',
    'bracket': 5,
    'enforce_ban_list': True
}

response = requests.post(url, json=data)
deck = response.json()
print(f'Commander: {deck.get("commander", {}).get("name", "N/A")}')
print(f'Total cards: {deck.get("stats", {}).get("total_cards", 0)}')
print(f'Nonland cards: {deck.get("stats", {}).get("nonland_cards", 0)}')
print(f'Bracket: {deck.get("bracket", {}).get("name", "N/A")} (Level {deck.get("bracket", {}).get("level", "N/A")})')
print(f'Bracket reasoning: {deck.get("bracket", {}).get("reasoning", "N/A")}')
print(f'Game changers: {deck.get("stats", {}).get("game_changer_count", 0)}')
print()

# Test 3: No bracket specified (should be auto-detected or default)
print("=" * 60)
print("TEST 3: No bracket specified (auto-detect)")
print("=" * 60)
data = {
    'description': 'A simple Red aggro deck with goblins and haste creatures',
    'format': 'commander',
    'enforce_ban_list': True
}

response = requests.post(url, json=data)
deck = response.json()
print(f'Commander: {deck.get("commander", {}).get("name", "N/A")}')
print(f'Total cards: {deck.get("stats", {}).get("total_cards", 0)}')
print(f'Nonland cards: {deck.get("stats", {}).get("nonland_cards", 0)}')
print(f'Bracket: {deck.get("bracket", {}).get("name", "N/A")} (Level {deck.get("bracket", {}).get("level", "N/A")})')
print(f'Bracket reasoning: {deck.get("bracket", {}).get("reasoning", "N/A")}')
print(f'Game changers: {deck.get("stats", {}).get("game_changer_count", 0)}')

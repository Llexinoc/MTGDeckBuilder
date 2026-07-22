#!/usr/bin/env python3
import requests
import json

response = requests.post('http://127.0.0.1:5000/api/build', json={
    'description': 'Iron Man: A brilliant artificer wielding advanced technology and mechanical armor to fight powerful threats. Relentless precision.',
    'format': 'commander',
    'enforce_ban_list': True
})

if response.status_code == 200:
    deck = response.json()
    print('=== IRON MAN DECK SUMMARY ===')
    print(f'Commander: {deck["commander"]["name"]}')
    print(f'Total cards: {deck["stats"]["total_cards"]}')
    print(f'Game Changers: {deck["stats"]["game_changer_count"]}')
    print(f'Avg CMC: {deck["stats"]["avg_cmc"]:.2f}')
    print()
    print('=== BRACKET CLASSIFICATION ===')
    bracket = deck.get('bracket', {})
    print(f'Level: {bracket.get("level")}')
    print(f'Name: {bracket.get("name")}')
    print(f'Reasoning: {bracket.get("reasoning")}')
    print()
    print('=== DECK COMPOSITION ===')
    for category, cards in deck.get('by_category', {}).items():
        if cards:
            print(f'{category.title()}: {len(cards)} cards')
else:
    print(f'Error: {response.status_code}')
    print(response.text)

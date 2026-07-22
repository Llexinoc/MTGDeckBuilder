#!/usr/bin/env python3
"""Import full card database from JSONL file."""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Import to the project database
db_path = Path(r'data/cards.sqlite')
jsonl_path = Path(r'c:\Users\Colli\Downloads\default-cards-20260721091054.jsonl\default-cards-20260721091054.jsonl')

print(f"Importing from: {jsonl_path}")
print(f"Database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Enable FTS5 and create/clear tables
cursor.execute('DROP TABLE IF EXISTS cards_fts')
cursor.execute('DROP TABLE IF EXISTS cards')
cursor.execute('''
    CREATE TABLE cards (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type_line TEXT,
        oracle_text TEXT,
        mana_cost TEXT,
        cmc REAL,
        color_identity TEXT,
        color_code TEXT,
        rarity TEXT,
        set_code TEXT,
        scryfall_uri TEXT,
        image_uris TEXT,
        reserved INTEGER,
        is_legal_commander INTEGER,
        legal_commander INTEGER,
        legal_standard INTEGER,
        edhrec_rank INTEGER,
        updated_at TIMESTAMP
    )
''')

# Create FTS5 index
cursor.execute('''
    CREATE VIRTUAL TABLE cards_fts USING fts5(
        name, type_line, oracle_text, color_identity
    )
''')

# Import cards from JSONL
imported = 0
errors = 0

with open(jsonl_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if not line.strip():
            continue
        try:
            card = json.loads(line)
            
            # Check if it's a valid card for MTG
            if card.get('object') != 'card':
                continue
            
            card_id = card.get('id', f'unknown-{i}')
            name = card.get('name', '')
            type_line = card.get('type_line', '')
            oracle_text = card.get('oracle_text', '')
            mana_cost = card.get('mana_cost', '')
            cmc = float(card.get('cmc', 0))
            color_identity = json.dumps(card.get('color_identity', []))
            color_code = ''.join(sorted(card.get('color_identity', [])))
            rarity = card.get('rarity', '')
            set_code = card.get('set', '')
            scryfall_uri = card.get('scryfall_uri', '')
            image_uris = json.dumps(card.get('image_uris', {}))
            reserved = 1 if card.get('reserved') else 0
            is_legendary = 'Legendary' in type_line
            is_legal = (not reserved) and is_legendary
            
            # Insert into cards table
            cursor.execute('''
                INSERT OR REPLACE INTO cards VALUES 
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                card_id, name, type_line, oracle_text, mana_cost, cmc,
                color_identity, color_code, rarity, set_code, scryfall_uri,
                image_uris, reserved, 1 if is_legal else 0, 1 if is_legal else 0, 
                1 if (not reserved) else 0, None, datetime.utcnow().isoformat()
            ))
            
            # Insert into FTS5
            cursor.execute('''
                INSERT INTO cards_fts(rowid, name, type_line, oracle_text, color_identity)
                VALUES (?, ?, ?, ?, ?)
            ''', (i, name, type_line, oracle_text, color_code))
            
            imported += 1
            if imported % 10000 == 0:
                print(f'Imported {imported} cards...')
                conn.commit()
                
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f'Error on card {i}: {e}')

conn.commit()

# Verify
cursor.execute('SELECT COUNT(*) FROM cards')
total = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM cards WHERE is_legal_commander = 1')
commanders = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(*) FROM cards WHERE color_code LIKE "%R%"')
red_cards = cursor.fetchone()[0]
cursor.execute('''
    SELECT COUNT(*) FROM cards 
    WHERE is_legal_commander = 1 AND color_code LIKE "%R%"
''')
red_commanders = cursor.fetchone()[0]

print(f'\nImport complete!')
print(f'Total cards: {total}')
print(f'Commander-legal: {commanders}')
print(f'Red cards: {red_cards}')
print(f'Red commanders: {red_commanders}')

conn.close()

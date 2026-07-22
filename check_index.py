#!/usr/bin/env python
"""Check card index status."""
from deckbuilder import carddata
import sqlite3
from pathlib import Path

status = carddata.get_index_status()
print("Index Status:", status)
print()

db_path = Path(__file__).resolve().parent / "data" / "cards.sqlite"
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM cards')
total = cur.fetchone()[0]
print(f'Total cards in index: {total}')

# Check for game_changer column
cur.execute("PRAGMA table_info(cards)")
columns = cur.fetchall()
print("\nCard table columns:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

# Count game_changer cards
cur.execute('SELECT COUNT(*) FROM cards WHERE game_changer = 1')
game_changers = cur.fetchone()[0]
print(f"\nCards with game_changer = 1: {game_changers}")

conn.close()

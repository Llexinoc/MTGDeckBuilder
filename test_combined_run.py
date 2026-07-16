from combined_app import build_deck

if __name__ == '__main__':
    d = build_deck('A Red Rising rebellion', fmt='commander', offline=True)
    print('format:', d.get('format'))
    print('total_cards:', d.get('stats', {}).get('total_cards'))
    print('nonland_cards:', d.get('stats', {}).get('nonland_cards'))

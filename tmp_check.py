import requests
q = 'id<=R t:Creature (o:"goblin" OR o:"warrior") set:mh3 legal:commander game:paper -is:funny'
params = {'q': q, 'order': 'edhrec', 'unique': 'cards', 'dir': 'asc'}
r = requests.get('https://api.scryfall.com/cards/search', params=params, headers={'User-Agent':'MTGThemeDeckbuilder/1.0 (educational project)','Accept':'application/json;q=0.9,*/*;q=0.8'}, timeout=20)
print(r.status_code)
print(r.text[:1200])

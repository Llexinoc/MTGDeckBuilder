# Scryfall Bulk Data — Reference Notes

Last verified: 2026-07-20

## Endpoint

```
GET https://api.scryfall.com/bulk-data
```

Returns a list of `bulk_data` objects, one per file. Download URLs change timestamp daily — always fetch them programmatically from this endpoint rather than hardcoding.

## File format

- Each file is a **gzipped JSONL** archive (`.jsonl.gz`) — plain `.gz`, **not** `.tar.gz`.
- Stream line-by-line from the gzip without full decompression:
  - Ruby: `Zlib::GzipReader#each_line`
  - Python: `gzip.open(path, "rt")` + iterate lines
  - Shell (POSIX): `gunzip` / `zcat`

## Available files

| File | Uncompressed size | Contents |
|---|---|---|
| Oracle Cards | 171 MB | One card object per Oracle ID; most up-to-date recognizable printing |
| Unique Artwork | 252 MB | Cards covering all unique artworks; best image scans |
| Default Cards | 532 MB | Every card object, English (or printed language if only one) |
| All Cards | 2.4 GB | Every card object in every language |
| Rulings | 24.7 MB | All rulings; linked to cards via `oracle_id` |
| Art Tags | 38.8 MB | Illustration tags from the community Tagger project |
| Oracle Tags | 17.3 MB | Oracle tags from the Tagger project |

## Bulk data object fields

| Property | Type | Details |
|---|---|---|
| `id` | UUID | Unique ID for the bulk item |
| `uri` | URI | Scryfall API URI for the file |
| `type` | String | Computer-readable kind (e.g. `oracle_cards`, `default_cards`, `all_cards`, `rulings`, `unique_artwork`) |
| `name` | String | Human-readable name |
| `description` | String | Human-readable description |
| `download_uri` | URI | Hosts the bulk file (JSON) |
| `jsonl_download_uri` | URI | Hosts the file as jsonl.gz |
| `updated_at` | Timestamp | Last update time |
| `size` | Integer | File size in bytes |
| `content_type` | MIME | MIME type |
| `content_encoding` | Encoding | Content-Encoding used on download |

## Caveats

- **Prices**: included in card objects but considered dangerously stale after 24 hours. Fine for trends/rough estimates; never power a storefront with them.
- **Gameplay data** (names, Oracle text, mana costs): changes rarely. Weekly downloads or refreshing after set releases is sufficient if that's all you need.
- **Coverage**: every card type in every product is included — double-faced, planar, schemes, vanguards, tokens, funny cards. Review the Card type docs before parsing.
- **Tags**: Art Tags / Oracle Tags come from the community Tagger project; see Tags docs for object format and how to join tags to cards.
- **Freshness**: bulk data regenerates every 12–24 hours. For fresher data use the card API methods, or `/cards/manifest` to check what changed.

## Typical fetch pattern

```python
import requests, gzip, json

# 1. Get current bulk data listing
bulk = requests.get("https://api.scryfall.com/bulk-data").json()

# 2. Pick a file by type
oracle = next(d for d in bulk["data"] if d["type"] == "oracle_cards")

# 3. Download the jsonl.gz and stream it
r = requests.get(oracle["jsonl_download_uri"], stream=True)
with open("oracle_cards.jsonl.gz", "wb") as f:
    for chunk in r.iter_content(1 << 20):
        f.write(chunk)

with gzip.open("oracle_cards.jsonl.gz", "rt", encoding="utf-8") as f:
    for line in f:
        card = json.loads(line)
        # process card...
```

Tip: compare `updated_at` against your last download before re-fetching.

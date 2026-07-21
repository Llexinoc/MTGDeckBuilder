# Prompt: build Scryfall card data ingest

Paste everything below the line into your coding agent, in the repo root of the
MTG Theme Deckbuilder.

---

Build the card data layer for this Flask app. Right now `deckbuilder/engine.py`
has no reliable local source of card data — add one.

## What to build

Create `deckbuilder/carddata.py`, a module that downloads Scryfall bulk data,
filters it to real playable cards, and loads a SQLite index the engine queries
offline. Expose a CLI:

```
python -m deckbuilder.carddata sync    # download + rebuild index
python -m deckbuilder.carddata info    # show index status
```

Then wire it into the app:

- `deckbuilder/engine.py` — `build_deck()` reads candidates from the index
  instead of any hardcoded card list or live per-card API calls.
- `app.py` — `/api/health` also reports `card_index`: whether the index exists,
  how many cards it holds, and the `updated_at` of the bulk file it came from.
- `/api/build` — return HTTP 503 with a clear message if the index is missing,
  rather than a 500 traceback.
- `requirements.txt` — add `requests` if absent.
- `README.md` — document that `sync` must be run once before first use.
- `.gitignore` — exclude `data/` (the archive and index are large, regenerable
  artifacts and must never be committed).

## How to pull the data — these are correctness requirements, not suggestions

**Never hardcode a download URL.** Fetch `GET https://api.scryfall.com/bulk-data`
and read `jsonl_download_uri` off the entry whose `type` matches. Those URLs
carry a timestamp that changes daily; a hardcoded one goes stale and 404s.

**Send a real User-Agent and an `Accept: application/json` header** on every
Scryfall request. They ask all clients to identify themselves.

**Files are plain gzip (`.gz`), not tarballs.** Do not try to untar them.

**Stream, never load.** Use `requests.get(..., stream=True)` +
`iter_content` to download, and `gzip.open(path, "rt")` iterating line by line
to parse. Do not call `resp.content`, do not `json.load()` the archive. All
Cards is 2.4 GB uncompressed and will blow the process's memory.

**Default to `oracle_cards`, support `all_cards` behind a flag.** Oracle Cards
(171 MB) is one object per Oracle ID and is what a deckbuilder actually wants.
All Cards (2.4 GB) is every printing in every language — roughly 30 near-copies
per card. If you index it without deduping, the engine will suggest the same
card 30 times and the German printing of everything. If All Cards is selected,
collapse to one row per `oracle_id`, preferring non-digital, non-promo, has an
image, most recent `released_at`.

**Filter out things that are not castable cards.** Every bulk file contains
tokens, emblems, art series, schemes, planes, vanguards and oversized
memorabilia. Drop rows where:

- `lang` is not in the wanted set (default `{"en"}`)
- `layout` is in `{token, double_faced_token, emblem, art_series, vanguard, scheme, planar, augment, host}`
- `set_type` is in `{token, memorabilia, minigame}`
- `oversized` is truthy
- `oracle_id` is missing (reversible cards — they're alternate printings of cards you already have)

**Double-faced cards have no top-level `oracle_text`, `mana_cost`, or
`type_line`.** For any card with `card_faces`, pull those fields off the faces
and join them. If you skip this, every MDFC and transform card lands in the
index with empty rules text and becomes invisible to theme matching.

**Use `color_identity`, not `colors`, for Commander legality.** They differ —
a card with `{R}` in its rules text but no red mana cost has red identity and is
illegal in a mono-blue deck. Filter candidates by whether their identity is a
subset of the commander's.

**Read legality from `legalities.commander` / `legalities.standard`** and store
as booleans. Do not infer legality from set or rarity.

**Prices are stale by design.** Bulk data regenerates every 12–24 hours, so
`prices.usd` is a rough estimate only. Store it if you want budget filtering,
but label it clearly and never present it as a live price.

**Check freshness before re-downloading.** Record the `updated_at` you last
ingested; skip the download if the manifest still reports the same value. Add
a `--force` flag to override. Re-pulling more than daily just burns their CDN.

**Build the index atomically.** Write to a temp DB and rename it into place at
the end, so an interrupted sync never leaves the app querying a half-populated
index.

## Index shape

One row per `oracle_id`, with at minimum: name, mana_cost, cmc, type_line,
oracle_text, power/toughness/loyalty, colors, color_identity, keywords, set,
rarity, released_at, edhrec_rank, legal_commander, legal_standard,
can_be_commander, image url, price_usd.

Add an FTS5 virtual table over name / type_line / oracle_text / keywords —
theme matching ("lifegain tokens", "artifact sacrifice") is a text search
problem and FTS is what makes it fast without an LLM call.

Mark `can_be_commander` true when the oracle text contains "can be your
commander", or the type line has both "Legendary" and "Creature".

Sort candidate results by `edhrec_rank` ascending (nulls last) — it's the best
free popularity signal in the data and keeps suggestions recognizable.

## Verify before you call it done

Write tests against a small synthetic `.jsonl.gz` fixture, not the live 2.4 GB
file. The fixture must include: two printings of one card, a non-English
printing, a token, an emblem, an oversized card, a reversible card with no
`oracle_id`, an MDFC with text only on its faces, and a legendary creature.
Assert that only the real cards survive, the duplicate collapses to the
preferred printing, the MDFC has joined rules text, and color identity subset
filtering works.

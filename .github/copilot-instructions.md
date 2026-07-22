# Project rules — MTG Theme Deckbuilder

Durable constraints for this repo. These apply to every change, not one task.
For one-off task briefs see `docs/prompts/`.

## What this app is

A Flask app that turns a plain-English theme description into a legal, playable
Commander or Standard decklist. Card data comes from Scryfall.

`app.py` serves the UI and `/api/build`. `deckbuilder/engine.py` builds decks,
`theme.py` interprets the request, `scryfall.py` fetches card data,
`carddata.py` owns the local SQLite index.

## Scryfall data — non-negotiable

**Double-faced cards have no top-level `oracle_text`, `mana_cost`, `type_line`,
or `image_uris`.** Those live on `card_faces[]`. Join from the faces anywhere
these fields are read. This is the single most common source of bugs in this
codebase — blank card art, empty rules text, commanders that can't be found.

**Never hardcode a bulk download URL.** Fetch `https://api.scryfall.com/bulk-data`
and read `jsonl_download_uri` off the matching entry. Those URLs carry a daily
timestamp.

**Bulk files are plain gzip, not tarballs.** Stream them — `gzip.open(path, "rt")`
line by line. Never `json.load()` the archive.

**Use `color_identity`, not `colors`, for Commander legality.** A card with `{R}`
in its rules text has red identity even with no red in its mana cost.

**Read legality from `legalities.commander` / `legalities.standard`.** Never
infer it from set or rarity. The values are `legal`, `not_legal`, `banned`, and
`restricted` — `banned` and `not_legal` are different things and are handled
differently.

**Mana Value (MV) is the field `cmc` in the data.** Scryfall never renamed it
after the game term changed from converted mana cost. There is no `mv` field.

**Prices are stale by design** — bulk data regenerates every 12–24 hours. Rough
estimates only, never presented as live.

**Send `User-Agent` and `Accept: application/json`** on every Scryfall request,
and keep the inter-request delay.

**Hotlink images from `cards.scryfall.io`.** Don't download or re-host.

## Architecture constraints

Card data is read from `data/cards.sqlite` when it exists, live API when it
doesn't, bundled sample pool only as a last resort. The build response reports
which was used — falling back to the sample pool must never be silent.

`no_network=True` is a hard guarantee of zero outbound requests to any host —
Scryfall, Datamuse, and Anthropic alike. Enforce at the request helper, not per
call site. Cache reads are still allowed.

Searches against Scryfall are batch `/cards/search` queries. Do not introduce
per-card API lookups.

`data/` is generated and gitignored. Never commit it, never delete it during
cleanup — it's expensive to rebuild.

## Theme interpretation

Resolution order is: named card match, then mechanical archetype mapping, then
text search. Raw FTS on the user's literal words must never drive card
selection on its own.

Parse compound requests into typed axes — tribal, strategy, support,
constraints — and prioritize when they conflict. Never silently drop an axis; if
the deck can't be everything asked for, the response says which gave way.

The LLM step returns validated structured JSON. Unvalidated model output must
not reach the search layer.

Do not hardcode theme-to-card mappings or special-case individual themes.

## Git

Commit after every discrete change. Never leave a session's work uncommitted.
Commit before anything destructive — deletions, renames, restructuring.

Never run `git reset --hard`, `git checkout .`, `git clean -fd`, or force-push
without asking first.

Never commit `data/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, or `.env`.

Show `git show --stat HEAD` after committing so the diff is visible.

## Working style

Report proposed deletions and wait for approval rather than removing files
directly.

Claims must match the repo. Verify before stating something was done — if you
say a file was deleted, confirm it's gone; if you say tests pass, paste the
output. Saying you skipped something is fine. A confident summary that doesn't
match the code is not.

Tests mock the HTTP layer — no live network calls in the suite. Use small
synthetic `.jsonl.gz` fixtures, never the real bulk file.

Every deck must be exactly 100 cards for Commander, singleton except basics,
roughly 36–38 lands.

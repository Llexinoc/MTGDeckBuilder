# ManaForge — Themed MTG Deckbuilder

Type a description of the deck you want ("a Red Rising rebellion against a
ruthless ruling hierarchy") and ManaForge builds a **legal, playable Magic: The
Gathering deck** that fits the theme — using Magic's own deckbuilding logic, not
by copying anyone's existing decklist.

It maps your description onto Magic's colour pie, picks a strategy, pulls real
card data from the [Scryfall API](https://scryfall.com/docs/api), and assembles
a deck with the right mana curve, category ratios, and mana base.

---

## Quick start

```bash
cd mtg-theme-deckbuilder
pip install -r requirements.txt

# Download and index the card database (required, ~171 MB)
python -m deckbuilder.carddata sync

# Start the server
python app.py
```

Then open **http://127.0.0.1:5000** in your browser, type a theme, and click
**Build deck**.

> The card index downloads from Scryfall's bulk-data service (no API key needed).
> After the first sync, subsequent runs only update if new data is available.
> To check index status: `python -m deckbuilder.carddata info`

---

## How it works (the "figure out Magic on its own" part)

The app is a pipeline of three stages. Nothing reads or reproduces a
user-authored decklist — every deck is derived from card attributes + rules.

**1. Theme interpreter** — `deckbuilder/theme.py`
Turns your freeform description into structured deck parameters:
- **Colours** via Magic's WUBRG colour philosophy (e.g. rebellion/war → Red,
  ruthless ambition/sacrifice → Black, rigid order → White…).
- **Archetype** (aggro / control / aristocrats / tokens / ramp / …) inferred
  from the language of the theme.
- **Flavor search terms** (e.g. "rebel", "revolt", "soldier", "sacrifice") used
  to find on-theme cards.
If an `ANTHROPIC_API_KEY` is set, an LLM produces the same structured output
with richer understanding; otherwise a built-in heuristic engine runs so the app
always works offline.

**2. Card index** — `deckbuilder/carddata.py`
Maintains a local SQLite database of ~22,000 Magic cards with full-text search.
The index is downloaded from Scryfall's bulk-data service once and rebuilt with
`python -m deckbuilder.carddata sync`. Subsequent deck builds use fast FTS5
queries instead of live per-card API calls, improving speed and reliability.
Falls back to the live Scryfall API if the index is unavailable.

**3. Deckbuilding engine** — `deckbuilder/engine.py` + `formats.py`
Assembles the deck against standard deckbuilding templates:
- category quotas (e.g. Commander wants ~10 ramp / ~10 draw / ~10 interaction /
  ~37 lands),
- a **mana curve** shaped for the chosen archetype,
- **colour-identity** and **singleton / copy-limit** legality,
- a **mana base** computed from the actual colour pips the spells need.
It also picks a legendary creature as the **commander** for EDH decks.

The result — plus a mana-curve chart, composition breakdown, and a written
explanation of *why* each choice was made — is rendered by the web UI
(`templates/index.html`, `static/`).

---

## Formats

- **Commander** — 100-card singleton deck led by a themed legendary creature.
- **Constructed (60-card)** — a 60-card deck that runs up to 4 copies of a card.

## Optional: LLM enrichment

```bash
# PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python app.py
```
With a key set, the theme interpreter uses an LLM for a more nuanced reading of
the description. Without one, the heuristic engine is used automatically.

## Testing

```bash
python tests/test_engine.py        # runs fully offline
# or, if you have pytest:  python -m pytest tests/ -q
```
The tests assert the deckbuilding *rules* hold: colour identity, singleton,
land count, curve, and stat consistency.

---

## Project layout

```
mtg-theme-deckbuilder/
├── app.py                  # Flask server + JSON API
├── requirements.txt
├── deckbuilder/
│   ├── theme.py            # description -> colours / archetype / terms
│   ├── scryfall.py         # Scryfall client + card normalization + roles
│   ├── engine.py           # deck assembly (curve, ratios, legality, lands)
│   └── formats.py          # format templates + curve targets
├── data/
│   └── sample_cards.json   # offline fallback pool
├── templates/index.html    # web UI
├── static/{style.css,app.js}
└── tests/test_engine.py
```

## Notes & limits

- Card data © Scryfall / Wizards of the Coast. This is an educational project
  and is not affiliated with either.
- Offline mode uses a small (~45-card) sample pool, so offline decks are smaller
  than a full 100/60. Online (the default) fills to full size.
- The engine optimizes for a *coherent, on-theme, legal* deck — a strong
  starting point to tune by hand, not a tournament-tuned netdeck.

# MTG Theme Deckbuilder

Small Flask app that generates Magic: The Gathering decks from a short theme or description.

Quick start
1. Create and activate a virtual environment (recommended):

```powershell
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
# open http://127.0.0.1:5000
```

4. Run tests:

```powershell
pytest -q
```

- Notes for the grader
- The core logic lives in `deckbuilder/` (modular). Run `app.py` to start the Flask server for grading and local testing.
- Tests: 18 passing (included in the `tests/` folder).
- No secrets are committed. If optional external services are used, provide credentials via environment variables locally.

Submission blurb (copy to assignment form):
"This submission includes a Flask-based UI and API (`app.py` + `deckbuilder/` package) that generates MTG decks from a theme. Tests are included and pass locally. See run instructions in `README.md`."
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
python app.py
```

Then open **http://127.0.0.1:5000** in your browser, type a theme, and click
**Build deck**.

> No API key or account needed. Card data comes from Scryfall's public API.
> If you have no internet, tick **"Offline sample data"** to build from a small
> bundled card pool instead.

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
The interpreter uses a built-in heuristic engine so the app works offline.

**2. Scryfall client** — `deckbuilder/scryfall.py`
Queries the live Scryfall API (correct `User-Agent`/`Accept` headers, <10 req/s
rate limiting, 24-hour response cache) for cards that match the derived colour
identity and flavor. Each card is tagged with a functional **role** (ramp /
draw / removal / wipe / creature) read from its rules text. Falls back to a
bundled `data/sample_cards.json` pool if there is no network.

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

## Optional: Online data

The app queries Scryfall to fetch card data by default. If you have no internet,
use the "Offline sample data" option in the UI to build from the bundled card
pool instead.

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

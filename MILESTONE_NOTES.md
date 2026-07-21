# Milestone progress notes — ManaForge (Themed MTG Deckbuilder)

## Where the project stands this week

The application is **functionally complete and demoable end-to-end**. A user can
open the web interface, type a natural-language description of a deck, choose a
format, and receive a legal, on-theme Magic deck — with the reasoning, mana
curve, and composition shown in the UI. That is the full intended core loop.

## Technologies integrated (all planned pieces are now wired together)

| Layer | Technology | Status |
|-------|-----------|--------|
| Web interface | HTML/CSS/vanilla JS single-page UI | working — input, format select, results, curve chart |
| Web server / API | Python **Flask** (`/api/build`, `/api/health`) | working |
| External data | **Scryfall REST API** (live card data) | working — rate-limited, cached, correct headers |
| Theme reasoning | Heuristic colour-pie + archetype engine, **optional LLM** (Anthropic) | working — LLM used if a key is present, heuristic otherwise |
| Deckbuilding logic | Custom engine: curve targets, category ratios, legality, mana base | working |
| Offline fallback | Bundled `sample_cards.json` pool | working |
| Tests | Offline end-to-end test suite (6 tests) | passing |

## What "accomplishing a task through the interface" looks like

1. User enters: *"A Red Rising rebellion in brutal war against a ruthless gold
   hierarchy — ambition, sacrifice, cunning politics."*
2. The app interprets it → **Red/Black (Rakdos)**, **aggro/sacrifice** archetype,
   flavor terms *rebel, revolt, sacrifice, soldier…*
3. It queries Scryfall for matching cards, tags each by role, and assembles a
   100-card Commander deck led by a themed legendary creature.
4. The UI shows the commander, the full decklist by category, a mana-curve chart,
   the colour identity, and a written explanation of every choice.

## Design decision worth highlighting for the assignment

The core requirement was that the app **derive** a deck from Magic's own logic
rather than copy an existing decklist. That is exactly how the engine works:
it reasons from the **colour pie**, **archetype curve targets**, and
**category ratios**, and pulls only *individual card records* from Scryfall. It
never ingests or reproduces a user-built decklist. (Scryfall's `edhrec` sort is
used only as a per-card popularity/quality signal, not as a source of decklists.)

## Known limitations / next steps

- **Offline mode** uses a ~45-card sample pool, so offline decks are smaller than
  a full 100/60. The live (default) path fills to full size. → could expand the
  bundled pool or cache a bulk Scryfall download.
- **Synergy** is currently role- and flavor-based. → next iteration could detect
  explicit combos (e.g. tribal lords, sacrifice-payoff loops) and weight them.
- **Curve/land math** is heuristic. → could add a mana-symbol solver and a
  playtest/goldfish simulator to score consistency.
- LLM enrichment is optional and gated on an API key. → could add OpenAI as a
  second provider.

## How to run / demo

```bash
cd mtg-theme-deckbuilder
pip install -r requirements.txt
python app.py            # -> http://127.0.0.1:5000
python tests/test_engine.py   # offline test suite
```

*If a network/Scryfall issue occurs during a live demo, tick "Offline sample
data" in the UI and the deck still builds from the bundled pool.*

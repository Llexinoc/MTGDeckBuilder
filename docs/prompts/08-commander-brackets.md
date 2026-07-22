# Prompt: Commander brackets and power level

Run `07-deck-composition.md` first. Bracket logic sits on top of correct deck
construction, and deck sizes are still wrong.

---

Add Commander bracket support — as an input constraint and as a computed output.

## The bracket system

Wizards' official power-level scale, introduced 2025. Five brackets:

| # | Name | Character |
|---|---|---|
| 1 | Exhibition | Ultra-casual, themed, jank |
| 2 | Core | Precon level |
| 3 | Upgraded | Meaningfully tuned, still fair |
| 4 | Optimized | High power, short of cEDH |
| 5 | cEDH | Tournament, metagame-tuned |

Defined mainly by three things: how many **Game Changers** the deck runs, whether
it has **two-card infinite combos**, and **how fast it wins**.

Constraints by bracket:

- **1 and 2** — zero Game Changers, no intentional infinite combos.
- **3** — up to three Game Changers, late-game combos only.
- **4 and 5** — no restrictions.

**These rules have already changed once** (an October 2025 revision renamed
brackets, dropped tutor restrictions, and reworked the Game Changers list). Put
the thresholds in a config constant, not scattered through the code, and make
them easy to update. Do not bake the current numbers into logic you'd have to
hunt down later.

## Game Changers — already in your data

Scryfall exposes a `game_changer` boolean on card objects. It's in the bulk file
you already sync, and it is the authoritative source — the list is maintained by
Wizards and Scryfall tracks changes.

1. Add a `game_changer INTEGER` column to the cards table in `carddata.py`,
   populated from the card object's `game_changer` field.
2. Re-run `python -m deckbuilder.carddata sync` to backfill it.
3. Never hardcode the list of Game Changer card names. Read the flag from the
   data so updates arrive with the next sync.

While you're editing the schema: `cmc` is declared `INTEGER` but mana value is a
float in Scryfall. Change it to `REAL`.

## Bracket as input

Accept a bracket in the request — parsed from the description ("bracket 3 deck",
"casual", "cEDH", "precon level") and as an explicit `bracket` field on
`/api/build`, 1–5, optional.

When set, it constrains the build:

- Filter out Game Changers entirely for brackets 1–2; cap at three for bracket 3.
- Bias card selection toward the bracket's power level — efficient tutors, fast
  mana, and free interaction belong in 4–5, not in 1–2.
- Adjust the expected win turn: lower brackets want a slower, more durable curve.

If no bracket is given, default to 2 or 3 and say which in the response. Silently
building an unbounded-power deck for someone who asked for a casual theme is the
current failure.

## Bracket as output

Always classify the finished deck and report it, whether or not one was
requested. Return the bracket, the reasoning, and the evidence: which Game
Changers are in the deck, any detected combos, the curve, and the estimated win
turn.

If the deck lands outside the requested bracket, say so explicitly rather than
quietly returning it.

## Combo detection

Detecting two-card infinite combos from card text is genuinely hard and is not
worth attempting with heuristics. Use the **Commander Spellbook** API, which
exists for exactly this and takes a card list. Cache results and treat the
service as optional — if it's unavailable, report combo status as unknown rather
than blocking the build or guessing.

Do not attempt to infer combos from oracle text pattern-matching. It produces
confident wrong answers.

## Deck research — use the right source

Scryfall has **no decklists and no bracket data**. It is a card database. Do not
try to query it for existing decks.

For "what do decks like this usually run," the sources are EDHREC, Moxfield, and
Archidekt. `theme.py` already fetches from Moxfield and Archidekt — extend that
rather than building something new.

Where reference decklists are available, use them to inform staple selection for
a given commander and theme, not to copy a list wholesale. Respect each service's
rate limits and terms, cache aggressively, and honor `no_network`.

## Tests

- A bracket 1 or 2 build contains zero cards where `game_changer` is true.
- A bracket 3 build contains at most three.
- A bracket 4 or 5 build is unconstrained on that axis.
- Every deck returns a computed bracket with its evidence, including when none
  was requested.
- A deck that can't hit the requested bracket reports the mismatch rather than
  returning silently.
- Bracket thresholds live in one config constant, and changing it changes
  behavior without touching build logic.
- Commander Spellbook being unreachable yields "combos unknown" and a completed
  deck, not an error.

# Prompt: card type balance and LLM re-ranking

Run `07-deck-composition.md` first — this builds on its category quotas.

---

Two changes to `deckbuilder/engine.py`, both about picking better cards.

## Part 1 — balance by card type

The builder parses `type_line` but only branches on land and creature
(`is_land`, `is_creature`, and the generic `types` list). Instants, sorceries,
artifacts, enchantments, and planeswalkers are never tracked as categories, so
nothing balances them. A deck can come out as 60 creatures and no interaction.

Derive the full type set from `type_line` for every card — instant, sorcery,
artifact, enchantment, planeswalker, battle, creature, land — and make those
counts first-class in the composition step.

Type matters independently of what a card *does*. A removal package that's
entirely sorcery-speed plays very differently from one that's mostly instants,
even when the card count is identical. So:

- Track the instant/sorcery split within interaction, not just the total.
  Instant-speed interaction is more valuable in Commander; a deck whose removal
  is all sorceries is worse than the count suggests. Prefer instants when
  otherwise equivalent.
- Enchantment- and artifact-heavy decks need enchantment and artifact removal
  available in the meta, but more importantly they need their own permanents to
  survive — factor that into how much protection the deck runs.
- Planeswalkers count toward the theme payload, not toward creatures.

Report the type distribution in the build response alongside the curve, so the
shape is visible without counting cards.

Do not invent a fixed type quota. The right instant/sorcery ratio depends on the
archetype; what's wrong today is that the number isn't considered at all.

## Part 2 — LLM re-ranking of candidates

Card selection is currently full-text search plus filters, which is fast but has
no sense of whether a card is actually on-theme — it matches words, not meaning.

Add a re-ranking step between retrieval and selection:

1. **Retrieve** 100–200 candidates per category using the existing FTS and SQL
   filters. Keep this deterministic and cheap. Do not change it.
2. **Re-rank** that candidate set with a single Claude call: pass the theme, the
   resolved archetype, and the candidates as a compact list — name, type line,
   mana cost, and oracle text, nothing else. Ask for scores on thematic and
   mechanical fit.
3. **Select** the final deck from the re-ranked list using the existing quotas
   and legality rules.

Constraints that matter:

- **One call per build, not per card.** Batch the whole candidate set. If it
  doesn't fit in context, chunk it — but keep the number of calls bounded and
  logged.
- **The model scores, it does not build.** It never chooses counts, never
  decides the deck is finished, never picks lands. All legality and composition
  logic stays in code. A model that can't reliably count to 100 must not be the
  thing counting to 100.
- **Validate the response.** Structured JSON, parsed into a schema. Discard any
  card name that isn't in the candidate set you sent — models will invent
  plausible card names, and a hallucinated card that reaches the deck is a bug
  that's hard to trace.
- **Degrade cleanly.** No API key, a failed call, malformed output, or
  `no_network` all fall back to the current FTS ordering. Re-ranking is an
  improvement, never a dependency. Report in `sources` whether it ran.
- **Cache by theme and candidate set** so repeated builds of the same theme
  don't re-pay for it.

Use the existing `ANTHROPIC_MODEL` env var. Haiku is a reasonable default for
scoring; make it configurable, since a stronger model may be worth it here.

## Tests

- A deck's type distribution appears in the response and the counts are correct.
- Interaction is not entirely sorcery-speed when instant-speed options existed in
  the candidate pool.
- Re-ranking makes exactly one API call per build, not one per card — assert on
  the mocked client's call count.
- A card name returned by the model that wasn't in the candidate set is discarded
  and never reaches the deck.
- With the API key unset, with the call failing, and with `no_network=True`, the
  build still completes using FTS ordering, and `sources` reports re-ranking as
  off.
- Malformed JSON from the model falls back rather than raising.

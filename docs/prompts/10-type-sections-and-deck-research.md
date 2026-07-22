# Prompt: type sections and deck research

---

## Step 0 — confirm the LLM path is actually running

Check `/api/health` for `llm_enabled`. If it's false, `ANTHROPIC_API_KEY` isn't
set and every LLM interpretation path silently falls back to heuristics — which
would explain most of the bad theme interpretation.

Restore `.env.example` documenting `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL`,
make sure `.env` is gitignored and loaded at startup, and have `/api/build`
report in `sources` whether LLM interpretation actually ran for that build. It
should not be possible to get a heuristic-only deck without knowing it.

## Part 1 — group the decklist by card type

Show the deck in sections by type, each with its own count, so the shape is
obvious at a glance. Order:

Commander, Creatures, Planeswalkers, Instants, Sorceries, Artifacts,
Enchantments, Battles, Lands.

Omit empty sections. Show the count in each heading, and the deck total
somewhere unmissable — that's the number people check first.

**Each card appears in exactly one section.** Many cards have multiple types and
double-counting them will make the sections sum to more than the deck. Pick one
canonical bucket per card with a fixed precedence:

1. Land (a land that's also an artifact is still a land)
2. Creature (an Artifact Creature is a creature)
3. Planeswalker
4. Battle
5. Instant
6. Sorcery
7. Artifact
8. Enchantment

Assert in a test that the section counts sum to the deck total. If they don't,
the precedence has a hole.

Cards with `card_faces` are typed by their front face.

Keep the existing text-decklist toggle working, grouped the same way.

## Part 2 — research real decks

Scryfall has no decklists. For "what do decks like this actually run," the
source is EDHREC — it aggregates real Commander decks and exposes, per
commander, the cards played most often and their synergy scores. Moxfield and
Archidekt are alternatives, and `theme.py` already fetches from both.

Use it as a signal, not a template:

1. Once a commander is chosen, look up its most-played and highest-synergy cards.
2. Feed those into candidate retrieval as a scoring boost — a card that appears
   in many real decks with this commander is more likely correct than one that
   merely matches a keyword.
3. Never copy a list wholesale. The point is a themed deck, not a netdeck. Cap
   how much of the final deck can come from the staples list so the theme still
   drives it.

Requirements:

- Cache responses on disk with a long TTL. This data changes slowly and the
  service is free — don't hammer it.
- Honor `no_network`, and degrade to index-only selection when unavailable.
  Deck research is an enhancement, never a dependency.
- Identify the client honestly in the User-Agent and respect rate limits and
  terms of service.
- Report in `sources` whether research data informed the build.

For Standard there's no commander to key on, so this applies to Commander only.
Don't fabricate an equivalent for 60-card.

## Tests

- Section counts sum to the deck total, across many themes.
- A card with multiple types appears in exactly one section, matching the stated
  precedence.
- Double-faced cards are typed by their front face.
- With research unavailable or `no_network` set, the build completes and
  `sources` reports research as off.
- Staples cannot exceed the configured share of the final deck.

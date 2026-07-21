# Prompt: fix theme resolution

---

Themes are being matched as raw text, so a theme naming a character returns
unrelated cards that happen to share a word with it. Fix the interpretation
layer.

## Prerequisite — do this first and re-test before touching theme logic

Cards with `card_faces` have no top-level `oracle_text`, `mana_cost`,
`type_line`, or `image_uris`. Join them from the faces everywhere those fields
are read — the index build, the FTS rows, and the response serializer. Right now
every double-faced card is indexed with empty rules text and is invisible to
search, including many legendary creatures that should be surfacing as
commanders.

Then run `python -m deckbuilder.carddata sync` so the index includes recent
sets. This alone may fix a large share of the bad results. Verify before
continuing.

## Theme resolution order

1. **Named match.** Query the index by card name before anything else. If the
   theme names a card that exists, that card anchors the deck — and if it's a
   legendary creature, it becomes the default commander. Build around *its*
   printed mechanics, not around the words in the theme.
2. **Mechanical mapping.** Only when no named match exists — map the concept to
   archetypes: card types, keywords, color identity, known synergy packages.
   Then search on those.
3. **Text search last.** Never let raw FTS on the user's literal words drive
   card selection. Matching a substring of a word in the theme is not a reason
   to include a card.

Implement this as a general rule. Do not special-case individual themes or
hardcode any theme-to-card mapping.

## Compound themes

Most requests carry more than one idea — a creature type, a win condition, a
support theme, and constraints, in plain English. Parse the description into a
structured plan before searching anything. The plan is typed, not a bag of
words:

- **tribal** — a creature type
- **strategy** — how the deck wins or what it does (mill, aristocrats, voltron,
  stax, combo, aggro)
- **support** — secondary themes that enable the strategy
- **constraints** — format, color limits, budget, power level, explicit
  exclusions

Handle ordinary phrasing: "with", "but no", "on a budget", "casual", "cheap",
"focused on", "splashing". Negations are constraints and must be honored — if
someone excludes something, it doesn't appear.

Then prioritize. Axes frequently conflict, because the color identity that
supports one rarely supports all of them, and some are actively anti-synergistic.
Resolve it the way a human would:

1. Weight the axes. A named card outranks a creature type; a creature type
   outranks a strategy; a strategy outranks a support theme. Explicit user
   emphasis overrides this ordering.
2. Choose the commander that covers the most high-weight axes, then build toward
   the remainder within that color identity.
3. When an axis can't be served — no legal color overlap, no meaningful card
   pool — demote it rather than forcing it, and say so.

Never silently drop an axis. If the deck can't be all three things the user
asked for, the response says which one gave way and why. A deck that quietly
ignores a third of the request reads as broken even when the cards are good.

The LLM step in `theme.py` is the right place for this parse — it's the part
LLMs are actually good at. Have it return structured JSON matching the plan
above, validate the shape, and fall back to mechanical mapping if the call fails
or returns something malformed. Do not let free text from the model reach the
search layer unvalidated.

## Acceptance criteria

Write regression tests covering these shapes. Pick your own example themes.

1. **Theme names a legendary creature.** That creature is the commander. Cards
   that match only on a shared substring are absent. Deck color identity equals
   the commander's exactly, and every card falls within it.
2. **Theme names a non-legendary card.** The card is included, a thematically
   appropriate commander is chosen separately, and the deck is built around the
   named card's mechanics.
3. **Theme is purely conceptual, no card matches the name.** Falls through to
   mechanical mapping and produces a coherent archetype.
4. **Theme names a double-faced legendary creature.** Confirms the face-joining
   fix holds end to end — this is the case most likely to regress.
5. **Compound theme, axes compatible.** A creature type plus a strategy plus a
   support theme that can coexist in one color identity. All three are visibly
   present in the decklist.
6. **Compound theme, axes conflict.** The same shape, but with axes whose usual
   color identities don't overlap. Assert the deck is still coherent and legal,
   and that the response names which axis was demoted.
7. **Theme with an explicit exclusion.** Assert the excluded thing appears
   nowhere in the deck.

Every deck must also satisfy: exactly 100 cards, singleton except basics,
roughly 36–38 lands, and a nonland composition that visibly reflects the
resolved archetype rather than generic goodstuff.

## Also

Log the resolved interpretation — matched card name if any, chosen archetype,
color identity, final search terms — and return it in the build response. Right
now there's no way to tell whether a bad deck came from bad interpretation or
bad search.

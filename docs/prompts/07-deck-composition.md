# Prompt: deck construction and balance

---

Deck composition is wrong. Fix the construction logic so both formats produce
legal, playable decks. Treat this as constraint satisfaction with a hard
validation gate at the end — not "fill some categories and return whatever."

**Terminology:** MV means Mana Value — the total cost of a card, what used to be
called converted mana cost. Scryfall never renamed the field, so in the data and
in our index it is `cmc`. Read `cmc`; there is no `mv` field.

## Format rules — hard constraints, validate before returning

**Commander (100 cards)**

- Exactly 100 cards including the commander. Not 99, not 101.
- Singleton: one copy of each card except basic lands.
- Every card's `color_identity` must be a subset of the commander's.
- Commander must be a legendary creature, or a card whose text says it can be
  your commander.
- Every card must be `legalities.commander == "legal"`.

**Standard (60 cards)**

- Exactly 60 in the maindeck. 15-card sideboard optional.
- Maximum 4 copies of any card except basic lands.
- Every card must be `legalities.standard == "legal"`.

If a build can't satisfy these, fail loudly with a specific reason. Never return
an illegal deck — a 98-card Commander list or a fifth copy of a card is worse
than an error message.

## Ban list toggle

Plenty of playgroups ignore the ban list. Add a toggle for it.

- UI control in the build form, labeled "Enforce ban list", on by default.
- `enforce_ban_list` boolean in the `/api/build` request, defaulting to `true`.

Semantics matter here, because `legalities.commander` has four values:

- `legal` — always included.
- `banned` — excluded when the toggle is on, included when off. This is what the
  toggle controls.
- `not_legal` — excluded either way. These aren't paper Commander cards at all:
  digital-only Alchemy cards, playtest cards, and similar. Turning off the ban
  list shouldn't smuggle in cards that don't physically exist.
- `restricted` — doesn't apply to Commander; treat as legal if encountered.

Card count, singleton, and color identity rules still apply with the toggle off.
It relaxes the ban list only, not the format.

Badge banned cards visibly in the decklist so the user can see exactly which
ones a rules-enforced table would reject, and report the setting plus a list of
included banned cards in the build response. Someone who flips this on and off
should be able to tell what changed.

Apply the same pattern to Standard's ban list.

## Composition

Derive these from the deck's archetype rather than hardcoding one template.
Ranges below are starting points, not laws.

**Commander**, of 100 total:

| Role | Count |
|---|---|
| Commander | 1 |
| Lands | 36–38 |
| Ramp | 10–12 |
| Card draw / advantage | 8–12 |
| Targeted removal | 8–10 |
| Board wipes | 2–4 |
| Theme payload | remainder, ~28–33 |
| Win conditions | 3–5, may overlap payload |

**Standard**, of 60 total:

| Archetype | Lands | Curve peak |
|---|---|---|
| Aggro | 20–22 | 1–2 MV |
| Midrange | 23–25 | 2–3 MV |
| Control | 25–27 | 3–4 MV |

Play 4 copies of cards central to the plan, fewer for situational or expensive
ones. A Standard deck that's 60 singletons is a bug.

## The 60-card format needs different instincts

Most of the logic here is written around Commander, and applying it unchanged to
Standard produces bad decks. Three things invert.

**Consistency beats variety.** Commander is singleton, so variety is forced and
toolboxing is correct. A 60-card deck wants to draw the same cards every game.
Default to 4 copies of anything central to the plan and only go lower for a
reason: legendary creatures that are dead in multiples, expensive cards you want
one of late, situational answers. If the builder is producing lots of 1-ofs and
2-ofs, it's applying Commander instincts and is wrong.

**There's no commander to anchor colors.** Every color decision downstream in
this app assumes a commander's identity to filter against. Standard has none, so
colors must be derived from the theme's card pool instead: find the colors that
cover the most on-theme cards, and prefer one or two. Three colors demands real
mana fixing and should only happen when the theme genuinely can't be served in
two. Once chosen, that color set becomes the filter the commander's identity
would have been.

**Rotation makes stale data dangerous.** Standard rotates, and
`legalities.standard` changes when it does. A card index built before a rotation
will happily report rotated cards as legal, and the app will confidently produce
an illegal deck with no error. When building Standard, check the index's
`updated_at` and warn if it's more than a week old. This risk doesn't exist for
Commander, where legality is nearly static.

## Sideboard

If a sideboard is requested, build 15 cards that answer what the deck loses to —
not more copies of what's already in the maindeck. Removal for problem
permanents, graveyard hate, artifact and enchantment answers, cards that come in
against faster or slower opponents.

Note which maindeck cards each sideboard card is meant to replace. A sideboard
with no swap plan is a list of 15 cards, not a sideboard.

## Standard mana base

Two-color decks are the default target. Include the dual lands legal in the
current Standard pool, weighted by pip count, and fill with basics. Lands that
enter tapped are a real cost in a format this fast — an aggro deck wants few of
them, a control deck tolerates more.

Utility and colorless lands are a luxury in 60 cards. One or two at most, and
only if the deck can afford the colored source loss.

## Adaptive land count

Do not hardcode a land number. Derive it from the finished curve: higher average
mana value means more lands, and cheap ramp partially substitutes for them.
Compute average MV across nonland cards, count ramp pieces at 2 MV or less, and
adjust within the ranges above. Log the computed value and the inputs.

## Curve

Target a shape, not just an average. Most decks want more cards at 2–3 MV than
at 5+. After assembly, check the distribution and swap high-cost cards for
cheaper ones with similar function if the top of the curve is overloaded.

For Commander, average MV around 3.0–3.5 is a reasonable default. Aggressive
decks want lower, ramp-heavy decks tolerate higher.

## Mana base

Count colored pips across the nonland cards, per color. Allocate colored sources
proportional to those pip counts — a color appearing in three cards does not
deserve equal footing with one in twenty.

Prefer lands that produce multiple relevant colors over basics, within legality
and budget. Fill the remainder with basics weighted by pip count. A color whose
pips are concentrated in early-drop cards needs more sources than the raw
proportion suggests, since those cards are dead without it on turn two or three.

Utility lands that produce no colored mana count against the color base — don't
let them crowd it out.

## Category assignment

A card can serve more than one role. A creature that draws when it attacks is
both payload and card draw. Count it once toward the total, but let it satisfy
multiple quota checks rather than double-counting it as two physical slots —
that's how decks end up short.

## Validation gate

Before returning any deck, run a validator that checks every hard constraint
above and refuses to pass a deck that violates one. Return the validation result
in the build response alongside the computed stats — total, land count, average
MV, curve histogram, pip distribution, and category counts. The user should be
able to see the deck's shape without counting cards.

## Tests

- Exactly 100 for Commander, 60 for Standard, across many themes.
- No duplicates outside basics in Commander; no fifth copies in Standard.
- Every card within the commander's color identity — build a mono-color and a
  four-color case.
- Land count moves in the right direction when average MV rises.
- Colored sources track pip counts, not just the number of colors.
- A deliberately impossible request fails with a clear error instead of an
  undersized deck.
- With `enforce_ban_list` on, no `banned` card appears. With it off, banned cards
  may appear and are badged — but `not_legal` cards never appear either way.
- A Standard build defaults to playsets, not singletons — assert the deck
  contains multiple 4-ofs.
- Standard color selection lands on one or two colors for a theme that can be
  served in two, and every card falls within the chosen colors.
- A stale index triggers the rotation warning on a Standard build.
- A requested sideboard is exactly 15 cards and names what each card swaps in
  for.

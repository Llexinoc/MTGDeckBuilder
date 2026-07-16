# PP4 Feature List — ManaForge MVP

## Product focus
This feature list is scoped to the Minimum Viable Product for the themed MTG deckbuilder. It prioritizes the core experience of turning a natural-language theme into a playable, legal deck.

## Core features
1. Theme-based deck generation
   - Accept a natural-language prompt describing the desired deck theme.
   - Interpret the description into deck intent such as colours, archetype, and flavor themes.

2. Deckbuilding logic
   - Build a deck from card attributes and rules rather than copying an existing decklist.
   - Enforce basic legality and structure constraints for the selected format.

3. Format support
   - Support Commander-style singleton decks and Constructed-style 60-card decks.
   - Select the appropriate deck skeleton and copy limits per format.

4. Card sourcing
   - Pull candidate cards from the live Scryfall API when available.
   - Fall back to bundled offline sample data when network access is unavailable.

5. Role-based deck composition
   - Assemble decks with a functional mix of role categories such as ramp, draw, removal, wipes, and themed creatures/payoffs.

6. Deck explanation and summary
   - Provide a plain-language explanation of why the deck was built the way it was.
   - Show deck statistics such as colour identity, mana curve, lands, and card composition.

## Out of scope for this phase
- Login or user accounts
- Settings menus
- Dark mode or visual theme customization
- Profile saving or long-term history
- Non-essential polish features

## Success criteria
- A user can enter a theme, generate a deck, and receive a coherent, playable result in one interaction.
- The generated deck is structurally legal for the selected format.
- The workflow works online and offline through the fallback path.

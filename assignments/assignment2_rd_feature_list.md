# Assignment 2 — R&D Feature List

## Purpose
This list captures the research and development areas required to build the ManaForge MVP effectively and reliably.

## R&D focus areas
1. Theme interpretation
   - Research how to translate natural-language prompts into colours, archetype, and flavor terms.
   - Determine whether heuristic rules alone are sufficient or whether optional LLM support should be integrated.

2. Card data integration
   - Research the Scryfall API structure, card metadata, and filtering options needed for deck generation.
   - Define how to tag cards by role and relevance for deckbuilding.

3. Deckbuilding engine design
   - Research the rules needed to create coherent decks: mana curve, category quotas, colour identity, singleton limits, and land count.
   - Define a deterministic approach for assembling a legal deck from a card pool.

4. Offline capability
   - Research a reliable offline fallback strategy using bundled sample cards.
   - Ensure the application can still generate a usable deck without network access.

5. Reliability and testing
   - Research validation approaches for deck legality and composition consistency.
   - Add automated tests to verify the core deckbuilding rules.

6. Performance and maintainability
   - Keep the architecture modular so the theme interpreter, card retrieval, and deckbuilder can evolve independently.
   - Avoid unnecessary complexity in the MVP.

## MVP priority
The highest-priority R&D work is the end-to-end pipeline:
- interpret the theme
- retrieve relevant cards
- build a legal deck
- present the result in the UI

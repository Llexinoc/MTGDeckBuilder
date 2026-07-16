# Assignment 3 — GUI Feature List

## Purpose
This GUI feature list defines the user interface requirements for the ManaForge MVP before implementation.

## Core GUI features
1. Input interface
   - Provide a text area where the user can describe the deck theme.
   - Include example prompts to guide first-time use.

2. Format selection
   - Allow the user to choose between Commander and Constructed formats.
   - Clearly communicate the deck size and structure implied by the selected format.

3. Build controls
   - Include a Build deck action button.
   - Provide an offline toggle so the user can request sample-data generation.

4. Results area
   - Display the generated deck summary, including the inferred colours and archetype.
   - Show a plain-language explanation of the deck choices.

5. Deck visualization
   - Show a mana curve chart for the generated deck.
   - Show a composition breakdown by category and type.

6. Decklist presentation
   - Present the generated deck grouped by category such as commander, ramp, draw, removal, wipes, and lands.
   - Make the decklist easy to scan and read.

7. Feedback and error handling
   - Show clear loading, success, and error states.
   - Provide a helpful message if input is empty or generation fails.

## UI scope for this phase
The interface should stay focused on the core deckbuilding workflow:
- enter theme
- build deck
- review results

## Out of scope for this phase
- Login or account flows
- Settings pages
- Dark mode
- Advanced customization panels

# Prompt: rename to Brewbot and theme the UI

---

The app is being renamed **Brewbot**. "Brewing" is the MTG term for building an
original deck rather than copying one — the name says the app brews you a deck
from a description. Rename it, then rework the UI around that idea.

## Step 1 — rename

Change the user-facing name to Brewbot everywhere it appears: page `<title>`,
headings, `README.md`, docstrings, log messages, and the `/api/health` response.

Leave alone:

- The `deckbuilder/` package and all module names. Renaming Python packages is
  pure churn and breaks imports for no user-visible gain.
- Route paths. `/api/build` stays.
- The git repo and directory name — I'll handle that separately.

Add a one-line description under the wordmark: what it does, in plain language,
no jargon.

## Step 2 — visual identity

Warm copper and amber against dark slate — alchemical, a little mechanical.
Adjust if it fights the existing CSS, but stay away from generic Bootstrap blue.

- Define the palette as CSS custom properties in `static/style.css` so it can be
  retuned in one place. No hardcoded hex values scattered through the markup.
- Two typefaces at most. A slightly technical or monospace accent face for the
  wordmark and labels reads as "bot"; keep body text plainly legible.
- Build a simple wordmark in inline SVG — no image asset, no icon font. A
  flask, gear, or cauldron silhouette next to the name is enough.
- Card art is the visual centerpiece. The chrome should recede — dark neutral
  surfaces, restrained accent use, nothing competing with the cards.

Check contrast ratios. Amber on dark slate fails WCAG AA easily if you're not
watching; body text needs 4.5:1 minimum.

## Step 3 — microcopy

Let the name carry through the interface without overdoing it.

- The primary action is "Brew" rather than "Build".
- The result is "your brew" or "this brew".
- Rotating status messages during the build, in brewing voice — the deck build
  takes several seconds and that's dead air right now.
- Empty state before first build should suggest what to type. Show two or three
  example descriptions as clickable chips that fill the input.
- Error states stay plain and literal. When something breaks, tell the user what
  happened — no cute flavor on failure messages.

Keep the decklist itself clinical. Card names, counts, and categories are
reference data people copy out; don't decorate them.

## Constraints

Don't restructure the templates or rewrite the JS beyond what the theming needs.
This is a visual and naming pass, not a refactor.

## Verify

Load the app, build a deck, and confirm: no instance of the old name remains in
the UI, the layout holds at mobile and desktop widths, contrast passes AA, and
the status messages actually appear during a build rather than flashing past.
Run the test suite — some tests may assert on the old name.

# Prompt: commit, card images, cleanup

---

Three steps, in order. Stop and show me the result of each before continuing.

## Step 1 — commit first

This repo has no commits. Everything is untracked, so nothing is recoverable if
a later step deletes the wrong thing. Before touching anything:

```
git add -A
git commit -m "Initial commit: deckbuilder app, card data ingest, project docs"
```

Confirm `data/` stayed out of the commit — it's gitignored and must remain so.

## Step 2 — display card art

Scryfall serves the images. Hotlink `cards.scryfall.io`; don't download or
re-host. Use `image_uris.normal` for the deck grid, `small` for dense views.
Pass the URL through from the index into the build response rather than fetching
it at render time.

Two cases that otherwise render blank:

- **Double-faced cards have no top-level `image_uris`** — they're on
  `card_faces[0].image_uris` and `card_faces[1].image_uris`. Fall back to the
  first face.
- **`image_status` of `missing` or `placeholder`** means there's no real art.
  Render the card name in a styled frame instead.

In `templates/index.html`, render the decklist as a CSS grid grouped by the
existing categories. No framework.

- Preserve the 5:7 aspect ratio.
- `loading="lazy"` on every image — 100 eager images will stall the page.
- `alt` is always the card name.
- Keep the name visible as a caption; art alone isn't identifiable at grid size.
- Hover or tap enlarges, via CSS transform. No lightbox library.
- Small flip control on double-faced cards.
- Keep a toggle back to the text decklist — that's what people paste elsewhere.

Placeholder at the right aspect ratio while loading so the grid doesn't reflow,
and an `onerror` swap to the name-frame fallback.

Commit when this works.

## Step 3 — cleanup

Find what the running app doesn't need. **Report the full list and wait for my
approval before deleting anything.**

Look for: debug and scratch scripts, modules with no inbound imports, unused
functions and constants, dead branches behind flags that no longer exist,
duplicate implementations, `requirements.txt` entries nothing imports, and
committed artifacts that should be generated.

Before flagging anything as unused, confirm it isn't:

- Referenced from a Jinja template by string name
- A Flask route, CLI entry point, or `__main__` block — no callers in the
  codebase, but not dead
- Imported dynamically via `importlib` or `getattr`
- Referenced in `static/` JS or in tests
- Reachable only through the sample-pool or no-network fallback paths

**Do not delete `data/`.** Regenerable but expensive — the index takes a full
bulk download to rebuild.

Group findings by confidence — certain, probable, unsure. I decide on anything
below certain.

## Verify

Start the app, build a deck containing at least one double-faced card, confirm
the grid renders with no blank tiles at mobile and desktop widths. Run the test
suite. Then confirm a fresh clone still works end to end.

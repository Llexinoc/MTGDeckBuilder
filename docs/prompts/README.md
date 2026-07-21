# Task prompts

One-shot briefs for coding agents. Paste the content below the `---` into
Copilot Chat in Agent mode.

Durable project rules live in `.github/copilot-instructions.md` instead — those
load automatically and don't need pasting.

| Prompt | Purpose | Status |
|---|---|---|
| `01-card-data-ingest.md` | Build `deckbuilder/carddata.py` and the SQLite index | done |
| `02-audit-scryfall-calls.md` | Read-only audit of how the app calls Scryfall | done |
| `03-offline-and-429.md` | Split the `offline` flag, add 429 retry | |
| `04-theme-resolution.md` | Named-match-first resolution, compound theme parsing | |
| `05-images-and-cleanup.md` | Render card art, remove unused files | |
| `06-brewbot-rebrand.md` | Rename to Brewbot, theme the UI | |

## Order

Run `04` before `05`. The double-faced card fix in `04` is what makes card art
render correctly, so doing it first turns half of `05` into a verification step.

Commit before running `05` — it deletes files.

## Notes

Prompts deliberately contain no named example cards or themes. An agent given
one vivid example tends to satisfy it with a special case rather than build the
general rule. Keep your own test themes out of the prompts and use them as
smoke tests afterward, so they're checks the agent couldn't have gamed.

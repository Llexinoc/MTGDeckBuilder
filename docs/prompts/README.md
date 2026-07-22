# Task prompts

One-shot briefs for coding agents. Paste the content below the `---` into
Copilot Chat in Agent mode.

Durable project rules live in `.github/copilot-instructions.md` instead — those
load automatically and don't need pasting.

| Prompt | Purpose | Status |
|---|---|---|
| `00-git-hygiene.md` | Establish git history, commit rules, accurate reporting | run first |
| `01-card-data-ingest.md` | Build `deckbuilder/carddata.py` and the SQLite index | done |
| `02-audit-scryfall-calls.md` | Read-only audit of how the app calls Scryfall | done |
| `03-offline-and-429.md` | Split the `offline` flag, add 429 retry | |
| `04-theme-resolution.md` | Named-match-first resolution, compound theme parsing | |
| `05-images-and-cleanup.md` | Render card art, remove unused files | |
| `06-brewbot-rebrand.md` | Rename to Brewbot, theme the UI | |
| `07-deck-composition.md` | Legal 60/100-card decks, curve and mana balance | |
| `08-commander-brackets.md` | Bracket 1–5 power level, Game Changers, combo detection | after 07 |
| `09-card-types-and-reranking.md` | Type balance, LLM re-ranking of candidates | after 07 |
| `10-type-sections-and-deck-research.md` | Decklist sections by type, EDHREC deck research | after 09 |

## Order

Run `04` before `05`. The double-faced card fix in `04` is what makes card art
render correctly, so doing it first turns half of `05` into a verification step.

Commit before running `05` — it deletes files.

## Notes

Prompts deliberately contain no named example cards or themes. An agent given
one vivid example tends to satisfy it with a special case rather than build the
general rule. Keep your own test themes out of the prompts and use them as
smoke tests afterward, so they're checks the agent couldn't have gamed.

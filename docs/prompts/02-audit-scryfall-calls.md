# Prompt: audit how the app talks to Scryfall

Paste below the line into Copilot Chat. This is read-only — no fixes yet.

---

Investigate how this app currently gets card data from Scryfall. Do not change
any code. Report findings only.

Answer these questions, citing the specific file and line numbers for each:

1. Every place the codebase makes an HTTP request to `api.scryfall.com` — list
   them all. Search for `scryfall`, `requests.`, `httpx`, `urlopen`, and
   `fetch(` across the repo.

2. For each call site: is it inside a loop, a list comprehension, or a function
   called once per card? I want to know whether a single `/api/build` request
   fans out into one HTTP call per candidate card, or makes a bounded number of
   calls regardless of deck size.

3. Trace the path from `POST /api/build` through `build_deck()` down to the
   first network call. Show me that chain as a list of function calls.

4. For a typical Commander build, roughly how many Scryfall requests does one
   `/api/build` fire? Give a number and show the reasoning.

5. Is there any caching — in-memory dict, `functools.lru_cache`, on-disk, or
   otherwise — between the app and Scryfall? Does it survive a process restart?

6. Is there any rate limiting or delay between requests? Scryfall asks for
   50–100 ms between calls and will start returning HTTP 429 without it. Does
   the code handle a 429 or a timeout at all, or does the exception propagate up
   to the `/api/build` handler?

7. Does the `offline` flag in `/api/build` actually prevent all network calls,
   or does it only skip the LLM step?

Finish with a short verdict: does this app depend on live per-card API calls at
build time, yes or no. If yes, list which call sites would need to move to a
local index.

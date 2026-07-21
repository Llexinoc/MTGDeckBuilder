# Prompt: fix the offline flag and 429 handling

---

Two fixes to the network layer. Don't rewrite the fetch architecture — batch
`/cards/search` with a 24h disk cache stays as-is.

## 1. Split the `offline` flag

It currently doesn't prevent network access (still calls Datamuse and
Anthropic) and separately swaps in a 60-card sample pool. Two unrelated things
under one flag. Replace with:

- **`no_network`** — hard guarantee of zero outbound requests, any host.
  Enforce inside `_cached_get()` and the equivalent helpers in `expand.py` and
  `theme.py`, so it's one choke point, not scattered checks. When it blocks a
  call, log the skipped host at INFO and return the same empty shape the caller
  already handles on 404 — don't raise. Disk cache reads are still allowed.
- **Card source** — not a flag. Use `data/cards.sqlite` if present, else live
  API, else the sample pool.

`/api/build` still accepts `offline`, mapped to `no_network`, marked deprecated.

Add a `sources` object to the build response: `{"cards": "index"|"api"|"sample",
"network": bool, "llm": bool}`. Falling back to the sample pool currently fails
silently and hands the user a bad deck.

## 2. Retry on 429

In `_cached_get()`:

- 429 → 3 attempts, backoff 1s/2s/4s, honoring `Retry-After` over the schedule.
- `Timeout`/`ConnectionError` → 2 retries, same backoff.
- Exhausted → raise `ScryfallUnavailable`, not bare `RuntimeError`.
- `app.py` catches it and returns 503 with a clear message, not a 500.
- Log each retry at WARNING with attempt number and URL.

Keep the 0.12s inter-request delay.

## Verify

Mock the HTTP layer, no live calls in tests. Assert:

1. `no_network=True` makes zero requests across a full `build_deck()` —
   including the Datamuse and Anthropic paths, not just Scryfall.
2. `no_network=True` with a warm cache still returns data.
3. 429 then 200 succeeds; three 429s → 503 from `/api/build`, not 500.
4. `Retry-After: 5` beats the default backoff.
5. `sources` reports `"sample"` when neither index nor API is available.

Run them and show the output.

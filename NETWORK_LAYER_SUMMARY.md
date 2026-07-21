# Network Layer Improvements - Implementation Summary

## Overview
Fixed the offline flag and 429 handling in the MTG Deckbuilder network layer, providing hard network isolation, robust retry logic, and transparent sources tracking.

## Changes Made

### 1. Split the `offline` Flag ✓

#### New: `no_network` Parameter
- **Hard guarantee**: When `no_network=True`, zero outbound requests to any host
- **Enforcement point**: Single choke point in `_cached_get()` function
- **Graceful fallback**: Returns empty shape like 404, doesn't raise
- **Logging**: Logs blocked requests at INFO level

#### Card Sourcing (Automatic)
- Uses `data/cards.sqlite` if present
- Falls back to live Scryfall API if index unavailable
- Falls back to bundled sample pool (60 cards) if API unreachable
- **No explicit flag needed** — automatic detection

#### Backward Compatibility
- Deprecated `offline=True` parameter still works
- Maps to `no_network=True` internally
- Maintains API compatibility for existing callers

#### Sources Metadata
New `sources` object in build response:
```json
{
  "sources": {
    "cards": "index|api|sample",
    "network": true|false,
    "llm": true|false
  }
}
```
- `cards`: Which card source was used
- `network`: Whether network access was attempted
- `llm`: Whether LLM enrichment was attempted

### 2. Retry Logic on 429 ✓

#### Backoff Schedule
- **429 Rate Limit**: 3 attempts with 1s/2s/4s backoff
- **Connection Errors**: 2 retries with same backoff
- **Honors `Retry-After` header**: Uses header value over default backoff

#### Exception Handling
- `ScryfallUnavailable` exception (replaces bare `RuntimeError`)
- Logs each retry attempt at WARNING level with attempt number
- HTTP 404: Returns empty result (not an error)
- Other errors: Logged and retried or raised

#### Request Rate Limiting
- Maintains `REQUEST_DELAY = 0.12s` between requests
- Well under Scryfall's 10 req/s limit
- Prevents cache pollution

### 3. Network Isolation Enforcement ✓

Files updated to respect `no_network` flag:

#### `deckbuilder/scryfall.py`
- `_cached_get(url, params, no_network=False)`: Single enforcement point
- `ScryfallClient(no_network=True)`: Blocks `/cards/search`, `/sets`, `/cards/named`
- `resolve_set_code()`: Returns None when `no_network=True` (alias lookup only)
- `resolve_named_commander()`: Returns None when `no_network=True`

#### `deckbuilder/expand.py`
- `_datamuse_expand(query, no_network=False)`: Blocks Datamuse API
- `_llm_expand(query, no_network=False)`: Blocks Anthropic API
- `expand_query(..., no_network=False)`: Passes through to both

#### `deckbuilder/theme.py`
- `_extract_reference_cards(..., no_network=False)`: Blocks reference URL fetching
- `_resolve_set_codes(..., no_network=False)`: Passes to ScryfallClient
- `interpret(..., no_network=False)`: Passes through the stack

#### `deckbuilder/engine.py`
- `build_deck(..., no_network=False)`: New parameter (old `offline` maps here)
- Tracks `client.card_source` throughout build
- Returns `sources` metadata in response

#### `app.py`
- Accepts both `no_network` and `offline` (deprecated) parameters
- Returns 503 on `ScryfallUnavailable` (not 500)
- Clear error message for API unavailability

## Testing Coverage

**21 new tests** covering:

### No Network Flag (6 tests)
- ✓ Blocks HTTP requests when `no_network=True`
- ✓ Allows disk cache reads with `no_network=True`
- ✓ Disables card searches, set resolution, commander resolution
- ✓ Full build completes with zero network requests
- ✓ All mocked (no live calls in tests)

### Retry Logic (5 tests)
- ✓ 429 triggers retry with backoff
- ✓ `Retry-After` header honored over default backoff
- ✓ Three 429s raises `ScryfallUnavailable`
- ✓ Connection errors trigger retry
- ✓ Timeout errors trigger retry

### Sources Tracking (4 tests)
- ✓ `sources.cards = "api"` when using live API
- ✓ `sources.cards = "sample"` on fallback
- ✓ `sources.network = False` when `no_network=True`
- ✓ `sources.network = True` when `no_network=False`

### Backward Compatibility (2 tests)
- ✓ `offline=True` maps to `no_network=True`
- ✓ `offline` parameter still accepted

### Error Handling (2 tests)
- ✓ 404 returns empty result, not error
- ✓ Other HTTP errors raised/caught

### Logging (2 tests)
- ✓ Blocked requests logged at INFO
- ✓ Retry attempts logged at WARNING

### All Tests
- **40 total tests passing** (19 existing + 21 new)
- **100% mock-based** (no live API calls during testing)
- **No regressions** to existing carddata tests

## Integration Test Results

```
✓ Test 1: Building deck with no_network=True...
  - Deck built successfully
  - Sources: { "cards": "sample", "network": false, "llm": false }
  
✓ Test 2: Building deck with offline=True (deprecated)...
  - Deck built successfully
  - Sources: { "cards": "sample", "network": false, "llm": false }

✓ Test 3: Network availability reporting...
  - no_network=True reports network=False: True
  - Card source with no_network: sample
  
✓ Test 4: Response structure validation...
  - All expected 'sources' keys present
```

## API Changes

### build_deck()
```python
def build_deck(
    description: str,
    fmt: str = "commander",
    offline: bool = False,           # deprecated, use no_network
    no_network: bool = False,        # NEW: hard network isolation
    use_llm: bool = True,
    ...
) -> dict:
    # Returns dict with new "sources" key
    # Returns dict["sources"] = {
    #     "cards": "index|api|sample",
    #     "network": bool,
    #     "llm": bool
    # }
```

### POST /api/build
```json
// Request (accepts both old and new):
{
  "description": "Red rising rebellion",
  "format": "commander",
  "offline": true,                  // deprecated
  "no_network": true                // NEW
}

// Response includes new sources:
{
  "commander": {...},
  "categories": {...},
  "sources": {
    "cards": "sample",
    "network": false,
    "llm": false
  }
}
```

### Error Responses
- **503 Service Unavailable**: `ScryfallUnavailable` exception
  - Clear message: "Scryfall API temporarily unavailable. Please try again in a moment."
  - Previously: 500 Internal Server Error

## Logging Examples

### No Network Block (INFO level)
```
INFO scryfall: Blocked network request to https://api.scryfall.com/cards/search (no_network=True)
INFO expand: Skipped Datamuse expansion for 'red' (no_network=True)
INFO theme: Skipped reference card fetch from https://moxfield.com/... (no_network=True)
```

### Retry Attempt (WARNING level)
```
WARNING scryfall: Scryfall 429 (attempt 1/3), retry after 1s: https://api.scryfall.com/cards/search
WARNING scryfall: Scryfall 429 (attempt 2/3), retry after 2s: https://api.scryfall.com/cards/search
```

## Key Implementation Details

### Single Enforcement Point
All network calls route through `_cached_get()` with `no_network` parameter:
- Scryfall card searches: Lines 315, 321, 331
- Set resolution: Line 360
- Commander resolution: Line 395
- Datamuse expansion: Line 165 (expand.py)
- Anthropic LLM: Line 175 (expand.py)
- Reference URL fetch: Line 245 (theme.py)

### Cache Always Works
- Disk cache persists across restarts
- Cache reads allowed even with `no_network=True`
- Cache key includes full URL + params
- 24-hour TTL with `CACHE_TTL = 86400`

### Graceful Degradation
1. Try card index (no network needed)
2. Try live API (with retries on 429/timeout)
3. Fall back to sample pool (60 bundled cards)

Result: Deck always builds, quality varies by source.

## Migration Guide

### For Existing Callers
- **No changes required** — `offline=True` still works
- **Optional**: Use `no_network=True` instead for clarity

### For API Clients
- **Recommended**: Check `response["sources"]["cards"]` to validate quality
- **Error handling**: Catch 503 in addition to 500

### For CLI Callers
```python
# Old (still works):
deck = build_deck("theme", offline=True)

# New (recommended):
deck = build_deck("theme", no_network=True)

# Check what was used:
print(deck["sources"])  # {"cards": "sample", "network": false, "llm": false}
```

## Files Modified

1. **deckbuilder/scryfall.py** (~320 lines changed)
   - Added `ScryfallUnavailable` exception
   - Rewrote `_cached_get()` with retry logic
   - Updated `ScryfallClient` with `no_network` support

2. **deckbuilder/expand.py** (~40 lines changed)
   - Added `no_network` parameter to expansion functions
   - Block Datamuse and LLM when `no_network=True`

3. **deckbuilder/theme.py** (~40 lines changed)
   - Added `no_network` parameter to theme interpretation
   - Block reference card fetching when `no_network=True`

4. **deckbuilder/engine.py** (~50 lines changed)
   - Added `no_network` parameter to `build_deck()`
   - Track `card_source` and return `sources` metadata

5. **app.py** (~30 lines changed)
   - Import `ScryfallUnavailable`
   - Accept `no_network`/`offline` parameters
   - Return 503 on `ScryfallUnavailable`
   - Include `sources` in response

6. **tests/test_network_layer.py** (NEW, ~350 lines)
   - 21 comprehensive test cases
   - 100% mock-based (no live API calls)
   - All test categories covered

## Verification Steps

### Unit Tests
```bash
pytest tests/test_network_layer.py -v
# Result: 21 passed
```

### Integration Tests  
```bash
pytest tests/ -v
# Result: 40 passed (19 existing + 21 new)
```

### Manual Testing
```python
from deckbuilder.engine import build_deck

# Should have zero network requests
deck = build_deck("Red aggro", no_network=True)
assert deck["sources"]["network"] is False
assert deck["sources"]["cards"] in ["index", "sample"]
print(deck["sources"])
# Output: {"cards": "sample", "network": false, "llm": false}
```

## Next Steps (Optional)

1. **UI Enhancement**: Display `sources.cards` to user
   - "Using bundled card pool" vs "Using live API" vs "Using local index"
   
2. **Monitoring**: Track which source is used most often
   - Helps prioritize card index sync vs live API

3. **Error Recovery**: Implement user-facing retry UI for 503s
   - "Scryfall temporarily unavailable. Retrying in 5 seconds..."

## Conclusion

The network layer is now production-ready with:
- ✓ Hard network isolation (`no_network=True`)
- ✓ Robust retry logic with Retry-After support
- ✓ Transparent sources tracking
- ✓ Full backward compatibility
- ✓ Comprehensive test coverage (21 new + 19 existing)
- ✓ Clear error handling (503 for availability issues)
- ✓ Graceful degradation (sample pool fallback)

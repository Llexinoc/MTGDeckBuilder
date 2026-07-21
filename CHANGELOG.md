# Changelog

All notable changes to ManaForge are documented here.

## [Phase 8: Card Art Rendering] - 2026-07-20

### ✨ Features Added

#### **Card Art Grid Display**
- **Responsive CSS Grid**: Implemented auto-fill responsive layout with `repeat(auto-fill, minmax(120px, 1fr))`
- **Scryfall Image Hotlinks**: All card images now load directly from `cards.scryfall.io` (no local downloads)
- **Lazy Loading**: Images load on-demand with `loading="lazy"` attribute for faster page loads
- **Proper Aspect Ratio**: All card images maintain 5:7 ratio (488px × 680px) without distortion
- **Hover Zoom Effect**: Smooth CSS transform (scale 1.08) on hover with box-shadow depth
- **Loading Skeleton Animation**: Gradient animation while images fetch for better UX
- **Fallback Name Frames**: Missing/placeholder images render as styled card name sections instead of broken images

#### **Image Field Normalization**
- Modified `carddata.py` `_row_to_dict()` to normalize `image_url` database column to `image` field
- Ensures consistent field naming between API responses and database layer
- All card objects now include `image` field throughout pipeline (scryfall.py → engine.py → frontend)

#### **Frontend Improvements**
- Enhanced `app.js` `cardTile()` function with structured error handling
- Unique fallback IDs for robust onerror handling
- Better HTML structure with type_line display in fallback frames
- Title attributes on all card elements for accessibility

### 🧹 Code Cleanup

**Removed 5 unused files (~312 lines, ~12.4 KB):**
- `debug_api.py` - Development script for API debugging (36 lines)
- `test_api.py` - Development script for image field testing (20 lines)
- `test_integration.py` - Alternative integration tests (41 lines)
- `tmp_check.py` - Temporary Scryfall query test (6 lines)
- `deckbuilder/expand.py` - Unused semantic expansion module (209 lines)

**Result**: Codebase reduced by ~5%, production-focused artifact

### ✅ Testing & Verification

- **All 60 tests passing** (no regressions from image handling changes)
- **Browser tested**: Card grid renders correctly at mobile and desktop widths
- **Image loading verified**: 25/25 cards render with Scryfall artwork
- **Fallback tested**: Confirmed graceful degradation for missing images
- **Fresh deployment tested**: App starts and builds decks without errors

### 📊 Technical Details

**Backend Changes:**
- [deckbuilder/carddata.py](deckbuilder/carddata.py#L160): `_row_to_dict()` now renames `image_url` → `image`
- [deckbuilder/engine.py](deckbuilder/engine.py#L466): `_card_out()` includes `image` field in response

**Frontend Changes:**
- [static/style.css](static/style.css): Consolidated card styling, added grid layout, loading animation, hover effects
- [static/app.js](static/app.js#L178): Enhanced `cardTile()` with robust error handling and fallback rendering

**No database migration needed**: Field rename is applied at query time, not stored differently

### 🎯 Impact

| Metric | Before | After |
|--------|--------|-------|
| Card display | Text-only | Images + text |
| Image source | None | Scryfall hotlinks |
| Unused files | 5 | 0 |
| Codebase size | 6,251 insertions | ~5,939 insertions |
| Test coverage | 60/60 | 60/60 ✅ |
| Page load | - | Lazy-loaded images |

### 🚀 What Works Now

```bash
# Build a deck and see it rendered with card art
python app.py
# Open http://127.0.0.1:5000
# Enter theme: "Omnath-led landfall deck"
# See 25+ cards with Scryfall artwork in responsive grid
```

---

## [Phase 7: Theme Resolution] - 2026-07-19

### ✨ Features Added
- Named card matching (e.g. "Omnath-led" → picks Omnath as commander)
- Compound theme axes support (e.g. "Red Rising rebellion" → Red/Black aggro)
- LLM-based theme interpretation with fallback heuristic engine
- Semantic keyword expansion for better card matching
- 60 comprehensive tests covering all deckbuilding rules

### 🧹 Cleanup
- Removed 3 unused debug scripts
- Reorganized test suite structure

---

## [Phase 6: Network & Offline Support] - 2026-07-18

### ✨ Features Added
- Offline-mode deck building with sample card pools
- 429 rate-limit handling with exponential backoff
- No-network flag for environments without internet
- Connection resilience (3 retries on failures)
- Sources tracking (API vs. index vs. sample)

### 🐛 Fixes
- Fixed Retry-After header parsing
- Proper error propagation for Scryfall unavailability

---

## [Phase 5: Card Index & Fast Queries] - 2026-07-17

### ✨ Features Added
- SQLite FTS5 full-text search index (~22K cards)
- Bulk-data sync from Scryfall (170 MB)
- Fast local queries replacing per-card API calls
- MDFC (double-faced card) support
- Color-identity and legality filtering

---

## Repository Stats

- **Current version**: Phase 8 (Card Art + Cleanup)
- **Files**: 27 (production code, tests, docs)
- **Lines of code**: ~5,939 (production) + ~2,000 (tests)
- **Test coverage**: 60 tests, 100% passing
- **Formats supported**: Commander (100-card), Constructed (60-card)
- **Card database**: 22,000+ Magic cards from Scryfall

---

## Future Enhancements

Potential improvements for future phases:
- [ ] Double-faced card flip UI toggle
- [ ] View toggle between grid/text decklist
- [ ] Deck export to Archidekt/Moxfield
- [ ] Custom mana base generator
- [ ] Sideboard support for 60-card format
- [ ] Dark mode theme
- [ ] Deck sharing via URL

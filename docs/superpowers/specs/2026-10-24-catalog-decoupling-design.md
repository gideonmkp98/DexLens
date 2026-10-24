# Catalog Decoupling & Instant Availability Design

- **Date**: 2026-10-24
- **Status**: Approved
- **Scope**: Phase 2 Architectural Correction (Zero-Import Catalog Browsing & Search)

---

## 1. Context & Motivation

The initial Phase 2 implementation required running an explicit CLI command (`python -m app.commands.import_cards`) to download and persist sets and cards into MariaDB before the catalog could be viewed or searched.

This revision eliminates that database dependency for public catalog browsing:
- The catalog must be usable immediately upon starting the application, with empty local `sets` and `cards` tables.
- All catalog metadata is fetched on demand from TCGdex and cached in memory.
- MariaDB tables (`sets`, `cards`, `import_runs`) and the CLI importer remain available for application-owned persistent features (e.g. user collections, scan history in future phases) without interfering with public browsing.

---

## 2. Architecture & Data Flow

```
[Browser]
   │
   ├─► (Images) ─────────────► [TCGdex Image CDN (assets.tcgdex.net)]
   │
   └─► (JSON API) ───────────► [Next.js Web Frontend]
                                     │
                                     ▼
                               [FastAPI Backend (/api/v1)]
                                     │
                                     ▼
                            [In-Memory Catalog Cache]
                                     │ (on cache miss / refresh)
                                     ▼
                              [TCGdex REST API]
```

### Key Principles:
1. **Frontend Isolation**: Next.js never calls TCGdex JSON endpoints directly. All JSON requests go through `/api/v1/*`.
2. **Database Decoupling**: Public catalog endpoints (`/api/v1/sets`, `/api/v1/sets/{id}`, `/api/v1/cards`, `/api/v1/cards/{id}`) do not query `sets` or `cards` tables in MariaDB.
3. **No Startup Full Prefetch**: The application does not download the 24,000+ card catalog on startup. Catalog data is fetched and cached lazily on demand.
4. **Digital-Only Exclusion**: *Pokémon TCG Pocket* and other digital-only products are excluded from set listings and search results.

---

## 3. Caching Strategy (`CatalogCache`)

Generalize the existing in-memory cache (`DetailCache`) into a unified `CatalogCache`:

- **Key Schema**: `(resource_type, source, language, identifier_or_query_hash)`:
  - `("sets", "tcgdex", "en", "all")`: Full list of physical sets (~150-200 items).
  - `("set", "tcgdex", "en", set_id)`: Set metadata + complete set card summaries.
  - `("card", "tcgdex", "en", card_id)`: Unified card detail.
  - `("search", "tcgdex", "en", query_string)`: Global card search results.
- **Cache Eviction & Bounds**:
  - Max entries: 1,000 entries (bounded LRU using `collections.OrderedDict`).
- **TTL & Resilience**:
  - Fresh TTL: 6 hours (`settings.DETAIL_CACHE_TTL_SECONDS`).
  - Stale Fallback: Up to 24 hours (`settings.DETAIL_CACHE_MAX_STALE_SECONDS`) if upstream TCGdex fails.
  - Failed Cooldown: 60 seconds on 404 or connection failures to prevent hammering TCGdex.
  - Request Deduplication: In-flight deduplication via `asyncio.Future` per key to ensure only one network request is made when concurrent requests ask for the same resource.

---

## 4. API Endpoints Contract

All catalog routes accept and return provider string IDs (`external_id`).

### 4.1. Sets Listing
`GET /api/v1/sets`
- Query parameters:
  - `page`: int (default `1`, $\ge 1$)
  - `page_size`: int (default `24`, $1 \le \text{page\_size} \le 100$)
  - `language`: str (default `"en"`)
- Logic:
  - Retrieve physical sets from cache/TCGdex.
  - Filter out digital sets (`is_digital_set`).
  - Paginate in FastAPI memory.
- Response Envelope:
  ```json
  {
    "items": [
      {
        "external_id": "base1",
        "name": "Base Set",
        "language": "en",
        "series": "Base",
        "logo_url": "https://assets.tcgdex.net/en/base/base1/logo",
        "symbol_url": "https://assets.tcgdex.net/en/base/base1/symbol",
        "release_date": "1999-01-09",
        "printed_total": 102,
        "total": 102,
        "card_count": 102
      }
    ],
    "total": 185,
    "page": 1,
    "page_size": 24,
    "has_more": true
  }
  ```

### 4.2. Set Details
`GET /api/v1/sets/{external_id}`
- Path parameter: `external_id: str`
- Query parameter: `language: str = "en"`
- Logic:
  - Fetch set from cache/TCGdex `sets/{external_id}`.
  - Return 404 if not found.
- Response: Set metadata including card count.

### 4.3. Cards Search & Listing
`GET /api/v1/cards`
- Query parameters:
  - `name`: str | None (case-insensitive substring)
  - `number`: str | None (exact local card number)
  - `set_id`: str | None (provider set ID, e.g. `base1`)
  - `language`: str = `"en"`
  - `page`: int = `1`
  - `page_size`: int = `24`
- Logic:
  - **Case A: `set_id` is provided**:
    - Fetch set details and its card list from cache/TCGdex `sets/{set_id}`.
    - Filter the set's cards in FastAPI memory by `name` and `number`.
    - Paginate in memory, returning exact `total` and `has_more`.
  - **Case B: `set_id` is NOT provided**:
    - Call TCGdex `/en/cards` with query params `name`, `localId`, `pagination:page`, and `pagination:itemsPerPage`.
    - Cache query results with query string key.
- Response:
  ```json
  {
    "items": [
      {
        "external_id": "base1-1",
        "set_id": "base1",
        "local_id": "1",
        "name": "Alakazam",
        "language": "en",
        "small_image_url": "https://assets.tcgdex.net/en/base/base1/1/low.webp",
        "large_image_url": "https://assets.tcgdex.net/en/base/base1/1/high.webp",
        "set_name": "Base Set"
      }
    ],
    "total": 102,
    "page": 1,
    "page_size": 24,
    "has_more": false
  }
  ```

### 4.4. Card Detail
`GET /api/v1/cards/{external_id}`
- Path parameter: `external_id: str`
- Query parameter: `language: str = "en"`
- Logic:
  - Fetch full card from cache/TCGdex `cards/{external_id}`.
  - Map allowlisted fields via `map_card_details`.
  - Return status (`"available"` | `"stale"`).
- Response:
  ```json
  {
    "external_id": "base1-1",
    "name": "Alakazam",
    "local_id": "1",
    "language": "en",
    "small_image_url": "https://assets.tcgdex.net/en/base/base1/1/low.webp",
    "large_image_url": "https://assets.tcgdex.net/en/base/base1/1/high.webp",
    "set": {
      "id": "base1",
      "name": "Base Set"
    },
    "status": "available",
    "category": "Pokemon",
    "illustrator": "Ken Sugimori",
    "rarity": "Rare Holo",
    "hp": 80,
    "types": ["Psychic"],
    "regulation_mark": null,
    "variants": {"normal": false, "reverse": false, "holo": true, "firstEdition": true},
    "attacks": [...],
    "abilities": [...]
  }
  ```

---

## 5. Frontend Alignment

1. **`apps/web/src/lib/api.ts`**:
   - Update `getSet(id: string)` and `getCard(id: string)` to take string IDs.
   - Update `getCards` to accept `set_id?: string`.
   - Update response interfaces to match external ID contracts.
2. **`apps/web/src/app/sets/page.tsx`**:
   - Link to `/sets/${set.external_id}`.
   - Update text to reflect that physical sets are browsable directly from the live catalog.
3. **`apps/web/src/app/sets/[id]/page.tsx`**:
   - Accept string `id` param.
   - Call `getSet(id)` and `getCards({ set_id: id })`.
4. **`apps/web/src/app/cards/page.tsx`**:
   - Link to `/cards/${card.external_id}`.
   - Set dropdown option values use `s.external_id`.
5. **`apps/web/src/app/cards/[id]/page.tsx`**:
   - Call single `getCard(id)` unified endpoint.
   - Show card attributes and graceful cached/stale indicator.

---

## 6. Testing Strategy

1. **Unit & Integration Tests in FastAPI**:
   - Mock TCGdex responses using `pytest-mock` or custom fake client.
   - Test `GET /api/v1/sets` with empty MariaDB database.
   - Test `GET /api/v1/sets/{id}` with valid and 404 set IDs.
   - Test `GET /api/v1/cards` filtering by `set_id`, `name`, `number`.
   - Test `GET /api/v1/cards/{id}` unified detail response.
   - Test cache behavior: hit, TTL expiry, stale fallback on 503, failed cooldown on 404.
2. **Frontend Typechecks & Build**:
   - `npm run typecheck`
   - `npm run lint`
   - `npm run build`

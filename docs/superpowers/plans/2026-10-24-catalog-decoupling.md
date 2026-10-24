# Catalog Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple Pokémon card catalog browsing and searching from local database imports so that sets and cards can be browsed and searched immediately upon starting the application, even when MariaDB catalog tables are empty.

**Architecture:** Next.js requests catalog JSON through FastAPI `/api/v1` routes; FastAPI queries an in-memory bounded LRU cache with 6h fresh TTL, 24h stale fallback, and 60s failed cooldown backed by TCGdex REST API; images load directly in the browser via TCGdex CDN; MariaDB remains decoupled for future application-owned data.

**Tech Stack:** FastAPI, Python 3.12, Pydantic v2, HTTPX, Next.js 15 (App Router), TypeScript, Tailwind CSS, Pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-24-catalog-decoupling-design.md`

## Global Constraints
- All catalog routes (`/sets`, `/sets/{external_id}`, `/cards`, `/cards/{external_id}`) must work with empty MariaDB tables.
- Public catalog routes must accept and return provider string IDs (`external_id`), not internal integer IDs.
- Digital-only sets (such as *Pokémon TCG Pocket*, series `tcgp`) must be filtered out of set listings and search results.
- No direct TCGdex JSON calls from the browser frontend.
- Do not download the full catalog into memory or disk on startup.
- Maintain existing tests, Ruff formatting, TypeScript strict mode, ESLint, and Next.js standalone build requirements.

## Review Focus
- Special characters in card/set identifiers (e.g. `base1-1`, `pop9-!`, `swsh3.5`): properly URL-encoded in paths and matched safely.
- Graceful degradation: when TCGdex is unreachable or returns 500, stale cached entries return HTTP 200 with `status="stale"`, while cache misses return HTTP 503 without crashing.
- Empty query responses: searching for non-existent names or numbers returns an empty list (`[]`) with `total=0` rather than 404.
- Out-of-bounds pagination: requesting page 999 returns empty `items` with `has_more=false`.
- Digital set exclusion: cards from `tcgp` or sets containing "pocket" do not appear in the catalog sets or card listings.

---

### Task 1: Generalize Cache Service (`CatalogCache`)

**Files:**
- Modify: `services/api/app/services/detail_cache.py`
- Test: `services/api/tests/test_detail_cache.py`

**Interfaces:**
- Produces: `catalog_cache = DetailCache()` (supporting arbitrary tuple keys `(resource, source, language, identifier)`), `DetailLookupResult(status, source, fetched_at, details)`.

- [ ] **Step 1: Write test for generalized cache keys and query caching**

```python
import pytest
from app.services.detail_cache import DetailCache

@pytest.mark.asyncio
async def test_cache_supports_sets_and_search_keys():
    cache = DetailCache(fresh_ttl_seconds=10)
    async def fetch_sets():
        return [{"id": "base1", "name": "Base Set"}]

    res1 = await cache.get_or_fetch(
        source="tcgdex",
        language="en",
        external_id="all",
        fetcher=fetch_sets,
        resource="sets",
    )
    assert res1.status == "available"
    assert res1.details == [{"id": "base1", "name": "Base Set"}]
```

- [ ] **Step 2: Run test to verify failure**

Run: `docker compose exec api pytest services/api/tests/test_detail_cache.py -k test_cache_supports_sets_and_search_keys -v`
Expected: FAIL (argument `resource` not accepted).

- [ ] **Step 3: Update `DetailCache` in `services/api/app/services/detail_cache.py`**

Support `resource: str = "card"` in key tuple: `(resource, source, language, external_id)`. Maintain backward compatibility.

- [ ] **Step 4: Run cache tests**

Run: `docker compose exec api pytest services/api/tests/test_detail_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/detail_cache.py services/api/tests/test_detail_cache.py
git commit -m "feat(api): generalize cache service for all catalog resources"
```

---

### Task 2: Update Schemas and TCGdex Client Methods

**Files:**
- Modify: `services/api/app/schemas/set.py`
- Modify: `services/api/app/schemas/card.py`
- Modify: `services/api/app/services/tcgdex.py`
- Test: `services/api/tests/test_tcgdex_client.py`

**Interfaces:**
- Produces:
  - `TcgdexClient.get_cards_search(params, language)`
  - Updated Pydantic schemas: `SetSummaryResponse` (`external_id`, `card_count`), `CardListItem` (`external_id`, `set_id: str`), `UnifiedCardDetailResponse`.

- [ ] **Step 1: Write tests for `get_cards_search` in `test_tcgdex_client.py`**

Test filtering by `name`, `localId`, `pagination:page`, and `pagination:itemsPerPage`.

- [ ] **Step 2: Run test to verify failure**

Run: `docker compose exec api pytest services/api/tests/test_tcgdex_client.py -k test_get_cards_search -v`
Expected: FAIL (`get_cards_search` not defined).

- [ ] **Step 3: Implement `get_cards_search` in `tcgdex.py` and update schemas in `set.py` & `card.py`**

Add `get_cards_search(name=None, local_id=None, page=1, page_size=24, language="en")`.
Ensure `SetSummaryResponse`, `SetDetailResponse`, `CardListItem`, and `CardDetailResponse` use string `external_id` and string `set_id`.

- [ ] **Step 4: Run test to verify passing**

Run: `docker compose exec api pytest services/api/tests/test_tcgdex_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/tcgdex.py services/api/app/schemas/ services/api/tests/test_tcgdex_client.py
git commit -m "feat(api): add tcgdex card search and update catalog schemas"
```

---

### Task 3: Revise Sets API Endpoints to Use Cache

**Files:**
- Modify: `services/api/app/api/v1/sets.py`
- Modify: `services/api/tests/test_sets_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/sets?page=1&page_size=24&language=en`
  - `GET /api/v1/sets/{external_id}?language=en`

- [ ] **Step 1: Write integration tests for sets endpoints with empty DB in `test_sets_api.py`**

Mock `TcgdexClient.get_sets` and `TcgdexClient.get_set` to assert that sets endpoints return data without any records in MariaDB `sets` table.

- [ ] **Step 2: Run test to verify failure**

Run: `docker compose exec api pytest services/api/tests/test_sets_api.py -v`
Expected: FAIL (currently queries MariaDB `Set` table).

- [ ] **Step 3: Update `services/api/app/api/v1/sets.py`**

- Fetch all sets via `catalog_cache` (`resource="sets"`).
- Filter out digital sets using `is_digital_set`.
- Paginate in memory for `GET /api/v1/sets`.
- Fetch set detail via `catalog_cache` (`resource="set"`) for `GET /api/v1/sets/{external_id}`.
- Remove `db: Session = Depends(get_db)` requirement for catalog queries.

- [ ] **Step 4: Run sets tests**

Run: `docker compose exec api pytest services/api/tests/test_sets_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/api/v1/sets.py services/api/tests/test_sets_api.py
git commit -m "feat(api): decouple sets endpoints from database"
```

---

### Task 4: Revise Cards API Endpoints to Use Cache

**Files:**
- Modify: `services/api/app/api/v1/cards.py`
- Modify: `services/api/tests/test_cards_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v1/cards?name=...&number=...&set_id=...&page=1&page_size=24`
  - `GET /api/v1/cards/{external_id}`

- [ ] **Step 1: Write integration tests for cards search and card detail with empty DB in `test_cards_api.py`**

Assert searching with `set_id` filters cached set card summaries; searching without `set_id` queries TCGdex card search; getting card detail returns unified metadata without querying MariaDB.

- [ ] **Step 2: Run test to verify failure**

Run: `docker compose exec api pytest services/api/tests/test_cards_api.py -v`
Expected: FAIL (currently queries MariaDB `Card` table).

- [ ] **Step 3: Update `services/api/app/api/v1/cards.py`**

- When `set_id` is supplied: load set from cache, filter its cards in memory by name and localId, paginate in memory.
- When `set_id` is not supplied: query `tcgdex_client.get_cards_search(...)` via cache.
- For `GET /api/v1/cards/{external_id}`: fetch card from `catalog_cache` (`resource="card"`), map allowlisted fields, return unified `CardDetailResponse`.
- Remove DB dependencies for card browsing.

- [ ] **Step 4: Run cards tests**

Run: `docker compose exec api pytest services/api/tests/test_cards_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/api/v1/cards.py services/api/tests/test_cards_api.py
git commit -m "feat(api): decouple cards endpoints from database"
```

---

### Task 5: Update Frontend API Client and Types

**Files:**
- Modify: `apps/web/src/lib/api.ts`

**Interfaces:**
- Produces: `getSets(params)`, `getSet(id: string)`, `getCards(params)`, `getCard(id: string)`.

- [ ] **Step 1: Update TypeScript interfaces and methods in `apps/web/src/lib/api.ts`**

Change `id` and `set_id` types to `string`. Update `CardDetail` to include unified attributes (attacks, abilities, hp, rarity, category, illustrator, etc.).

- [ ] **Step 2: Run TypeScript check**

Run: `npm.cmd --prefix apps/web run typecheck`
Expected: Type errors on pages using old signatures (confirming interface boundary).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): update api client interfaces for provider identifiers"
```

---

### Task 6: Update Frontend Catalog Pages

**Files:**
- Modify: `apps/web/src/app/sets/page.tsx`
- Modify: `apps/web/src/app/sets/[id]/page.tsx`
- Modify: `apps/web/src/app/cards/page.tsx`
- Modify: `apps/web/src/app/cards/[id]/page.tsx`

- [ ] **Step 1: Update `sets/page.tsx` and `sets/[id]/page.tsx`**

- Accept string ID params.
- Display sets from TCGdex.
- Links to `/sets/${set.external_id}`.
- Remove references to "locally imported cards".

- [ ] **Step 2: Update `cards/page.tsx`**

- Links to `/cards/${card.external_id}`.
- Dropdown passes string `external_id` for sets.

- [ ] **Step 3: Update `cards/[id]/page.tsx`**

- Read string `params.id`.
- Single fetch to `getCard(id)`.
- Render attributes with cached/stale badge if `status === "stale"`.

- [ ] **Step 4: Verify frontend build & typecheck**

Run:
```bash
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/
git commit -m "feat(web): update catalog pages for zero-import instant browsing"
```

---

### Task 7: Full Verification & Documentation

**Files:**
- Modify: `README.md`
- Run: Pytest, Ruff, ESLint, Prettier, Next.js build.

- [ ] **Step 1: Update `README.md`**

Explain that the card catalog is available immediately upon starting without manual imports, and explain the caching architecture.

- [ ] **Step 2: Run full verification suite**

```bash
docker compose exec api pytest
docker compose exec api ruff check .
docker compose exec api ruff format --check .
npm.cmd --prefix apps/web run typecheck
npm.cmd --prefix apps/web run lint
npm.cmd --prefix apps/web run format:check
npm.cmd --prefix apps/web run build
docker compose config --quiet
```
Expected: ALL PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document instant catalog browsing and cached architecture"
```

# Pokémon TCG Scanner — Phase 6: Personal Collection & Scan Library

A production-minded Pokémon TCG scanner and collection management web application. Building on Phase 5's optical recognition and catalog matching, Phase 6 delivers a persistent personal collection store: seamless conversion from confirmed card scans into inventory records, manual additions from the card catalog, condition and foil variant tracking, atomic quantity adjustments, duplicate trade binder analytics, optimistic concurrency control, and a rich, collector-oriented Dutch interface.

> [!NOTE]
> **Phase 6 Scope & Architectural Principles**:
> - **Catalog vs. Inventory Separation**: TCGdex remains the external catalog authority. The database stores only personal inventory records with immutable catalog snapshots (`card_name`, `set_id`, `set_name`, `collector_number`, `card_image_url`) so cards remain permanently viewable offline without cloning the full TCGdex catalog.
> - **Privacy & Provenance**: Expired or purged scans never delete or corrupt collection specimens (`ON DELETE SET NULL` foreign keys).
> - **Authentication & Market Pricing Out of Scope**: The app remains single-user/local-first with clean service boundaries ready for multi-tenancy in future phases. Financial portfolio valuations and live market pricing are strictly reserved for later phases.

---

## Architecture & Data Flow

```
1. Image Selection & Upload:
   User (Browser) ──> Select / Drag-and-Drop (JPEG, PNG, WebP)
                  ──> POST /api/v1/scans (multipart/form-data)
                  ──> Request size limit & normalization (Pillow, max 2500 px)
                  ──> Atomic store to /app/uploads/scans/<uuid>.jpg
                  ──> Persist scan record in MariaDB (scans table)
                  ──> Redirect to /scan/[id]

2. Automatic Card Detection & Interactive Crop (Phase 4):
   Next.js (Web)  ──> POST /api/v1/scans/{id}/detect (OpenCV edge & contour scoring)
   User (Browser) ──> Adjust corner handles & 90° rotation controls (CornerSelector)
                  ──> POST /api/v1/scans/{id}/crop (perspective warp to <uuid>_crop.jpg)
                  ──> POST /api/v1/scans/{id}/confirm (version concurrency check)
                  ──> Confirmed crop persisted; enables Phase 5 recognition

3. Local OCR Text Extraction & Normalization (Phase 5):
   User (Browser) ──> Click "Kaart herkennen"
                  ──> POST /api/v1/scans/{id}/recognize
                  ──> Threadpool worker: CLAHE preprocessing & ROI extraction
                      - Header ROI: Card name & suffix (ex, EX, VMAX, etc.)
                      - Footer ROI: Collector number (199/165, 058/102, TG01, SVP 001)
                      - Set code ROI & full-card fallback
                  ──> Tesseract OCR (5.5.0) execution bounded by process timeout & concurrency semaphore
                  ──> Structured normalization & false-positive rejection (HP, damage, copyright years)

4. Catalog Candidate Matching & Explainable Ranking (Phase 5):
   API Backend    ──> Query TCGdex for matching cards (by collector number & name tokens)
                  ──> Exclude digital products (TCG Pocket / tcgp)
                  ──> Rank candidates (0-100 score) with human-readable match reasons
                  ──> Atomically store recognition state & candidate list in MariaDB

5. User Review, Correction & Explicit Confirmation (Phase 5):
   User (Browser) ──> Inspect recognized fields and top candidate cards
                  ──> Optional: Edit name, number, or set code and click "Zoekopdracht bijwerken"
                  ──> Optional: Manual catalog search fallback if OCR missed fields
                  ──> Explicitly click "✓ Bevestig deze kaart" on chosen candidate
                  ──> POST /api/v1/scans/{id}/confirm-card (atomic version-checked SQL update)
                  ──> Side-by-side view: cropped user photo alongside official catalog image
                  ──> Persistent state preserved across browser reloads
                  ──> Optional: "Andere kaart kiezen" resets selection without losing confirmed crop

6. Personal Collection & Inventory Management (Phase 6):
   User (Browser) ──> Click "Voeg toe aan collectie" on confirmed scan or catalog card (/cards/[id])
                  ──> POST /api/v1/scans/{id}/collection (idempotent, derives snapshot from confirmed card)
                  ──> POST /api/v1/collection (manual catalog card addition with variant, condition, price)
                  ──> Persisted in MariaDB (collection_items table) with OCC versioning & loose scan FK
                  ──> View and manage inventory at /collection:
                      - Filter by expansion set, condition (NM/LP/MP/HP/DMG), variant (Holo/Reverse/etc.), language
                      - Instant search across card names, collector numbers, set names, notes
                      - Grid & compact list views with quantity badges and duplicate trade binder counts
                      - In-app modal for atomic quantity (+ / -) adjustments and optimistic-locked updates
                      - Safe delete flow with accessible confirmation modal
                      - Fast server-side statistics (/api/v1/collection/stats) without external API dependencies
```

---

## Phase 5 Scope & Exclusions

The October 27 recognition audit, measured results and remaining limitations are in
[Recognition quality](docs/recognition-quality-2026-10-27.md). Recognition now uses
printed set counts, corrected TCGdex set identifiers, multiple OCR readings and
bounded artwork comparison. New scans use the updated pipeline; use **OCR opnieuw
uitvoeren** to recompute an existing scan. Confirmation remains a user action.

### Included in Phase 5
- **Local OCR Engine**: Integrated Tesseract OCR 5.5.0 via Debian packages; 0 runtime model downloads; ~15 MB image overhead; ~80–120 ms ROI OCR speed on CPU; non-blocking threadpool execution; bounded concurrency and timeouts; overall request deadline tracking.
- **Evidence-Aware Preprocessing & Normalization**: CLAHE contrast enhancement; multi-ROI slicing (header, footer, bottom-left, bottom-right); strict slash validation (`_validate_slash_structure`) rejecting pure alphabetic noise (e.g. `thoes/ie`); retreat/modifier number suppression (`[\+x×\-@*]\s*\d{1,3}`); evidence strength classification (`strong`, `moderate`, `weak`, `none`); bounded name hypotheses generation (`generate_name_hypotheses`) recovering base names from noise (`Gastly se` -> `Gastly`, `ad Steelix eee 4` -> `Steelix`).
- **Image Quality & Low-Resolution Detection**: Automatic resolution assessment (`assess_crop_quality`) flagging crops under 400×550 px with actionable advice for sharper photos.
- **Catalog Matching & Evidence-Aware Ranking**: Decoupled TCGdex search by collector number and name hypotheses; bounded independent retrieval queries; weak number suppression avoiding catalog pool pollution; conflicting name penalties (-45 pts) preventing weak numbers from displacing credible name matches; digital-only card filtering; distinction between 0 matches and catalog provider outages.
- **Frontend Workflow**: Editable pre-filled search fields; raw OCR inspection toggle; confidence state banners (`high`, `medium`, `low`); image quality advisory banners; candidate cards with match reasons, conflict indicators (⚠️), and score badges; explicit card confirmation; side-by-side comparison; reload persistence; selection reset ("Andere kaart kiezen"); manual search fallback when OCR fails.
- **Data Integrity & Concurrency**: Migrations `0005` & `0006`; atomic crop invalidation on re-crop; conditional database updates checking `crop_version`, `search_version`, `card_selection_version`, `crop_status == 'confirmed'`, and non-expired status; full real MariaDB concurrency test suite.

### Excluded from Phase 5
- Automatic final confirmation without explicit user action.
- Guaranteed recognition of holographic foils or print variants (first edition, reverse holo).
- Live video stream scanning.
- Multi-card simultaneous detection in a single photo.
- Price estimation or condition grading.
- Paid external vision APIs.

---

## API Specification

### 1. Upload Scan
`POST /api/v1/scans` (multipart/form-data)

### 2. Get Scan Metadata
`GET /api/v1/scans/{id}`

Returns scan metadata including crop status, crop version, recognition status, candidate matches, and confirmed card details.

### 3. Detect Card Corners
`POST /api/v1/scans/{id}/detect`

Runs OpenCV edge detection and returns detected corners or fallback defaults.

### 4. Generate Crop Preview
`POST /api/v1/scans/{id}/crop`

Payload:
```json
{
  "corners": {
    "top_left": {"x": 0.15, "y": 0.12},
    "top_right": {"x": 0.85, "y": 0.12},
    "bottom_right": {"x": 0.85, "y": 0.88},
    "bottom_left": {"x": 0.15, "y": 0.88}
  },
  "rotation": 0,
  "expected_version": 0
}
```

### 5. Confirm Crop
`POST /api/v1/scans/{id}/confirm`

Payload: `{"crop_version": 1}`

### 6. Run Card Recognition (Phase 5)
`POST /api/v1/scans/{id}/recognize`

Executes local OCR on the confirmed crop, normalizes extracted text, queries TCGdex, and returns ranked candidate matches.

### 7. Search Candidates with Corrected Fields (Phase 5)
`POST /api/v1/scans/{id}/search-candidates`

Payload:
```json
{
  "name": "Pikachu",
  "number": "58",
  "set_code": "base1",
  "expected_crop_version": 2,
  "expected_search_version": 0
}
```

### 8. Explicitly Confirm Catalog Card (Phase 5)
`POST /api/v1/scans/{id}/confirm-card`

Payload:
```json
{
  "card_id": "base1-58",
  "expected_crop_version": 2,
  "expected_search_version": 0,
  "expected_selection_version": 0
}
```

### 9. Reset Card Confirmation (Phase 5)
`POST /api/v1/scans/{id}/reset-card-confirmation`

Payload:
```json
{
  "expected_crop_version": 2,
  "expected_selection_version": 0
}
```

### 10. List Collection (Phase 6)
`GET /api/v1/collection`

Query Parameters: `q`, `set_id`, `condition`, `language`, `variant`, `sort` (`recent`, `name_asc`, `name_desc`, `set_asc`, `number_asc`, `quantity_desc`), `page`, `page_size`.

Returns `CollectionListResponse` containing collection items with snapshots, quantities, conditions, and pagination metadata.

### 11. Manually Add to Collection (Phase 6)
`POST /api/v1/collection`

Payload:
```json
{
  "card_id": "base1-4",
  "variant": "holo",
  "condition": "mint",
  "quantity": 1,
  "purchase_price": "249.50",
  "currency": "EUR",
  "acquired_at": "2026-10-30",
  "notes": "Bought at card show, mint candidate"
}
```

### 12. Add Confirmed Scan to Collection (Phase 6)
`POST /api/v1/scans/{scan_id}/collection`

Converts a confirmed card scan into an inventory item. Idempotent: repeated calls safely return the existing record without duplicate creation. Rejects unconfirmed or expired scans.

Payload (optional overrides):
```json
{
  "variant": "normal",
  "condition": "near_mint",
  "quantity": 1
}
```

### 13. Get Collection Item (Phase 6)
`GET /api/v1/collection/{entry_id}`

Returns single collection item with full snapshots and provenance.

### 14. Update Collection Item (Phase 6)
`PATCH /api/v1/collection/{entry_id}`

Supports optimistic concurrency locking via `expected_version`. Increments `version` on change.

Payload:
```json
{
  "quantity": 2,
  "condition": "near_mint",
  "expected_version": 1
}
```

### 15. Delete Collection Item (Phase 6)
`DELETE /api/v1/collection/{entry_id}`

Safely removes a card entry from personal inventory. Returns HTTP 204 No Content.

### 16. Get Collection Statistics (Phase 6)
`GET /api/v1/collection/stats`

Fast server-side MariaDB analytics:
- `total_cards`: Physical count (sum of quantities)
- `unique_cards`: Distinct card entries
- `total_sets`: Number of represented sets
- `duplicate_count`: Excess trade binder copies
- `condition_distribution`: Breakdown by condition
- `set_distribution`: Top expansion sets in collection
- `recent_additions`: Recently added specimens

---

## Tech Stack

### Frontend (`apps/web`)
- **Next.js 14** (App Router, Standalone production build)
- **TypeScript** (Strict mode)
- **Tailwind CSS** (Custom collectible & elemental palette)
- **Centralized Typed API Client** (`src/lib/api.ts`)
- **ESLint** & **Prettier**

### Backend (`services/api`)
- **FastAPI** (`/api/v1` versioned REST routing)
- **Python 3.12**
- **TCGdex Python SDK** (`tcgdexsdk` official SDK for typed catalog queries & detail retrieval)
- **SQLAlchemy 2.0** & **Alembic**
- **PyMySQL** & **Cryptography**
- **Pydantic Settings v2**
- **HTTPX** (Async HTTP client with retry backoff)
- **OpenCV & Pillow** (Card boundary detection, perspective transform, CLAHE contrast enhancement)
- **Tesseract OCR 5.5.0** (Fast, local multi-ROI OCR extraction)
- **Ruff** (Linter & formatter)
- **Pytest** & **pytest-asyncio**

### Database & Infrastructure
- **MariaDB 11.4** (Containerized with healthchecks)
- **Docker** & **Docker Compose**

---

## Environment Setup

Copy `.env.example` to `.env` in the repository root:

```bash
cp .env.example .env
```

Key environment configuration variables:

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `production`) | `development` |
| `NEXT_PUBLIC_API_URL` | Base URL used by the frontend to reach FastAPI | `http://localhost:8000` |
| `API_PORT` | Host port exposed for FastAPI | `8000` |
| `WEB_PORT` | Host port exposed for Next.js | `3000` |
| `CORS_ORIGINS` | Allowed CORS origins for the API | `http://localhost:3000,http://127.0.0.1:3000` |
| `DATABASE_URL` | MariaDB SQLAlchemy connection string | `mysql+pymysql://tcg_user:tcg_password@db:3306/tcg` |
| `MARIADB_DATABASE` | MariaDB database name | `tcg` |
| `MARIADB_USER` | MariaDB application user | `tcg_user` |
| `MARIADB_PASSWORD` | MariaDB application password | `tcg_password` |
| `MARIADB_ROOT_PASSWORD` | MariaDB root password | `tcg_root_password` |
| `TCGDEX_BASE_URL` | Base REST endpoint for TCGdex API | `https://api.tcgdex.net/v2` |
| `TCGDEX_HTTP_TIMEOUT` | HTTP client timeout in seconds | `10.0` |
| `IMPORT_MAX_RETRIES` | Max retries for transient HTTP errors | `3` |
| `DETAIL_CACHE_TTL_SECONDS` | In-memory fresh cache TTL | `21600` (6h) |
| `DETAIL_CACHE_MAX_ENTRIES` | In-memory LRU max entries | `1000` |
| `DETAIL_CACHE_MAX_STALE_SECONDS` | Max stale age for fallback | `86400` (24h) |
| `DETAIL_CACHE_FAILED_COOLDOWN_SECONDS` | Cooldown after failed provider fetch | `60` |

---

## Running with Docker Compose

### Development Mode (Recommended)

Starts Next.js (with hot-reload and polling) and FastAPI with local volume mounts:

```bash
# Build and start services in development mode
docker compose -f docker-compose.dev.yml up -d

# Follow container logs
docker compose -f docker-compose.dev.yml logs -f

# Follow logs for a specific service (e.g. web or api)
docker compose -f docker-compose.dev.yml logs -f web
docker compose -f docker-compose.dev.yml logs -f api

# Stop development stack
docker compose -f docker-compose.dev.yml down
```

### Production Stack

Starts the optimized production container stack:

```bash
# Build and start all services
docker compose up --build -d

# Check running container status
docker compose ps

# Follow logs
docker compose logs -f

# Stop production stack
docker compose down
```

### Rebuilding Individual Services

When changing frontend or backend code without rebuilding the entire stack:

```bash
# Rebuild and restart only the web frontend
docker compose build web
docker compose up -d --no-deps web

# Rebuild and restart only the backend API
docker compose build api
docker compose up -d --no-deps api
```

---

## Database Migrations

Apply Alembic migrations to update MariaDB:

```bash
# Upgrade to latest migration revision
docker compose exec api alembic upgrade head

# Rollback one migration revision
docker compose exec api alembic downgrade -1

# Show current migration revision
docker compose exec api alembic current
```

The database schema includes:
- `0001`: Initial sets table.
- `0002`: Phase 2 catalog tables (`cards`, `import_runs`).
- `0003`: Phase 3 scans table (`scans` with indexed `expires_at`).
- `0004`: Phase 4 crop fields (`crop_status`, `corners`, `rotation`, `crop_path`, `crop_width`, `crop_height`, `crop_file_size`, `crop_version`, `confirmed_at`).
- `0005`: Phase 5 recognition & confirmed card fields (`recognition_status`, `recognition_id`, `ocr_crop_version`, `ocr_raw_text`, `recognized_name`, `recognized_number`, `recognized_set_code`, `ocr_confidence`, `search_version`, `candidate_matches`, `confirmed_card_id`, `confirmed_card_name`, `confirmed_card_set_name`, `confirmed_card_number`, `confirmed_card_image_url`, `card_confirmed_at`).
- `0006`: Phase 5 search persistence, catalog status & card selection versioning (`card_selection_version`, `catalog_status`, `catalog_error`, `user_search_name`, `user_search_number`, `user_search_set_code`, `user_search_provider_set_id`).
- `0007`: Persist structured OCR field confidence and source regions in the `recognition_evidence` JSON column.
- `0008`: Create `collection_items` table with card snapshots, quantity, condition, variant, pricing, notes, optimistic concurrency `version`, and `ON DELETE SET NULL` foreign key to `scans.id`.

---

## Importing the Card Index (Optional CLI Utility)

Populate MariaDB with card sets and card summaries for offline queries:

```bash
# Import a single set (e.g. Base Set - 102 cards)
docker compose exec api python -m app.commands.import_cards --set base1 --language en

# Import Jungle (base2 - 64 physical cards)
docker compose exec api python -m app.commands.import_cards --set base2 --language en

# Import all eligible physical sets (excludes digital-only TCG Pocket)
docker compose exec api python -m app.commands.import_cards --all --language en
```

---

## Frontend Web Routes

Access the web interface at `http://localhost:3000`:

- `/`: Home page with camera scan launcher, live stats, quick filter chips, and collection link.
- `/collection`: Personal collection library with set/condition/variant filtering, instant search, grid & list views, quantity tracking, edit dialog, safe delete modal, and stats overview.
- `/scan`: Mobile-first camera scanner viewfinder with aspect framing reticle and photo upload.
- `/scan/[id]`: Interactive card crop adjustment, live crop preview, OCR recognition, candidate matching, verified specimen slab, and "Voeg toe aan collectie" action.
- `/cards`: Card catalog visual browser with name, number, and expansion set filters.
- `/cards/[id]`: Detailed card specimen view with artwork, HP, attacks, abilities, variants, illustrator info, and "+ Voeg toe aan collectie" modal.
- `/cards/[id]`: Detailed card specimen view with artwork, HP, attacks, abilities, variants, and illustrator info.
- `/sets`: Complete expansion sets directory with set symbols, logos, and card counts.
- `/sets/[id]`: Set detail view showing set statistics and a paginated list of cards in that set.
- `/debug`: System telemetry and database connectivity status.

---

## Verification Suite

### Backend Tests & Linters

```bash
# Run full test suite in Docker against MariaDB (289 passed in ~90s)
docker compose exec api pytest

# Ruff code quality and format checks
docker compose exec api ruff check /app
docker compose exec api ruff format --check /app
```

### Frontend Typecheck, Lint, Format & Production Build

```bash
# Type check with TypeScript strict mode
npm.cmd --prefix apps/web run typecheck

# Run Next.js ESLint
npm.cmd --prefix apps/web run lint

# Check code formatting with Prettier
npm.cmd --prefix apps/web run format:check

# Verify Next.js production standalone build
npm.cmd --prefix apps/web run build
```

### Browser End-to-End Verification (Playwright on Isolated `_test` Stack)

```bash
# Start the dedicated E2E test stack on port 3001 connected strictly to MariaDB tcg_test
docker compose -f docker-compose.test.yml up -d

# Run automated end-to-end browser test suite (covering all 9 Phase 6 flows: upload, crop, recognize, confirm, duplicate grouping, idempotency, atomic edit, stale 409 rejection, reload persistence, manual catalog addition, safe deletion, existing upload workflow, and database safety guard verification)
npm.cmd --prefix apps/web run test:e2e
```

### Recognition Quality Benchmark

```bash
docker compose exec api python tests/evaluate_recognition_quality.py
```

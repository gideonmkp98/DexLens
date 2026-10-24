# Pokémon TCG Scanner — Phase 2: Searchable Card Catalog

A production-minded Pokémon TCG scanner web application. Phase 2 builds a searchable card catalog combining a minimal local index in MariaDB, on-demand enrichment via TCGdex, temporary in-memory caching, and direct CDN image rendering.

---

## Architecture & Data Flow

```
Index Import:
  TCGdex API  ──>  Python CLI Importer  ──>  MariaDB (Minimal Index)

Local Browsing & Search:
  Next.js (Web)  ──>  FastAPI (/api/v1)  ──>  MariaDB

On-Demand Detail Enrichment:
  Next.js (Web)  ──>  FastAPI (/api/v1/cards/{id}/details)  ──>  In-Memory LRU Cache  ──>  TCGdex API (fallback)

Images:
  Browser (Client)  ──>  TCGdex CDN (assets.tcgdex.net)
```

### Architectural Principles

1. **Minimal Local Index**: Only essential set and card identity fields required for local search and browsing are persisted in MariaDB. No heavy card stats, attacks, abilities, or full raw payloads are mirrored locally.
2. **On-Demand Remote Enrichment**: Additional card details (category, illustrator, rarity, HP, types, regulation mark, known variants, attacks, abilities) are fetched on-demand from TCGdex and cached temporarily in-memory.
3. **Graceful Degradation**: Local search and browsing never depend on TCGdex uptime. If TCGdex is slow or unreachable, local browsing remains 100% functional, and the detail endpoint gracefully returns `{ "status": "unavailable", "details": null }` with HTTP 200.
4. **Direct CDN Images**: Card images and set logos stream directly from TCGdex CDN (`assets.tcgdex.net`) into the browser with lazy loading and fallback states. No image datasets or image binaries are stored locally in Phase 2. (Machine learning scanner datasets belong to a separate later phase).
5. **Strict Field Ownership**:
   - **Stored Locally**: Set metadata (`id`, `source`, `external_id`, `name`, `language`, `series`, `logo_url`, `symbol_url`, `release_date`, `printed_total`, `total`), Card basic index (`id`, `source`, `external_id`, `set_id`, `local_id`, `name`, `language`, `image_base_url`), and Import audit records (`import_runs`).
   - **Fetched On-Demand**: Category, Illustrator, Rarity, HP, Types, Regulation mark, Variants, Attacks, Abilities.
   - **Explicitly Excluded**: Prices and secondary marketplace pricing.

---

## TCGdex Integration & Data Rules

- **TCGdex Base URL**: `https://api.tcgdex.net/v2`
- **TCGdex Documentation**:
  - Main Docs: [https://tcgdex.dev](https://tcgdex.dev)
  - REST Sets: [https://tcgdex.dev/rest/set](https://tcgdex.dev/rest/set)
  - REST Cards: [https://tcgdex.dev/rest/card](https://tcgdex.dev/rest/card)
  - Assets CDN: [https://tcgdex.dev/assets](https://tcgdex.dev/assets)

### Digital-Only Product Exclusion Rule

TCGdex catalogs both physical cards and digital-only apps (such as *Pokémon TCG Pocket*).
- **Identification Rule**: Any set belonging to series ID `tcgp`, series name `Pokémon TCG Pocket`, or with image paths containing `/tcgp/` is identified as digital-only.
- **Import Behavior**: Digital sets are explicitly excluded from the default physical catalog import. Attempting to import a digital-only set via `--set` reports an intentional exclusion failure and prevents inserting digital cards into MariaDB.

### Image URL Construction

Cards store a single provider `image_base_url` (e.g. `https://assets.tcgdex.net/en/base/base1/1`). The application derives:
- List image: `{image_base_url}/low.webp` (245x337 WebP)
- Detail image: `{image_base_url}/high.webp` (600x825 WebP)
- Fallback: Transparent `.png` or custom client-side placeholder if CDN fails.

---

## Tech Stack

### Frontend (`apps/web`)
- **Next.js 14** (App Router, Standalone build)
- **TypeScript** (Strict mode)
- **Tailwind CSS**
- **Centralized Typed API Client** (`src/lib/api.ts`)
- **ESLint** & **Prettier**

### Backend (`services/api`)
- **FastAPI** (`/api/v1` versioned routing)
- **Python 3.12**
- **SQLAlchemy 2.0** (Declarative Models & Relationships)
- **Alembic** (Database schema migrations)
- **PyMySQL** & **Cryptography**
- **Pydantic Settings v2**
- **HTTPX** (Async HTTP client with retry backoff)
- **Ruff** (Linter & formatter)
- **Pytest** & **pytest-asyncio**

### Database & Infrastructure
- **MariaDB 11.4** (Containerized with healthchecks)
- **Docker** & **Docker Compose**

---

## In-Memory Detail Cache

To comply with provider guidelines and minimize redundant network fetches:
- **Key Strategy**: Keyed by `(source, language, external_id)`.
- **Fresh TTL**: 6 hours (`DETAIL_CACHE_TTL_SECONDS=21600`).
- **Maximum Stale Age**: 24 hours (`DETAIL_CACHE_MAX_STALE_SECONDS=86400`). If a background refresh fails, previously cached data is served with `status="stale"`.
- **Capacity**: Bounded at 500 entries (`DETAIL_CACHE_MAX_ENTRIES=500`) using Least Recently Used (LRU) eviction.
- **Failure Cooldown**: 60 seconds (`DETAIL_CACHE_FAILED_COOLDOWN_SECONDS=60`) prevents repeated hammering when a remote resource returns 404 or network errors.
- **Request Deduplication**: In-flight concurrent requests for the exact same card share a single network call without a global blocking lock.
- **Process Boundary**: The cache is stored in-memory per FastAPI process and resets on application restart. Multiple independent API workers do not share cache state (deliberate Phase 2 design avoiding Redis).

---

## Environment Setup

Copy `.env.example` to `.env` in the repository root:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | Runtime environment (`development`, `production`) | `development` |
| `NEXT_PUBLIC_API_URL` | Base URL used by the frontend to reach FastAPI | `http://localhost:8000` |
| `API_PORT` | Host port exposed for FastAPI | `8000` |
| `WEB_PORT` | Host port exposed for Next.js | `3000` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `DATABASE_URL` | MariaDB SQLAlchemy connection string | `mysql+pymysql://tcg_user:tcg_password@db:3306/tcg` |
| `TCGDEX_BASE_URL` | Base REST endpoint for TCGdex API | `https://api.tcgdex.net/v2` |
| `TCGDEX_HTTP_TIMEOUT` | HTTP client timeout in seconds | `10.0` |
| `IMPORT_MAX_RETRIES` | Max retries for transient HTTP errors | `3` |
| `DETAIL_CACHE_TTL_SECONDS` | In-memory fresh cache TTL | `21600` (6h) |
| `DETAIL_CACHE_MAX_ENTRIES` | In-memory LRU max entries | `500` |
| `DETAIL_CACHE_MAX_STALE_SECONDS` | Max stale age for fallback | `86400` (24h) |
| `DETAIL_CACHE_FAILED_COOLDOWN_SECONDS` | Cooldown after failed provider fetch | `60` |

---

## Running with Docker Compose

### Development Mode (Recommended)

Starts Next.js and FastAPI with local volume mounts and hot-reloading enabled:

```bash
# Build and start services
docker compose -f docker-compose.dev.yml up -d

# View container logs
docker compose -f docker-compose.dev.yml logs -f
```

### Production Build

```bash
# Build and start optimized production stack
docker compose up --build -d

# Stop services
docker compose down
```

---

## Database Migrations (Alembic)

The API container runs `alembic upgrade head` on startup via `entrypoint.sh`.

Manual migration commands inside container:

```bash
# Apply migrations to head
docker compose exec api alembic upgrade head

# Rollback one revision
docker compose exec api alembic downgrade -1

# Show current migration revision
docker compose exec api alembic current
```

---

## Importing the Card Index

Use the Python CLI import tool inside the API container to populate sets and card summaries into MariaDB.

### Import a Single Set

```bash
# Import Jungle (base2 - 64 physical cards)
docker compose exec api python -m app.commands.import_cards --set base2 --language en

# Import Base Set (base1 - 102 physical cards)
docker compose exec api python -m app.commands.import_cards --set base1 --language en
```

### Import All Eligible Physical Sets

```bash
# Sequentially discovers and imports all physical card sets (excluding Pocket)
docker compose exec api python -m app.commands.import_cards --all --language en
```

### Idempotency & Audit Logging

- Repeating an import creates **zero duplicates**, preserves internal IDs, and increments `skipped_count`.
- Changed records are updated in-place and increment `updated_count`.
- Every import execution logs an `ImportRun` row recording `source`, `language`, `scope`, `started_at`, `finished_at`, `status` (`running`, `succeeded`, `partially_failed`, `failed`), card counters, and `error_summary`.

---

## API Endpoints

FastAPI provides versioned REST endpoints under `/api/v1`:

### Sets
- `GET /api/v1/sets`: Paginated list of imported sets with `local_card_count`.
  - Query params: `page` (default 1), `page_size` (1-100, default 24), `language` (default null).
- `GET /api/v1/sets/{id}`: Detailed metadata for a single set and its local card count.

### Cards
- `GET /api/v1/cards`: Search local cards index with deterministic ordering.
  - Query params: `name` (case-insensitive partial match), `number` (exact match against `local_id`), `set_id` (internal set ID), `language`, `page`, `page_size`.
  - Filters combine using **AND** semantics.
  - Never calls external APIs.
- `GET /api/v1/cards/{id}`: Basic local card metadata, basic set info, and derived image URLs.
  - Never calls external APIs.
- `GET /api/v1/cards/{id}/details`: On-demand remote card details enrichment.
  - Checks in-memory LRU cache first.
  - Fetches from TCGdex if missing or expired.
  - Returns allowlisted fields (`category`, `illustrator`, `rarity`, `hp`, `types`, `regulationMark`, `variants`, `attacks`, `abilities`).
  - Response contract:
    ```json
    {
      "status": "available",
      "source": "tcgdex",
      "fetched_at": "2026-10-24T21:34:44.079821Z",
      "details": {
        "category": "Pokemon",
        "illustrator": "Ken Sugimori",
        "rarity": "Common",
        "hp": 50,
        "types": ["Lightning"],
        "variants": { "holo": false, "normal": true },
        "attacks": [...]
      }
    }
    ```

### Health
- `GET /api/v1/health`: Checks API and MariaDB connectivity (HTTP 200 OK / HTTP 503 Degraded).

---

## Frontend Web Routes

Access the web interface at `http://localhost:3000`:

- `/cards`: Card catalog search with name, card number, and set filter inputs, responsive card grid, and URL-synchronized pagination.
- `/cards/[id]`: Card detail view loading basic local data instantly, followed by independent on-demand enrichment, variant pills, attacks/abilities breakdown, and graceful degradation when offline.
- `/sets`: Overview of all imported card sets with logos, release dates, and indexed card counts.
- `/sets/[id]`: Set detail view showing set statistics and a paginated list of cards in that set.
- `/`: System foundation and real-time API & Database health monitor.

---

## Code Quality & Testing

### Backend Testing & Linting

Automated tests run against an isolated test database (`tcg_test` in MariaDB or SQLite in-memory fallback), protecting development data from modification:

```bash
# Run full pytest test suite (32 tests covering imports, cache, APIs, health)
docker compose exec api pytest

# Run Ruff linter
docker compose exec api ruff check .

# Check code formatting with Ruff
docker compose exec api ruff format --check .
```

### Frontend Linting & Type Checking

```bash
# Type check with TypeScript compiler
npm.cmd --prefix apps/web run typecheck

# Run Next.js ESLint
npm.cmd --prefix apps/web run lint

# Check formatting with Prettier
npm.cmd --prefix apps/web run format:check
```

---

## Future Roadmap (Phase 3 Preview)

Phase 2 establishes the complete catalog and search infrastructure. Future phases will incorporate:
- Camera input and image capture via web/mobile interfaces.
- Image preprocessing and computer vision recognition (OpenCV / perceptual hashing / embeddings).
- Scanner ML training dataset generation (downloading card images locally in a dedicated offline pipeline).
- User collections, binder management, and scan history.

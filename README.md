# Pokémon TCG Scanner — Phase 2: Searchable Card Catalog

A production-minded Pokémon TCG scanner web application. Phase 2 delivers a searchable, browsable card catalog that works **out-of-the-box without requiring an initial database import**, combining an in-memory bounded LRU cache with stale fallback, on-demand retrieval from TCGdex, direct CDN image rendering, and decoupled MariaDB persistence for future application features.

---

## Architecture & Data Flow

```
Live Catalog Browsing & Search:
  Next.js (Web)  ──>  FastAPI (/api/v1)  ──>  In-Memory Catalog Cache  ──>  TCGdex API (on miss / refresh)

Card Details:
  Next.js (Web)  ──>  FastAPI (/api/v1/cards/{external_id})  ──>  In-Memory Catalog Cache  ──>  TCGdex API

Images:
  Browser (Client)  ──>  TCGdex Image CDN (assets.tcgdex.net)

Application Persistence (Optional / Future Phases):
  CLI Importer / Scans / Collections  ──>  MariaDB
```

### Architectural Principles

1. **Instant Availability (Zero Initial Import)**: The application is immediately usable upon startup. Users can browse physical Pokémon sets, search for cards, open set card lists, and view full card details when the local database `sets` and `cards` tables are completely empty.
2. **Decoupled Catalog Layer**: Public catalog routes (`/api/v1/sets`, `/api/v1/sets/{id}`, `/api/v1/cards`, `/api/v1/cards/{id}`) query an in-memory bounded cache backed by TCGdex. MariaDB remains dedicated to application-owned persistent data (e.g. user collections, scan history in future phases).
3. **Provider String Identifiers**: All catalog routes and URLs use provider string identifiers (`external_id`), such as `/sets/base1` and `/cards/base1-1`.
4. **On-Demand Caching with Stale Fallback**:
   - Multi-resource caching for sets lists, set card summaries, search queries, and single card details.
   - Bounded LRU capacity (1,000 entries) with 6-hour fresh TTL and up to 24-hour stale fallback if upstream TCGdex degrades.
   - 60-second failed lookup cooldown to avoid hammering the upstream provider on missing cards or connection drops.
   - In-flight request deduplication prevents concurrent identical fetches.
5. **Direct CDN Images**: Card images and set logos stream directly from TCGdex CDN (`assets.tcgdex.net`) into the browser with lazy loading and fallback states. No image datasets or image binaries are stored locally in Phase 2.
6. **Digital-Only Product Exclusion**: Digital-only products (such as *Pokémon TCG Pocket*, series ID `tcgp`) are automatically identified and excluded from physical set listings and card searches.
7. **Strict Field Ownership**:
   - **Catalog Details**: Category, Illustrator, Rarity, HP, Types, Regulation mark, Variants, Attacks, Abilities.
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
- **Identification Rule**: Any set or card belonging to series ID `tcgp`, series name `Pokémon TCG Pocket`, or with image/logo paths containing `/tcgp/` is identified as digital-only.
- **Catalog Behavior**: Digital sets and cards are filtered out from set listings, search results, and direct detail endpoints (returning HTTP 404 if directly requested).

### Image URL Construction

Cards reference images directly from the CDN:
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
- **SQLAlchemy 2.0** & **Alembic**
- **PyMySQL** & **Cryptography**
- **Pydantic Settings v2**
- **HTTPX** (Async HTTP client with retry backoff)
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
| `DETAIL_CACHE_MAX_ENTRIES` | In-memory LRU max entries | `1000` |
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

## API Endpoints

FastAPI provides versioned REST endpoints under `/api/v1`:

### Sets
- `GET /api/v1/sets`: Paginated physical sets list served from cache.
  - Query params: `page` (default 1), `page_size` (1-100, default 24), `language` (default "en").
  - Digital sets (*Pocket*) are filtered out automatically.
- `GET /api/v1/sets/{external_id}`: Metadata and card count for a specific set (e.g. `base1`).

### Cards
- `GET /api/v1/cards`: Search and list cards.
  - Query params:
    - `set_id`: String provider set ID (e.g. `base1`). When provided, filters the set's card summaries in memory.
    - `name`: Case-insensitive partial name search.
    - `number`: Exact match against local card number.
    - `language`: Card language code (default "en").
    - `page`, `page_size`: Pagination bounds.
  - Excludes digital-only cards.
- `GET /api/v1/cards/{external_id}`: Unified single card detail response.
  - Path param: `external_id` (e.g. `base1-1`).
  - Returns metadata, set relation, and allowlisted gameplay attributes (`category`, `illustrator`, `rarity`, `hp`, `types`, `attacks`, `abilities`, `variants`).
  - Includes cache freshness status (`"available"` or `"stale"`).
  - Returns 404 for unknown cards or digital sets; returns 503 if upstream is unavailable without cache.

### Health
- `GET /api/v1/health`: Checks API and MariaDB connectivity (HTTP 200 OK / HTTP 503 Degraded).

---

## Frontend Web Routes

Access the web interface at `http://localhost:3000`:

- `/cards`: Card catalog search with name, card number, and set filter dropdown, responsive card grid, and URL-synchronized pagination.
- `/cards/[id]`: Card detail view displaying card art, set badge, stats, variants, attacks, and abilities with cache indicator and fallback handling.
- `/sets`: Overview of all physical Pokémon card sets with logos, series, release dates, and card counts.
- `/sets/[id]`: Set detail view showing set statistics and a paginated list of cards in that set.
- `/`: System foundation and real-time API & Database health monitor.

---

## Code Quality & Verification Suite

### Backend Testing & Linting

```bash
# Run full pytest test suite (55 tests covering sets, cards, cache, tcgdex client, import, health)
docker compose exec api pytest

# Run Ruff linter
docker compose exec api ruff check .

# Check code formatting with Ruff
docker compose exec api ruff format --check .
```

### Frontend Linting, Type Checking & Build

```bash
# Type check with TypeScript compiler
npm.cmd --prefix apps/web run typecheck

# Run Next.js ESLint
npm.cmd --prefix apps/web run lint

# Check formatting with Prettier
npm.cmd --prefix apps/web run format:check

# Verify Next.js production build
npm.cmd --prefix apps/web run build
```

---

## Optional Database Import Tool (Persistent Features)

MariaDB tables (`sets`, `cards`, `import_runs`) and the CLI importer remain available as an optional utility for persistent indexing:

```bash
# Import Jungle (base2 - 64 physical cards)
docker compose exec api python -m app.commands.import_cards --set base2 --language en

# Import all physical sets
docker compose exec api python -m app.commands.import_cards --all --language en
```

---

## Future Roadmap (Phase 3 Preview)

Phase 2 establishes the complete catalog and search infrastructure. Future phases will incorporate:
- Camera input and image capture via web/mobile interfaces.
- Image preprocessing and computer vision recognition (OpenCV / perceptual hashing / embeddings).
- Scanner ML training dataset generation.
- User collections, binder management, and scan history.

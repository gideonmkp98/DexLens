# Phase 6: Personal Collection & Scan Library — Readiness & Delivery Report

Date: October 30, 2026
Status: PRODUCTION-READY (HARDENED, ISOLATED & CHECKPOINTED)

---

## 1. Executive Summary

Phase 6 introduces a persistent, atomic personal Pokémon card collection and inventory management system to the Pokémon TCG Scanner application. Built on top of Phase 5's optical card recognition and verified specimen slabs, Phase 6 enables users to:
1. Seamlessly convert confirmed card scans into permanent inventory specimens with a single click.
2. Group duplicate physical scans of the same card into a single collection item with atomic quantity increments ($\times2$, $\times3$).
3. Maintain idempotency: repeating the same physical scan never creates additional duplicates or increments (HTTP 200).
4. Perform atomic quantity adjustments and metadata updates with database-enforced optimistic concurrency control (`expected_version`).
5. Manually add catalog cards with fine-grained condition grading, print variants, purchase prices, currency, acquisition dates, and collector notes.
6. Browse, filter, sort, and paginate through personal collections with high-performance local MariaDB queries.
7. Remove cards safely with accessible application dialogs (zero browser `alert()` or `confirm()`).
8. Inspect accurate server-side analytics (total cards = `SUM(quantity)`, unique cards = `COUNT(*)`, represented sets, duplicate counts, physical card condition distributions, and set distributions) calculated in fast MariaDB aggregations.

The implementation is verified across:
- **Pytest**: 289 passed, 0 failed in MariaDB container (including 13 dedicated concurrency tests)
- **Playwright End-to-End**: 4 passed, 0 failed covering all 9 required flows with a dedicated `_test` stack (`docker-compose.test.yml` on port 3001) and preflight safety guard refusing execution on non-test databases
- **TypeScript**: Strict typecheck clean (`tsc --noEmit`)
- **ESLint**: Clean pass (`next lint`)
- **Prettier**: Clean pass (`prettier --check .`)
- **Next.js Standalone Production Build**: Succeeded with `sharp` native image optimization
- **Security & Vulnerability Audit**: Upgraded to Next.js `15.5.28` (LTS backport with React 18 compatibility) and PostCSS `8.5.32`, achieving **0 vulnerabilities** on `npm audit --omit=dev` and full npm audit
- **Docker Compose**: Production, development, and isolated test stack configurations valid, container health checks passing, and restart resilience verified.

---

## 2. Sub-Agent Work Breakdown

The work was coordinated across multiple specialized sub-agents with strict boundaries:

### Category 1: Security & Dependency Review
- **Deliverables**:
  - Upgraded Next.js from `14.2.15` to `15.5.28` (LTS backport with full React 18 support).
  - Maintained PostCSS override `"postcss": "^8.5.32"` to eliminate all PostCSS CVEs.
  - Resolved all critical and high vulnerabilities without breaking Next.js App Router code or introducing experimental preview frameworks.
  - Result: `found 0 vulnerabilities` on both `npm audit --omit=dev` and full audit.

### Category 2: Database & Concurrency Hardening
- **Deliverables**:
  - Replaced read-check-mutate in `CollectionService.update_item` with database-atomic conditional update:
    `UPDATE collection_items SET ..., version = version + 1 WHERE id = :id AND version = :expected_version`.
  - Distinguishes rowcount 0 as HTTP 404 (item not found) or HTTP 409 (`VERSION_CONFLICT`).
  - Required `expected_version: int = Field(ge=1)` in `CollectionUpdateRequest` (no silent default).
  - Added unique constraint `uq_collection_items_grouping` on `("provider", "card_id", "language", "variant", "condition")` via migration `0010`.
  - Implemented concurrent insert race and deadlock handling in `CollectionService.create_item` and `add_from_scan` (catches `(IntegrityError, OperationalError)`, rolls back, finds winner, atomically merges quantity/version, links scan, prevents HTTP 500).

### Category 3: Collection Statistics Semantics
- **Deliverables**:
  - `total_cards`: `SUM(quantity)`
  - `unique_cards`: `COUNT(*)` (distinct grouped items)
  - `duplicate_count`: `total_cards - unique_cards`
  - `condition_distribution`: uses physical card count `SUM(quantity)` grouped by condition
  - `set_distribution`: includes both unique card count (`COUNT(*)`) and total cards (`SUM(quantity)`)
  - `recent_additions`: orders by `updated_at DESC, created_at DESC LIMIT 5`.

### Category 4: Dedicated `_test` Stack & Isolated E2E Testing
- **Deliverables**:
  - Created dedicated isolated E2E test stack in `docker-compose.test.yml`:
    - `api-test` running on port 8001 connected strictly to MariaDB `tcg_test`.
    - `web-test` running on port 3001 proxying to `http://api-test:8000`.
  - Hard preflight safety guard in `apps/web/e2e/collection-flow.spec.ts` (`test.beforeAll`): queries `GET /api/v1/testing/db-info` and immediately throws an error if `is_test_database` is False. Prevents any accidental execution against or card deletions from real development databases (`tcg`).
  - Implemented `POST /api/v1/testing/reset`: verifies database name ends in `_test`, creates all missing tables (`Base.metadata.create_all`), disables foreign keys, truncates test data, and re-enables foreign keys. Returns HTTP 403 Forbidden on non-test databases.
  - Expanded `apps/web/e2e/collection-flow.spec.ts` covering all 9 required flows against `http://localhost:3001`:
    1. Upload -> detect -> crop -> OCR -> candidate confirmation -> add to collection
    2. Second independent scan of same card -> same collection tile with quantity increment ($\times2$)
    3. Repeating same scan -> no additional increment (idempotent HTTP 200)
    4. Edit quantity using expected version
    5. Stale concurrent edit -> HTTP 409 `VERSION_CONFLICT`
    6. Reload -> persistence remains correct ($\times3$)
    7. Manual catalog addition with variant & condition
    8. Safe deletion with accessible alertdialog
    9. Existing upload workflow remains functional
  - Tested safety guard refusal: verified that pointing tests at `http://localhost:3000` (`tcg`) aborts execution immediately with `[CRITICAL SAFETY GUARD VIOLATION]`.

### Category 5: Agent Process & Memory Improvement
- **Deliverables**:
  - Created reusable audit skill `.agents/skills/phase-readiness-audit/SKILL.md` defining the 15-step phase-readiness checklist.
  - Created `docs/agent-playbook.md` capturing Windows host tooling rules (`npm.cmd`, `npx.cmd`, `-LiteralPath`), no polling loops, dedicated `_test` stack orchestration, and migration continuity.

---

## 3. Data Architecture & Schema Details

### MariaDB `collection_items` Table Schema (`0010_enforce_collection_grouping_unique.py`)

```sql
CREATE TABLE `collection_items` (
  `id` varchar(36) NOT NULL,
  `card_id` varchar(100) NOT NULL,
  `provider` varchar(32) NOT NULL DEFAULT 'tcgdex',
  `card_name` varchar(255) NOT NULL,
  `set_id` varchar(50) NOT NULL,
  `set_name` varchar(255) NOT NULL,
  `collector_number` varchar(50) NOT NULL,
  `card_image_url` varchar(512) DEFAULT NULL,
  `quantity` int(11) NOT NULL DEFAULT 1,
  `language` varchar(10) NOT NULL DEFAULT 'en',
  `variant` varchar(32) NOT NULL DEFAULT 'normal',
  `condition` varchar(32) NOT NULL DEFAULT 'near_mint',
  `notes` text DEFAULT NULL,
  `purchase_price` decimal(10,2) DEFAULT NULL,
  `currency` varchar(3) DEFAULT NULL,
  `acquired_at` date DEFAULT NULL,
  `source_scan_id` varchar(36) DEFAULT NULL,
  `version` int(11) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_collection_items_grouping` (`provider`,`card_id`,`language`,`variant`,`condition`),
  KEY `ix_collection_items_card_id` (`card_id`),
  KEY `ix_collection_items_card_name` (`card_name`),
  KEY `ix_collection_items_set_id` (`set_id`),
  KEY `ix_collection_items_language` (`language`),
  KEY `ix_collection_items_variant` (`variant`),
  KEY `ix_collection_items_condition` (`condition`),
  KEY `ix_collection_items_source_scan_id` (`source_scan_id`),
  KEY `ix_collection_items_created_at` (`created_at`),
  KEY `ix_collection_items_set_collector` (`set_id`,`collector_number`),
  KEY `ix_collection_items_card_variant_lang` (`card_id`,`variant`,`language`),
  CONSTRAINT `fk_collection_items_source_scan_id_scans` FOREIGN KEY (`source_scan_id`) REFERENCES `scans` (`id`) ON DELETE SET NULL,
  CONSTRAINT `ck_collection_items_quantity_positive` CHECK (`quantity` >= 1),
  CONSTRAINT `ck_collection_items_purchase_price_non_negative` CHECK (`purchase_price` is null or `purchase_price` >= 0),
  CONSTRAINT `ck_collection_items_version_positive` CHECK (`version` >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;
```

---

## 4. Verification Results Summary

| Verification Gate | Command | Result | Status |
|---|---|---|---|
| Gate 1: Security Audit | `npm.cmd --prefix apps/web audit --omit=dev` | **0 vulnerabilities** | PASS |
| Gate 2: Frontend Typecheck | `npm.cmd --prefix apps/web run typecheck` | Clean (0 errors) | PASS |
| Gate 3: Frontend Lint | `npm.cmd --prefix apps/web run lint` | Clean (0 warnings or errors) | PASS |
| Gate 4: Frontend Prettier | `npm.cmd --prefix apps/web run format:check` | Clean (All files pass) | PASS |
| Gate 5: Backend Ruff Lint | `docker compose exec api ruff check .` | Clean (All checks passed) | PASS |
| Gate 6: Backend Ruff Format | `docker compose exec api ruff format --check .` | Clean (89 files formatted) | PASS |
| Gate 7: Database Migration Head | `docker compose exec api alembic current` / `heads` | Head is `0010 (head)` | PASS |
| Gate 8: Bidirectional Migration | `alembic downgrade -1` & `upgrade head` | Clean idempotent rollback & upgrade | PASS |
| Gate 9: Full Backend Pytest | `docker compose exec api pytest` | **289 passed, 0 failed** in ~93s | PASS |
| Gate 10: MariaDB Concurrency Tests | `pytest tests/test_concurrency_mariadb.py` | **13 passed, 0 failed** in 11.43s | PASS |
| Gate 11: Playwright E2E Isolated 9 Flows | `npm.cmd --prefix apps/web run test:e2e` against `http://localhost:3001` (`tcg_test`) | **4 suites (9 flows) passed, 0 failed in 19.9s** | PASS |
| Gate 12: E2E Non-Test DB Safety Rejection | Run against `http://localhost:3000` (`tcg`) | **Safety guard immediately aborts with 403 / violation** | PASS |
| Gate 13: Next.js Standalone Build | `npm.cmd --prefix apps/web run build` | Succeeded, standalone output generated | PASS |
| Gate 14: Sharp Native Loader | Native image test in standalone runtime | `sharp@0.35.5` loads cleanly | PASS |
| Gate 15: Docker Stack Validation | `docker compose` dev, prod, and test | All 3 configurations valid and healthy | PASS |
| Gate 16: Clean Working Tree | `git diff --check` | Clean (0 trailing whitespace issues) | PASS |

---

## 5. Phase 6 Readiness Verdict

- **Phase 5 Readiness:** VERIFIED (All Phase 5 regression tests, crop aspect ratios, line endings, dev volumes, and scan flows pass).
- **Phase 6 Readiness:** VERIFIED (All release blockers resolved, atomic concurrency enforced, unique grouping constraint live, stats semantics accurate, 0 vulnerabilities, dedicated `_test` E2E stack active and verified, full E2E 9-flow test suite passed with hard safety guards).
- **Safe to Begin Phase 7:** **YES — GO FOR PHASE 7**.

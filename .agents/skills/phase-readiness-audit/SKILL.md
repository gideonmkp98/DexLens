---
name: phase-readiness-audit
description: Comprehensive 15-step phase-readiness audit protocol for Pokémon TCG Scanner, verifying dependencies, migrations, test coverage, concurrency, standalone builds, and Docker stability.
---

# Phase Readiness Audit Protocol

This skill enforces a comprehensive, repeatable verification process before closing any phase or transitioning to a subsequent phase (such as Phase 7).

## Audit Scope & Principles
1. **Evidence Before Assertions:** Never declare a gate passed based on expectations or assumptions. Always execute the verification command and inspect output.
2. **Strict Environment Parity:** Verify both host tooling (Windows PowerShell) and container environments (Linux Debian/Alpine).
3. **Zero Security Regressions:** Production dependencies must report zero critical or high vulnerabilities.
4. **Data & Schema Integrity:** Alembic migrations must be linear, single-headed, reversible, and matched with SQLAlchemy models.

---

## 15-Step Verification Checklist

### Gate 1: Security & Dependency Audit
- [ ] Run `npm.cmd --prefix apps/web audit --omit=dev`
  - Result must report 0 vulnerabilities (critical/high).
- [ ] Check container image base pins and pip dependencies.

### Gate 2: Static Typing (Frontend)
- [ ] Run `npm.cmd --prefix apps/web run typecheck`
  - TypeScript strict checking must exit with code 0.

### Gate 3: Frontend Linting
- [ ] Run `npm.cmd --prefix apps/web run lint`
  - Zero warnings or errors.

### Gate 4: Code Formatting (Frontend)
- [ ] Run `npm.cmd --prefix apps/web run format:check`
  - All files in `apps/web` must adhere to Prettier styling.

### Gate 5: Backend Linting
- [ ] Run `docker compose -f docker-compose.dev.yml exec api ruff check .`
  - Zero Ruff lint violations.

### Gate 6: Backend Formatting
- [ ] Run `docker compose -f docker-compose.dev.yml exec api ruff format --check .`
  - All Python files formatted.

### Gate 7: Database Migration Synchronization
- [ ] Run `docker compose -f docker-compose.dev.yml exec api alembic current`
- [ ] Run `docker compose -f docker-compose.dev.yml exec api alembic heads`
  - Both commands must display identical current head revisions without branches.

### Gate 8: Database Bidirectional Migration Resilience
- [ ] Run `docker compose -f docker-compose.dev.yml exec api alembic downgrade -1`
- [ ] Run `docker compose -f docker-compose.dev.yml exec api alembic upgrade head`
  - Downgrade and upgrade must execute idempotently without data corruption.

### Gate 9: Comprehensive Backend Test Suite
- [ ] Run `docker compose -f docker-compose.dev.yml exec api pytest`
  - Full suite must pass (baseline: >= 285 tests).

### Gate 10: Real MariaDB Concurrency Testing
- [ ] Run `docker compose -f docker-compose.dev.yml exec api pytest tests/test_concurrency_mariadb.py -vv`
  - Concurrency tests (optimistic locking conflicts, duplicate grouping merges, identical scan idempotency) must pass against real MariaDB InnoDB engine.

### Gate 11: End-to-End Browser Flow Coverage (Playwright)
- [ ] Run `npm.cmd --prefix apps/web run test:e2e`
  - Must cover 9 mandatory flows:
    1. Upload -> detect -> crop -> OCR -> candidate confirmation -> add to collection
    2. Second independent scan of same card -> same collection tile with quantity increment (x2)
    3. Repeating same scan -> no additional increment
    4. Edit quantity using expected version
    5. Stale concurrent edit -> HTTP 409
    6. Reload -> persistence remains correct
    7. Manual catalog addition
    8. Safe deletion
    9. Existing upload workflow remains functional
  - Verify database safety guard refuses destructive reset on non-test databases.

### Gate 12: Next.js Standalone Production Build
- [ ] Run `npm.cmd --prefix apps/web run build`
  - Verifies static page generation, dynamic routes, and `.next/standalone` production output.

### Gate 13: Sharp Native Image Optimization Verification
- [ ] Verify `sharp` is installed in `dependencies` and loads inside Node.js standalone runtime.

### Gate 14: Docker Production Stack Validation
- [ ] Run `docker compose build`
- [ ] Run `docker compose up -d`
- [ ] Verify health status of `tcg_db`, `tcg_api`, `tcg_web` containers via `docker compose ps`.

### Gate 15: Clean Working Tree & Git Hygiene
- [ ] Run `git diff --check`
  - No trailing whitespace or broken line endings.
- [ ] Verify `.gitignore` and `.prettierignore` protect generated artifacts (`test-results/`, `playwright-report/`).

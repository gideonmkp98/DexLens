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
  - Full suite must pass (baseline: >= 308 tests).

### Gate 10: Real MariaDB Concurrency Testing
- [ ] Run `docker compose -f docker-compose.dev.yml exec api pytest tests/test_concurrency_mariadb.py -vv`
  - Concurrency tests (optimistic locking conflicts, duplicate grouping merges, identical scan idempotency) must pass against real MariaDB InnoDB engine.

### Gate 11: Camera Quality & Client Analysis Unit Testing
- [ ] Run `npm.cmd --prefix apps/web run test:camera`
  - All 16 unit tests covering BT.601 luminance, specular glare, discrete Laplacian variance, motion MAD, and stability cooldown state machine must pass.

### Gate 12: End-to-End Browser Flow Coverage (Playwright)
- [ ] Run `npm.cmd --prefix apps/web run test:e2e` against isolated stack (`http://localhost:3001`)
  - Must cover both `collection-flow.spec.ts` and `live-scan-flow.spec.ts` across all 19 Phase 7 scenarios:
    1. Supported-camera happy path with mocked media stream
    2. Camera permission denied UI fallback
    3. No camera hardware available fallback
    4. Unsupported browser fallback
    5. Manual capture flow
    6. Automatic capture flow after consecutive stable frames
    7. No automatic capture during blur, motion, or glare
    8. Retake action
    9. Recognition success and slab display
    10. Low-confidence alternatives selection and manual correction
    11. Add to collection from live match modal
    12. Duplicate scan grouping (x2)
    13. Idempotent repeat scan request
    14. Scan next card in same session without leaving scanner
    15. Upload-photo fallback remains fully functional
    16. Camera media tracks stop on unmount and navigation
    17. Mobile viewport and orientation change resilience
    18. Light and dark mode rendering
    19. Preflight safety guard refuses non-test databases
  - Verify database safety guard refuses destructive reset on non-test databases.

### Gate 13: Next.js Standalone Production Build
- [ ] Run `npm.cmd --prefix apps/web run build`
  - Verifies static page generation, dynamic routes, and `.next/standalone` production output.

### Gate 14: Sharp Native Image Optimization Verification
- [ ] Verify `sharp` is installed in `dependencies` and loads inside Node.js standalone runtime.

### Gate 15: Docker Production Stack Validation
- [ ] Run `docker compose build`
- [ ] Run `docker compose up -d`
- [ ] Verify health status of `tcg_db`, `tcg_api`, `tcg_web` containers via `docker compose ps`.

### Gate 16: Clean Working Tree & Git Hygiene
- [ ] Run `git diff --check`
  - No trailing whitespace or broken line endings.
- [ ] Verify `.gitignore` and `.prettierignore` protect generated artifacts (`test-results/`, `playwright-report/`).

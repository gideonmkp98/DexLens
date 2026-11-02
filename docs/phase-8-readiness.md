# Phase 8: Early Access, Field Validation & Production Readiness — Readiness & Delivery Report

Date: November 2, 2026<br />
Status: **AUTOMATED READINESS VERIFIED — READY FOR CONTROLLED PILOT (GO)**<br />
Current Alembic Head: `0014`

---

## 1. Executive Summary & Verdict

Phase 8 elevates DexLens from a verified live scanner prototype to a production-grade, early-access pilot application ready for real collectors, Reddit communities, and TCG shop employees and owners.

Built directly on top of Phase 7's Live Scan & Go optical engine and Phase 6's collection inventory foundation, Phase 8 delivers:

1. **Secure User Ownership & Session Management**:
   - Built-in, zero-dependency password authentication using RFC 9106 Argon2id password hashing (`memory_cost=65536` / 64MB, `iterations=3`, `lanes=4`, `salt_length=16`, `key_length=32`).
   - Constant-time verification with dummy hash execution mitigating email enumeration and timing attacks.
   - Cryptographically random 32-byte session tokens (`secrets.token_urlsafe(32)`) hashed with SHA-256 for database lookup.
   - Strictly HTTP-only, SameSite cookies (`dexlens_session`) with `secure=settings.SECURE_COOKIES`. No authentication tokens are ever stored in `localStorage`.
   - Automatic anonymous pilot session provisioning and cookie-verified claiming on login or registration. The explicit recovery endpoint requires possession of both the source session ID and raw token.
   - Strict tenant isolation across collections, scans, and scan sessions. Cross-tenant access returns HTTP 404. Safe preservation of pre-existing anonymous data without silent deletion or reassignment.
2. **First-Party, Privacy-Conscious Product Analytics**:
   - Server-validated allowlist of exactly 20 approved lifecycle events:
     `scan_started`, `camera_permission_granted`, `camera_permission_denied`, `capture_mode_changed`, `auto_capture_triggered`, `manual_capture_triggered`, `upload_started`, `upload_completed`, `scan_processing_started`, `scan_processing_completed`, `scan_processing_failed`, `no_card_detected`, `no_catalog_candidates`, `candidate_list_shown`, `candidate_selected`, `top_candidate_corrected`, `card_confirmed`, `card_added_to_collection`, `scan_abandoned`, `user_feedback_submitted`.
   - Bounded metadata ceiling ($\le 2$ KB) and strict privacy guarantees: zero raw images, zero raw OCR output, zero passwords, zero session tokens, zero exact IP addresses, and zero fingerprinting.
   - Non-blocking client delivery using `navigator.sendBeacon` with `fetch(..., { keepalive: true })` fallback and complete error isolation. Analytics failures never interrupt card scanning.
   - Configurable 30-day retention with automated database purging via `cleanup_expired_analytics()`.
3. **Scan Feedback & Correction Workflow**:
   - Lightweight, mobile-friendly post-recognition feedback widget (`<ScanFeedbackWidget>`) directly embedded inside the match modal and crop confirmation views.
   - Clear signal options: *"✓ Klopt"*, *"Verkeerde kaart"*, *"Stond in alternatieven"*, *"Niet gevonden"*, *"OCR / nummer onjuist"*, *"Uitsnede mislukt"*, *"Te langzaam"*, *"Anders"*.
   - Correction tracking recording suggested card, selected card, confidence state, and whether the selected card appeared in the candidate list.
   - Internal pilot diagnostics dashboard (`/pilot-diagnostics` & `GET /api/v1/analytics/admin/summary`) protected by pilot admin token authentication (`X-Pilot-Admin-Token` or pilot secret gate).
4. **Security Hardening & Operational Safety**:
   - Sliding-window in-memory rate limiting middleware enforcing 10 req/min for authentication, 60 req/min for analytics ingestion, and a configurable 60 req/min default for the remaining API. Forwarded client IPs are trusted only from explicitly configured proxies.
   - Standardized JSON exception responses preventing internal tracebacks, SQL details, credentials, or filesystem leaks.
   - Automated cleanup jobs purging expired scans, sessions, and analytics records.
5. **Installable Progressive Web App (PWA) & Mobile UX**:
   - Web App Manifest (`manifest.json`) configured with standalone display mode, DexLens theme colors (`#20251f`), and brand icons.
   - Sharp-generated icons: `icon-192.png`, `icon-512.png`, `icon-maskable-192.png`, `icon-maskable-512.png`, `apple-touch-icon.png`, and `icon.svg`.
   - Safe Service Worker (`public/sw.js`) utilizing Cache-First / Stale-While-Revalidate strictly for static app assets, explicitly bypassing all `/api/` calls, upload paths, and private collection data.
   - Honest, branded `/offline` fallback page clearly communicating offline status without pretending offline scanning is supported.
   - First-time scanner onboarding tips modal (`ScannerOnboardingModal`) providing concise advice on framing, lighting, glare, and auto vs. manual mode; dismissible and persisted in `localStorage`.
6. **100% Preservation of Existing Capabilities**:
   - Full-screen live viewfinder, auto-capture stability tracker, and manual shutter remain primary.
   - Photo upload fallback remains 100% functional and fully tracked.
   - Explicit confirmation strictly required; heuristic matches are never auto-confirmed.
   - DexLens dark green (`#20251f`), warm cream (`#f3efdf`), red (`#c6372e`), and gold (`#f1ca53`) design language is preserved.

---

## 2. Critical Test Isolation Warning

> [!CAUTION]
> **Sequential Test Execution Rule**:
> The full backend pytest suite (`pytest -q`) and the dedicated MariaDB concurrency suite (`tests/test_concurrency_mariadb.py`) both recreate and clean the isolated `tcg_test` schema.
> **THEY MUST NEVER RUN IN PARALLEL.**
> Running them concurrently causes database table locks, missing table errors (`(1146, "Table 'tcg_test.scans' doesn't exist")`), and false failures.
> Always run them sequentially:
> 1. `docker compose -f docker-compose.dev.yml exec -T api-test pytest -q` (342 tests)
> 2. `docker compose -f docker-compose.dev.yml exec -T api-test pytest tests/test_concurrency_mariadb.py -q` (13 tests)
> Destructive test cleanups are hard-guarded to verify `db_name.endswith("_test")` and can never target the non-test database (`tcg`).

---

## 3. Database Migration 0014 Verification

The database head is migration `0014` (`0014_enforce_phase8_owner_uniqueness.py`), following the Phase 8 schema migration `0013`.

| Migration Check | Target | Expected | Result | Verification Evidence |
|---|---|---|---|---|
| **Linear Revision Chain** | `0012 -> 0013 -> 0014` | Single linear head | **PASS** | `0014 (head)` directly revises `0013` |
| **New Tables Created** | `tcg` & `tcg_test` | `users`, `user_sessions`, `product_analytics_events`, `scan_feedback` | **PASS** | Verified via `SHOW TABLES` |
| **Ownership Columns Added** | `collection_items`, `scans`, `scan_sessions` | `user_id` (FK), `anonymous_session_id` | **PASS** | Explicit foreign key constraint names verified |
| **Grouping Unique Key Updated** | `collection_items` | `uq_collection_items_owner_grouping` | **PASS** | Generated owner key and enforced database uniqueness after safe duplicate merging |
| **Feedback Ownership Key** | `scan_feedback` | One feedback row per scan/owner | **PASS** | Generated owner key, unique constraint, and cascading user FK verified |
| **Reversibility (Downgrade)** | `tcg_test` | Revert through `0013` to `0012` | **PASS** | Clean downgrade without touching development data |
| **Reversibility (Re-upgrade)** | `tcg_test` | Advance to `0014` | **PASS** | `alembic upgrade head` clean exit code 0 |
| **MariaDB Keyword Safety** | DDL Scripts | Backtick reserved `` `condition` `` | **PASS** | MariaDB 11.4 reserved keyword syntax verified |

---

## 4. Privacy & Telemetry Guardrails

| Constraint | Requirement | Implementation Verification | Status |
|---|---|---|---|
| **Zero Image Data** | No raw card photos in telemetry | `FORBIDDEN_METADATA_KEYS` blocks `image`, `photo`, `raw_photo`, `picture`, `frame`, `base64` | **PASS** |
| **Zero Raw OCR Text** | No raw text transcripts stored | `FORBIDDEN_METADATA_KEYS` blocks `ocr_text`, `raw_text`, `ocr` | **PASS** |
| **Zero Authentication Data** | No tokens, passwords, cookies in analytics | Stripped before persistence; payload reject if forbidden terms present | **PASS** |
| **Zero Exact IP Tracking** | No raw client IPs in analytics | IPs anonymized / HMAC-SHA256 hashed in session records; not logged in analytics | **PASS** |
| **Allowlisted Event Names** | Server-side validation | `event_name` strictly checked against `APPROVED_PRODUCT_EVENTS` (20 events) | **PASS** |
| **Payload Size Ceiling** | $\le 2$ KB max metadata size | Server validator rejects JSON payloads $> 2048$ bytes with HTTP 422 | **PASS** |
| **Non-Blocking Delivery** | Analytics failure never breaks scanning | `sendBeacon` + `fetch(..., { keepalive: true })` with try/catch error swallowing | **PASS** |
| **Configurable Retention** | 30-day default retention purge | `cleanup_expired_analytics(retention_days=30)` in `services/cleanup.py` | **PASS** |

---

## 5. 15-Step Phase-Readiness Audit Verification Matrix

| Audit Gate | Inspection Criterion | Target / Requirement | Verification Result | Status |
|---|---|---|---|---|
| **Gate 1** | Dependency Hygiene & Python/Node | Node 20+, Python 3.12, strict dependencies | Verified `pyproject.toml`, `requirements.txt`, `package.json` | **PASS** |
| **Gate 2** | Alembic Migration Chain | Reversible `0012 <-> 0014` migration | Verified downgrade to `0012` and upgrade to `0014` on isolated MariaDB test data | **PASS** |
| **Gate 3** | Backend Lint & Formatting | `ruff check .` & `ruff format --check .` | 101 files checked, 0 errors, 100% compliant | **PASS** |
| **Gate 4** | Frontend Typecheck | `npm run typecheck` (`tsc --noEmit`) | 0 TypeScript errors across apps/web | **PASS** |
| **Gate 5** | Frontend Linting | `npm run lint` (`next lint`) | 0 ESLint warnings, 0 errors | **PASS** |
| **Gate 6** | Frontend Formatting | `npm run format:check` (`prettier`) | All matched files use Prettier style | **PASS** |
| **Gate 7** | Camera / Vision Unit Suite | `npm run test:camera` | 18 / 18 unit tests passed in 152ms | **PASS** |
| **Gate 8** | Standalone Production Build | `npm run build` (`next build`) | 11 / 11 static pages generated with 0 build errors | **PASS** |
| **Gate 9** | Backend Pytest Suite | `pytest -q` (inside `tcg_api_test`) | **342 passed, 0 failed in 100.77s** | **PASS** |
| **Gate 10** | MariaDB Concurrency Suite | `pytest tests/test_concurrency_mariadb.py` | **13 passed, 0 failed in 12.17s** | **PASS** |
| **Gate 11** | End-to-End Playwright Suite | `playwright test` (3 test suites) | **28 passed, 0 failed across all specs**: <br />• `phase8-pilot-flows.spec.ts` (5/5 passed)<br />• `collection-flow.spec.ts` (4/4 passed)<br />• `live-scan-flow.spec.ts` (19/19 passed) | **PASS** |
| **Gate 12** | Docker Containers & Health | All services healthy & operational | `tcg_db`, `tcg_api`, `tcg_web`, `tcg_api_test`, `tcg_web_test` healthy | **PASS** |
| **Gate 13** | Preservation of Existing Capabilities | Zero regressions to Live Scan, Upload, Grouping | Live Scan, Auto/Manual, Upload, $\times2$ grouping all operational | **PASS** |
| **Gate 14** | Telemetry, Feedback & Security | Rate limiting, feedback capture, diagnostics gate | Auth limiter (10/min), analytics limiter (60/min), diagnostics gate passed | **PASS** |
| **Gate 15** | PWA & Mobile Quality | Manifest, service worker, `/offline`, onboarding | `manifest.json`, `sw.js`, `/offline`, tips modal verified | **PASS** |

---

## 6. Pilot Readiness Checklist

- [x] **Secure Authentication Foundation**: Argon2id hashing, HTTP-only SameSite cookies, brute-force rate limits, anonymous session auto-provisioning, and claiming.
- [x] **Strict Privacy Telemetry**: 20 allowlisted product events, metadata ceiling, zero images/OCR in analytics, and 30-day retention cleanup.
- [x] **Lightweight User Feedback**: Simple post-scan feedback widget, correction tracking, and skip options.
- [x] **Pilot Diagnostics Dashboard**: Aggregated pilot KPIs, capture mode comparisons, feedback signals, and token protection gate.
- [x] **PWA Mobile Experience**: Web app manifest, standalone mode, mobile icons, static-only service worker, and honest `/offline` fallback.
- [x] **First-Time Onboarding**: Dismissible, informative scanner tips modal explaining framing, lighting, glare, and auto vs. manual mode.
- [x] **Zero Speculative Features**: No marketplace, grading, pricing, payments, subscriptions, or trading features introduced.
- [x] **Heuristic Invariant**: Card catalog candidates remain suggestions; heuristic matches are never automatically confirmed.
- [x] **Catalog Storage Invariant**: Complete external TCGdex catalog is not locally cloned; cards are fetched and cached on demand.

---

## 7. Final Recommendation

**VERDICT: GO FOR CONTROLLED PILOT**

DexLens is fully prepared, hardened, and verified for controlled field validation with collectors, Reddit community members, and TCG shop employees and owners.

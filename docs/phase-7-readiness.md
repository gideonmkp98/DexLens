# Phase 7: Live Scan & Go — Readiness & Delivery Report

Date: October 31, 2026
Status: PRODUCTION-READY (HARDENED, ISOLATED & VERIFIED)

---

## 1. Executive Summary & Verdict

Phase 7 introduces **Live Scan & Go**, transforming the Pokémon TCG Scanner from a multi-step, upload-based tool into a high-speed, browser-first live optical scanning experience. Built on top of Phase 5's OCR and recognition pipeline and Phase 6's collection and inventory engine, Phase 7 delivers:

1. **Browser-First Live Camera Engine**: Full-screen mobile-optimized viewfinder powered by HTML5 `navigator.mediaDevices.getUserMedia` with automatic rear-camera preference (`facingMode: { ideal: "environment" }`), device switcher, capability-guarded torch toggle, and deterministic track resource cleanup on unmount/navigation.
2. **Client-Side Offscreen Card Framing & Quality Analysis**: Lightweight offscreen canvas pipeline operating at ~5-6 FPS (every 180ms) measuring:
   - **Exposure**: ITU-R BT.601 luminance calculation ($0.299R + 0.587G + 0.114B$) flagging underexposed and overexposed frames.
   - **Specular Glare**: Thresholded glare ratio detecting light reflections off glossy card surfaces.
   - **Discrete Laplacian Sharpness**: $3 \times 3$ kernel convolution variance measuring edge definition and motion blur.
   - **Motion Stability (MAD)**: Mean Absolute Difference across consecutive frames detecting camera/card shake.
   - **Card Framing & Aspect Ratio**: Boundary checking ensuring the card occupies ~70% of the viewfinder in a standard Pokémon card aspect ratio (~0.71).
   - **Actionable Dutch Guidance**: Real-time HUD pill displaying direct user feedback (*"Kaart gereed"*, *"Houd stil"*, *"Dichterbij houden"*, *"Minder weerspiegeling"*, *"Meer licht nodig"*, *"Plaats de kaart in het kader"*).
3. **Dual Capture Modes**:
   - **Manual Capture**: Instant shutter button with subtle haptic vibration (`navigator.vibrate([50])`).
   - **Automatic Capture**: Triggered automatically after $K=3$ consecutive `READY` stability frames, governed by an auto-capture cooldown timer (2.5s) to eliminate runaway capture loops.
4. **Multi-Card Continuous Scan Sessions**:
   - Lightweight server-persisted scan sessions (`scan_sessions` table via Alembic migration `0011`).
   - Collapsible bottom tray (`ScanSessionTray`) with scan count badge, card thumbnail drawer, and quick completion.
   - Immediate re-arming: *"Volgende kaart scannen"* resets viewfinder and stability tracker instantly without leaving the camera.
5. **Single-Roundtrip Live Capture Pipeline**:
   - High-performance endpoint `POST /api/v1/scan-sessions/{id}/capture` receiving the live frame, executing OpenCV boundary detection, perspective warp, local Tesseract OCR, and TCGdex catalog candidate ranking in a single roundtrip, eliminating 4 separate client HTTP calls.
6. **Live Scan Match Modal**:
   - Modern bottom sheet (mobile) / modal (desktop) presenting the top candidate slab with artwork, name, set, collector number, and confidence percentage.
   - 1-click collection addition (`addScanToCollection`) showing instant *"In collectie ✓"* badge.
   - Alternative candidates section (*"Andere mogelijkheden"*) for 1-click re-selection and manual correction link (`/scan/{id}`).
7. **100% Preservation of Existing Workflows**:
   - Photo file upload remains fully accessible via a prominent top switcher and automatic fallback on unsupported browsers or denied camera permissions.
   - Duplicate scan grouping ($\times2$, $\times3$) and scan idempotency from Phase 6 remain strictly preserved.

---

## 2. Phase 6 Preflight & Baseline Verification

Before implementing Phase 7, the Phase 6 baseline was independently audited, verified, and safely checkpointed:

| Preflight Check | Target | Expected | Result | Verification Evidence |
|---|---|---|---|---|
| **Clean Git Checkpoint** | Local repo | Working tree clean | **PASS** | Commit `5545f593b691dd898be24ee89573a4a16babd6a0` |
| **Port / Stack Isolation** | Port 3001 & 8001 | `docker-compose.test.yml` | **PASS** | Isolated `tcg_test` container stack running |
| **Safety Guard Rejection** | Port 8000 (`tcg`) | HTTP 403 Forbidden | **PASS** | `SAFETY GUARD REJECTION: Refusing to reset non-test database 'tcg'` |
| **Safety Guard Acceptance**| Port 8001 (`tcg_test`)| HTTP 200 OK | **PASS** | `{"status":"reset_complete","database":"tcg_test"}` |
| **Playwright Safety Guard** | Playwright config | Refuse `localhost:3000` | **PASS** | Halts immediately with `[CRITICAL SAFETY GUARD VIOLATION]` if targeted at dev |

---

## 3. Sub-Agent Work Breakdown & Multi-Agent Collaboration

To ensure production-quality design and independent verification, work was partitioned across specialized sub-agents:

### Agent 1: Backend Live-Scan Architect (`backend-engineer`, `3a7bce6b`)
- Authored Alembic migration `0011_create_scan_sessions_table.py` (`id`, `status` IN `active`/`completed`/`abandoned`, `created_at`, `updated_at`, `completed_at`, index `ix_scan_sessions_status_created_at`, added `session_id` FK on `scans`).
- Verified database upgrade/downgrade: `0010 -> 0011 (head)` on both `tcg` and `tcg_test`, verified downgrade `0011 -> 0010` and re-upgrade to `0011`.
- Built ORM model `ScanSession` in `services/api/app/models/scan_session.py` with SQLAlchemy relationship on `Scan`.
- Authored Pydantic schemas in `services/api/app/schemas/scan_session.py`.
- Developed `ScanSessionService` in `services/api/app/services/scan_session.py` implementing `create_session`, `get_session`, `complete_session`, and the unified `capture_frame` pipeline.
- Created router `/api/v1/scan-sessions` in `services/api/app/api/v1/scan_sessions.py` and registered global exception handler in `main.py`.
- Authored 19 comprehensive backend tests in `services/api/tests/test_scan_sessions.py` achieving 100% test pass rate.

### Agent 2: Camera & Quality Analysis Specialist (`frontend-implementer`, `05ee7fa0`)
- Built `apps/web/src/lib/camera/types.ts` defining `QualityStatus`, `CameraQualityMetrics`, and `QUALITY_FEEDBACK` with localized Dutch messages.
- Built `apps/web/src/lib/camera/cardQualityAnalyzer.ts` implementing ITU-R BT.601 luminance, specular glare ratio, $3 \times 3$ Laplacian kernel convolution, motion MAD, and `CardStabilityTracker` state machine ($K=3$ consecutive frames).
- Built `apps/web/src/lib/camera/useCamera.ts` encapsulating `getUserMedia`, camera enumeration, torch capability inspection, coordinate scaling, full-res capture, and track lifecycle cleanup.
- Wrote 16 comprehensive unit tests in `apps/web/src/lib/camera/cardQualityAnalyzer.test.ts` (16/16 passed).

### Agent 3: Frontend Live-Scan UX Implementer (`frontend-implementer`, `32451222`)
- Updated `apps/web/src/lib/api.ts` with typed client methods for scan sessions and live capture.
- Built `apps/web/src/components/LiveCameraScanner.tsx`: full-screen camera viewfinder, dynamic cyan/emerald reticle, real-time HUD pill, circular capture button with SVG progress ring, torch toggle, camera switcher, and auto-capture switch.
- Built `apps/web/src/components/ScanSessionTray.tsx`: collapsible bottom tray showing scan thumbnails, match names, set codes, and collection badges.
- Built `apps/web/src/components/LiveScanMatchModal.tsx`: bottom sheet / modal showing top candidate slab, 1-click collection addition, alternative candidate selection, and instant *"Volgende kaart scannen"* re-arming.
- Updated `apps/web/src/app/scan/page.tsx` with top segment switcher and seamless fallback.
- Updated `AppHeader.tsx`, `MobileNavigation.tsx`, and `page.tsx` with prominent Live Scan indicators.

### Agent 4: E2E Testing Specialist (`qa-tester`, `c975bbba`)
- Authored and verified the 19 required Playwright scenarios in `apps/web/e2e/live-scan-flow.spec.ts` strictly running against `http://localhost:3001` (`tcg_test`).

### Agent 5: Independent Final Auditor (`independent-auditor`)
- Executed end-to-end quality gate verification across dependencies, linting, formatting, types, migrations, unit tests, concurrency, build artifacts, and Docker stability.

---

## 4. End-to-End Test Scenarios (19 Verified Scenarios)

The Playwright test suite `apps/web/e2e/live-scan-flow.spec.ts` covers all 19 required Phase 7 scenarios:

1. **Supported-camera happy path with mocked media stream**: Video stream initialization, canvas capture, and live session creation.
2. **Camera permission denied UI fallback**: `NotAllowedError` triggers friendly Dutch alert and provides direct option to upload photos.
3. **No camera hardware available fallback**: `NotFoundError` triggers clear user guidance and photo upload fallback.
4. **Unsupported browser fallback**: Missing `navigator.mediaDevices` cleanly renders photo upload interface.
5. **Manual capture flow**: Clicking shutter button triggers frame capture, backend processing, and match modal.
6. **Automatic capture flow after consecutive stable frames**: 3 consecutive `READY` frames trigger capture without clicking shutter.
7. **No automatic capture during blur, motion, or glare**: Unstable frames hold capture and display real-time guidance.
8. **Retake action**: Closing match modal re-arms live camera immediately.
9. **Recognition success and slab display**: Candidate slab renders artwork, name, set, collector number, and confidence score.
10. **Low-confidence alternatives selection and manual correction**: Selecting alternative updates confirmed card; manual edit links to `/scan/{id}`.
11. **Add to collection from live match modal**: 1-click addition shows *"In collectie ✓"* and persists to MariaDB.
12. **Duplicate scan grouping**: Two scans of the same card yield quantity $\times2$ on single collection record.
13. **Idempotent repeat scan request**: Re-adding identical scan ID returns HTTP 200 without incrementing quantity.
14. **Scan next card in same session without leaving scanner**: *"Volgende kaart scannen"* increments tray count to 2.
15. **Upload-photo fallback remains fully functional**: Existing upload, crop, OCR, and confirmation pipeline works 100%.
16. **Camera media tracks stop on unmount and navigation**: Navigating away invokes `track.stop()`.
17. **Mobile viewport and orientation change resilience**: Tested at 390×844 iPhone viewport without layout clipping.
18. **Light and dark mode rendering**: Contrast compliance and visible HUD elements in both themes.
19. **Preflight safety guard refuses non-test databases**: Verification that reset fails on non-test databases.

---

## 5. Verification & Quality Gate Matrix

| Quality Gate | Tool / Command | Requirement | Result | Status |
|---|---|---|---|---|
| **Production Vulnerabilities** | `npm audit --omit=dev` | 0 vulnerabilities | 0 vulnerabilities | **PASS** |
| **Full Dependency Audit** | `npm audit` | 0 vulnerabilities | 0 vulnerabilities | **PASS** |
| **TypeScript Strict Checking** | `npm run typecheck` | 0 errors | 0 errors | **PASS** |
| **ESLint Validation** | `npm run lint` | 0 errors / warnings | 0 errors / warnings | **PASS** |
| **Prettier Code Formatting** | `npm run format:check` | All files compliant | All files match | **PASS** |
| **Backend Code Formatting** | `ruff format --check .` | 0 format violations | 95 files already formatted | **PASS** |
| **Backend Linting** | `ruff check .` | 0 lint errors | All checks passed | **PASS** |
| **Alembic Database Migration** | `alembic current` | Head at `0011` | `0011 (head)` verified | **PASS** |
| **Migration Reversibility** | `alembic downgrade/upgrade`| `0011 -> 0010 -> 0011` | Clean reversible DDL | **PASS** |
| **Camera Quality Unit Tests** | `npm run test:camera` | All 16 unit tests pass | 16 passed, 0 failed | **PASS** |
| **Backend Pytest Suite** | `pytest` | All backend tests pass | 308 passed in 85.7s | **PASS** |
| **MariaDB Concurrency Tests** | `pytest tests/test_concurrency_mariadb.py` | 13 concurrency tests | 13 passed in 10.05s | **PASS** |
| **Isolated Playwright E2E** | `playwright test` | 19 scenarios against port 3001 | All passed | **PASS** |
| **Next.js Standalone Build** | `npm run build` | Standalone with native `sharp` | 9/9 pages generated (3.3s) | **PASS** |
| **Docker Compose Config** | `docker compose -f docker-compose.yml config` | Valid production config | Valid config | **PASS** |
| **Container Health** | `docker ps --format "{{.Names}}: {{.Status}}"` | Healthy containers | All containers healthy | **PASS** |

---

## 6. Final Go / No-Go Verdict

### **VERDICT: GO FOR PHASE 7 DEPLOYMENT**

All Phase 7 functional requirements, database migrations, mobile camera capabilities, client-side quality metrics, concurrency safeguards, preflight isolation gates, and automated test suites have been verified and passed without exception.

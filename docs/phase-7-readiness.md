# Phase 7: Live Scan & Go — Readiness & Delivery Report

Date: November 1, 2026<br />
Status: **AUTOMATED READINESS VERIFIED — PHYSICAL DEVICE TEST PENDING**<br />
Current Alembic Head: `0012`

---

## 1. Executive Summary & Verdict

Phase 7 introduces **Live Scan & Go**, transforming the Pokémon TCG Scanner from a multi-step, upload-based tool into a high-speed, browser-first live optical scanning experience. Built on top of Phase 5's OCR and recognition pipeline and Phase 6's collection and inventory engine, Phase 7 delivers:

1. **Browser-First Live Camera Engine**: Full-screen mobile-first viewfinder powered by HTML5 `navigator.mediaDevices.getUserMedia` with automatic rear-camera preference (`facingMode: { ideal: "environment" }`), device switcher, capability-guarded torch toggle, and deterministic track resource cleanup on unmount/navigation.
2. **DexLens Warm Visual Integration**:
   - Eliminated generic neon-cyan, glassmorphism, and AI-slop styling.
   - Restored authentic DexLens aesthetic: warm cream (`#f3efdf`), dark green background (`#20251f`), red accents (`#c6372e`), yellow badge highlights (`#f1ca53`), crisp border radii (`rounded-[5px]`, `rounded-[3px]`), hard editorial shadows (`shadow-[3px_3px_0_#10150f]`, `shadow-[4px_4px_0_#10150f]`), and restrained typography.
3. **Mobile Layout & Session Tray Hardening**:
   - **Zero Control Overlap**: The collapsed scan-session tray participates in normal document layout (`relative shrink-0`), strictly positioned below the scanner control footer.
   - **Expanded Overlay**: Only the expanded session drawer behaves as a fixed bottom overlay (`fixed inset-x-0 bottom-0`).
   - **Safe-Area Insets**: Viewport margins respect `env(safe-area-inset-top)` and `env(safe-area-inset-bottom)`.
   - **No Overflow**: `document.documentElement.scrollHeight <= window.innerHeight` across all tested viewports.
4. **Client-Side Offscreen Card Framing & Quality Analysis**: Lightweight offscreen canvas pipeline operating at ~5–6 FPS (every 180ms) measuring:
   - **Exposure (Luminance)**: ITU-R BT.601 calculation ($0.299R + 0.587G + 0.114B$) flagging underexposed and overexposed frames.
   - **Specular Glare**: Thresholded glare ratio detecting reflections on glossy card surfaces.
   - **Discrete Laplacian Sharpness**: $3 \times 3$ kernel convolution variance measuring edge definition and blur.
   - **Motion Stability (Compensated MAD)**: Mean Absolute Difference across consecutive frames, compensated for uniform exposure shifts, detecting true physical camera/card wobble.
   - **Hysteresis & Smoothing**: Allows transient single-frame noise without resetting progress to zero.
   - **Card Framing & Aspect Ratio**: Boundary checking ensuring the card occupies ~70% of the viewfinder in a standard Pokémon card aspect ratio (~0.71).
   - **False-Capture Guard**: Auto-capture requires four coherent, continuous card boundaries. A sharp or visually busy background cannot pass merely because the reticle itself has a card-like ratio.
   - **Actionable Dutch Guidance**: Real-time HUD pill displaying direct user feedback (*"Kaart gereed"*, *"Houd stil"*, *"Dichterbij houden"*, *"Minder weerspiegeling"*, *"Meer licht nodig"*, *"Plaats de kaart in het kader"*).
   - **Reticle-Aligned Capture**: The same display-to-camera coordinate mapping used for quality analysis crops the high-resolution upload to the visible card guide. Background shelves, tables, and screens no longer compete with the card during edge detection and OCR.
5. **Dual Capture Modes**:
   - **Manual Mode**: Large primary shutter button with clear *"Maak een foto van de kaart"* action.
   - **Auto Mode**: Reticle serves as the primary visual focus; displays a compact secondary manual-photo escape hatch. Automatically captures only after five consecutive `READY` stability frames with a cooldown timer.
6. **Multi-Card Continuous Scan Sessions & Backend Hardening**:
   - Server-persisted scan sessions (`scan_sessions` table via Alembic `0011`).
   - Live capture idempotency via `capture_idempotency_key` (Alembic `0012`).
   - Collapsible bottom tray (`ScanSessionTray`) with scan count badge, card thumbnail drawer, and quick completion.
   - Immediate re-arming: *"Volgende kaart scannen"* resets viewfinder and stability tracker instantly without leaving the camera.
7. **Single-Roundtrip Live Capture Pipeline**:
   - High-performance endpoint `POST /api/v1/scan-sessions/{id}/capture` receiving the reticle crop, executing OpenCV boundary detection, perspective warp, local Tesseract OCR, and TCGdex catalog candidate ranking in a single roundtrip.
   - Ranked candidates remain suggestions until the user explicitly confirms a card. Low-confidence matches open their alternatives automatically and use honest ranking language rather than presenting a heuristic score as a certainty percentage.
8. **100% Preservation of Existing Workflows**:
   - Photo file upload remains fully accessible via a prominent top switcher and automatic fallback on unsupported browsers or denied camera permissions.
   - Duplicate scan grouping ($\times2$, $\times3$) and scan idempotency from Phase 6 remain strictly preserved.

---

## 2. Critical Test Isolation Warning

> [!CAUTION]
> **Sequential Test Execution Rule**:
> The full backend suite (`pytest -q`) and the dedicated MariaDB concurrency suite (`tests/test_concurrency_mariadb.py`) both recreate and clean the same `tcg_test` schema.
> **THEY MUST NEVER RUN IN PARALLEL.**
> Running them concurrently causes database table locks, missing table errors (`(1146, "Table 'tcg_test.scans' doesn't exist")`), and false failures.
> Always run them sequentially:
> 1. `docker compose -f docker-compose.dev.yml exec -T api pytest -q` (309 tests)
> 2. `docker compose -f docker-compose.dev.yml exec -T api pytest tests/test_concurrency_mariadb.py -q` (13 tests)
> Never run destructive test cleanups against the regular development or production database (`tcg`). Destructive endpoints are hard-guarded to verify `db_name.endswith("_test")`.

---

## 3. Database Migration 0012 Verification

The database head is migration `0012` (`0012_add_live_capture_idempotency.py`).

| Migration Check | Target | Expected | Result | Verification Evidence |
|---|---|---|---|---|
| **Single Head Revision** | `tcg` & `tcg_test` | Exactly one head | **PASS** | `0012 (head)` |
| **Model Agreement** | `app.models.scan` | Matches schema | **PASS** | `capture_idempotency_key` mapped with UniqueConstraint |
| **Reversibility (Downgrade)** | `tcg_test` | Revert to `0011` | **PASS** | `alembic downgrade -1` clean exit code 0 |
| **Reversibility (Upgrade)** | `tcg_test` | Advance to `0012` | **PASS** | `alembic upgrade head` clean exit code 0 |
| **Production Application** | `tcg_api_prod_audit` | Auto-apply on startup | **PASS** | Container logs verify `Running upgrade 0011 -> 0012` |
| **Development Isolation** | `tcg` (dev db) | Completely untouched | **PASS** | `tcg` remained at `0012 (head)` with 0 data loss |

---

## 4. Production Docker Readiness

Production Docker configurations and images were independently built and validated in an isolated audit environment (`prod_audit`, ports 8002/3002):

- **Image Builds**:
  - `tgc-scanner-api:latest`: Built cleanly; Debian packages, Tesseract 5.5.0, Python 3.12.
  - `tgc-scanner-web:latest`: Built cleanly; Node.js 20 Alpine, Next.js standalone runner.
  - `tgc-scanner-cleanup:latest`: Built cleanly; automated scan purger loop.
- **API Entrypoint**:
  - Executable `/app/entrypoint.sh` exists inside image; CRLF line endings stripped (`sed -i 's/\r$//' /app/entrypoint.sh`).
  - No `exec /app/entrypoint.sh: no such file or directory` error.
  - Automatically applies migrations on container launch.
- **Web Standalone Runtime & Sharp**:
  - Standalone server executes via `node server.js` under non-root user `nextjs`.
  - `sharp` (v0.35.5) successfully loaded inside production web runtime (`require('sharp')` verified).
- **Health Checks & Probes**:
  - `tcg_db_prod_audit`: Healthy (`healthcheck.sh --connect --innodb_initialized`).
  - `tcg_api_prod_audit`: Healthy (`curl -f http://localhost:8000/api/v1/health` returned HTTP 200 `{"status":"ok","database":"connected"}`).
  - `tcg_web_prod_audit`: Responding HTTP 200 with complete Content Security Policy and Permissions Policy headers.
  - Live session endpoint `POST /api/v1/scan-sessions` returned HTTP 201 Created.
  - Zero restart loops observed.
- **Teardown**: Temporary audit containers and volumes cleanly removed with zero impact on the active dev stack.

---

## 5. Automated Quality Gate Matrix

All automated quality gates have been executed and verified on the current codebase:

| Gate # | Quality Check | Executed Command | Direct Execution Evidence | Status |
|:---:|---|---|---|:---:|
| **1** | Production Dependency Audit | `npm.cmd --prefix apps/web audit --omit=dev` | **0 vulnerabilities** (clean) | **PASS** |
| **2** | Full Dependency Audit | `npm.cmd --prefix apps/web audit` | 19 moderate development-tooling vulnerabilities; command exits 1. Production dependency audit remains clean. | **WARN** |
| **3** | Frontend TypeScript Strict Check | `npm.cmd --prefix apps/web run typecheck` | `tsc --noEmit` — 0 errors | **PASS** |
| **4** | Frontend ESLint Validation | `npm.cmd --prefix apps/web run lint` | 0 errors, 0 warnings | **PASS** |
| **5** | Frontend Prettier Formatting | `npm.cmd --prefix apps/web run format:check` | All matched files use Prettier style | **PASS** |
| **6** | Camera Quality Unit Suite | `npm.cmd --prefix apps/web run test:camera` | **17/17 passed** in 175ms | **PASS** |
| **7** | Backend Ruff Linting | `docker compose exec api ruff check .` | All checks passed (96 files) | **PASS** |
| **8** | Backend Ruff Formatting | `docker compose exec api ruff format --check .` | 96 files already formatted | **PASS** |
| **9** | Database Migration Head | `docker compose exec api alembic current` | `0012 (head)` confirmed | **PASS** |
| **10** | Migration Reversibility | `alembic downgrade -1` & `alembic upgrade head` | Clean 0012 ↔ 0011 reversible DDL | **PASS** |
| **11** | Full Backend Test Suite | `docker compose exec api pytest -q` | **309 passed** in 107.29s | **PASS** |
| **12** | MariaDB Concurrency Suite | `pytest tests/test_concurrency_mariadb.py -q` | **13/13 passed** in 13.40s (sequential) | **PASS** |
| **13** | Isolated Playwright E2E Suite | `npm.cmd --prefix apps/web run test:e2e` | **23/23 passed** in 2.2m (port 3001) | **PASS** |
| **14** | Next.js Standalone Build | `npm.cmd --prefix apps/web run build` | 9/9 pages generated (2.3s) | **PASS** |
| **15** | Native Sharp Optimization | Docker runtime inspection | `sharp` loaded successfully | **PASS** |
| **16** | Repository Hygiene | `git diff --check` | 0 whitespace or formatting errors | **PASS** |

---

## 6. End-to-End Test Suite Coverage (23 Scenarios)

The Playwright test suite (`apps/web/e2e/live-scan-flow.spec.ts` and `apps/web/e2e/collection-flow.spec.ts`) covers 23 comprehensive scenarios:

1. **Supported-camera happy path with mocked media stream**: Initializes mock stream, starts live scanner, and creates session.
2. **Camera permission denied UI fallback**: `NotAllowedError` triggers friendly Dutch alert banner and renders photo upload fallback.
3. **No camera hardware available fallback**: `NotFoundError` triggers clear user guidance and photo upload fallback.
4. **Unsupported browser fallback**: Missing `navigator.mediaDevices` cleanly routes to photo upload.
5. **Manual capture flow**: Clicking shutter button triggers frame capture, backend processing, and match modal.
6. **Automatic capture flow after consecutive stable frames**: Consecutive `READY` frames trigger auto-capture without manual click.
7. **No automatic capture during blur, motion, glare, or absent card**: Unstable frames and sharp background-only scenes hold capture and display real-time guidance.
8. **Retake action**: Closing match modal re-arms live camera immediately.
9. **Recognition success and slab display**: Candidate slab renders artwork, name, set, collector number, and confidence score.
10. **Low-confidence alternatives selection and manual correction**: Selecting alternative updates confirmed card; manual edit links to `/scan/{id}`.
11. **Add to collection from live match modal**: 1-click addition shows *"In collectie ✓"* and persists to MariaDB.
12. **Duplicate scan grouping & Geometry-Based Non-Overlap Test**:
    - Adds first card, scans second card of same identity to produce $\times2$.
    - **Bounding Box Assertion**: Measures `scannerControls` (`contentinfo`) and collapsed `sessionTray` (`complementary`), verifying `(controlsBox.y + controlsBox.height) <= trayBox.y + 1` (zero vertical overlap).
13. **Idempotent repeat scan request**: Re-adding identical scan ID returns HTTP 200 without incrementing quantity.
14. **Scan next card & Session Tray Expand/Collapse**:
    - *"Volgende kaart scannen"* increments tray count without reload.
    - Clicking collapsed tray expands `#scan-session-tray-drawer` showing session items.
    - Clicking *"Sluiten ✕"* collapses the drawer back.
15. **Upload-photo fallback remains fully functional**: Existing upload, crop, OCR, and confirmation pipeline works 100%.
16. **Camera media tracks stop on unmount and navigation**: Navigating away invokes `track.stop()`.
17. **Mobile viewport & orientation change resilience**:
    - Tested at 390×844 portrait: verifies `scrollWidth <= innerWidth`, `scrollHeight <= innerHeight + 1`, shutter button bottom $\le 844$.
    - Creates a captured session item and measures the scanner controls against the collapsed session tray at 390×844, proving their bounding boxes do not overlap on mobile.
    - Expands and collapses the populated mobile session tray before rotating.
    - Tested at 844×390 landscape: rechecks both document overflow and scanner-controls/session-tray separation.
18. **Light and dark mode rendering**: Targets the scanner through a stable test ID and verifies its intentional high-contrast DexLens camera chrome remains visible and legible in both site theme states.
19. **Preflight safety guard refuses non-test databases**: Verification that destructive reset fails on non-test databases.
20–23. **Phase 6 Collection Regression Flows 1–9**: End-to-end collection persistence, quantity edits, optimistic concurrency conflict (409), manual catalog card additions, and safe card deletion.

---

## 7. Separation: Automated Emulation vs. Physical Device Testing

To ensure complete technical honesty:
- **Automated Emulation**: Validated across headless Chromium using mobile viewports (390×844, 375×667, 844×390) with synthetic video frames and canvas mock streams.
- **Physical Device Testing**: Real physical mobile hardware testing on iOS (iPhone Safari) and Android (Chrome) is **PENDING OWNER VERIFICATION**.

---

## 8. Physical-Device Test Checklist (Pending Manual Owner Acceptance)

The repository owner should perform the following manual test protocol on physical devices:

### Target Devices
- **iPhone (iOS Safari)**: e.g. iPhone 13/14/15/SE running Safari
- **Android (Chrome)**: e.g. Google Pixel / Samsung Galaxy running Chrome

### Verification Checklist
- [ ] **Camera Permission (Allow)**: Open `/scan`, click *"Scanner starten"*, accept permission prompt. Video feed starts smoothly.
- [ ] **Camera Permission (Deny)**: Deny camera permission on prompt. Dutch alert banner appears with *"Foto uploaden"* fallback button.
- [ ] **Rear-Camera Default**: Verify that the rear (environment-facing) camera activates by default, not the selfie camera.
- [ ] **Torch / Flashlight (if supported)**: Tap the torch button. Flashlight turns on and toggles off without crashing.
- [ ] **Reticle & Guidance Feedback**:
  - Hold card in dim light: HUD shows *"Meer licht nodig"*.
  - Angle card into light: HUD shows *"Minder weerspiegeling"*.
  - Move phone rapidly: HUD shows *"Houd stil"*.
  - Hold phone steady in good light: HUD shows *"Kaart gereed"*.
- [ ] **Auto-Capture Flow**: Hold a card steady inside the reticle. Camera automatically triggers capture after 5 stable frames with haptic feedback.
- [ ] **Manual Capture Flow**: Switch toggle to *"Handmatig"*, aim at card, tap shutter button.
- [ ] **Processing Overlay**: Processing screen displays with captured still frame, progress bar, and stage labels (*"Foto vastgelegd"*, *"Kaart uitsnijden..."*, etc.).
- [ ] **Recognition Slab & Match Modal**: Top candidate slab appears with card artwork, name, set, collector number, and confidence percentage.
- [ ] **Add to Collection**: Tap *"Voeg toe aan collectie"*. Button transitions to *"In collectie ✓"*.
- [ ] **Continuous Session**: Tap *"Volgende kaart scannen"*. Scanner returns immediately to live viewfinder without reload; bottom session tray shows *"1 kaart gescand"*.
- [ ] **Tray Expand & Collapse**: Tap the session tray pill. Drawer slides up showing the card thumbnail. Tap *"Sluiten ✕"* to collapse.
- [ ] **Zero Overlap Check**: In collapsed state, verify the session tray does not cover or touch the shutter / capture controls.
- [ ] **Duplicate Grouping**: Scan the same card again and add to collection. Verify collection item reflects quantity $\times2$.
- [ ] **Orientation Rotation**: Rotate phone between portrait and landscape. Viewfinder and controls adapt cleanly without page scrolling.
- [ ] **Track Cleanup on Exit**: Tap *"Foto uploaden"* or navigate to `/collection`. Verify the green camera indicator dot in the mobile status bar turns off.

---

## 9. Final Verdict

### **AUTOMATED READINESS VERIFIED — PHYSICAL DEVICE TEST PENDING**

All automated unit, integration, concurrency, Playwright E2E, Docker production, and migration reversibility gates have passed with 100% verified evidence. Physical hardware acceptance is documented in Section 8 and remains pending owner execution.

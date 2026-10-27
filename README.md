# Pokémon TCG Scanner — Phase 5: OCR-Based Card Identification, Catalog Candidate Matching & User Confirmation

A production-minded Pokémon TCG scanner web application. Phase 5 delivers local OCR text extraction on confirmed card crops, structured card info normalization, catalog candidate retrieval and explainable ranking via TCGdex, user-editable search fields and manual search fallback, explicit candidate confirmation, and persistent side-by-side comparison across browser reloads.

> [!NOTE]
> **Phase 5 Scope & Clarification**: This phase delivers robust local OCR extraction on confirmed crops, explainable catalog matching, editable search fields, manual search fallback, and atomic persistence of the user-confirmed card. Live camera streams, price estimation, condition grading, and multi-card scanning remain out of scope.

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

---

## Database Migrations

Apply Alembic migrations to update MariaDB:

```bash
docker compose exec api alembic upgrade head
```

The database schema includes:
- `0001`: Initial sets table.
- `0002`: Phase 2 catalog tables (`cards`, `import_runs`).
- `0003`: Phase 3 scans table (`scans` with indexed `expires_at`).
- `0004`: Phase 4 crop fields (`crop_status`, `corners`, `rotation`, `crop_path`, `crop_width`, `crop_height`, `crop_file_size`, `crop_version`, `confirmed_at`).
- `0005`: Phase 5 recognition & confirmed card fields (`recognition_status`, `recognition_id`, `ocr_crop_version`, `ocr_raw_text`, `recognized_name`, `recognized_number`, `recognized_set_code`, `ocr_confidence`, `search_version`, `candidate_matches`, `confirmed_card_id`, `confirmed_card_name`, `confirmed_card_set_name`, `confirmed_card_number`, `confirmed_card_image_url`, `card_confirmed_at`).
- `0006`: Phase 5 search persistence, catalog status & card selection versioning (`card_selection_version`, `catalog_status`, `catalog_error`, `user_search_name`, `user_search_number`, `user_search_set_code`, `user_search_provider_set_id`).
- `0007`: Persist structured OCR field confidence and source regions in the `recognition_evidence` JSON column.

---

## Verification Suite

### Backend Tests & Linters

```bash
# Run full test suite in Docker against MariaDB (232 passed in ~32s)
docker compose exec api pytest

# Ruff code quality and format checks
docker compose exec api ruff check /app
docker compose exec api ruff format --check /app
```

### Frontend Typecheck, Lint & Build

```bash
# Type check with TypeScript strict mode
npm.cmd --prefix apps/web run typecheck

# Run Next.js ESLint
npm.cmd --prefix apps/web run lint

# Check code formatting with Prettier
npm.cmd --prefix apps/web run format:check

# Verify Next.js production build
npm.cmd --prefix apps/web run build
```

### Browser End-to-End Verification (Playwright)

```bash
services\api\.venv\Scripts\python services/api/tests/verify_phase5_browser_flow.py
```

### Recognition Quality Benchmark

```bash
docker compose exec api python tests/evaluate_recognition_quality.py
```
"# DexLens" 

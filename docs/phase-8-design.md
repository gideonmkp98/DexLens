# Phase 8: Early Access, Field Validation, and Production Readiness
## Architecture and Technical Design Document

**Date:** November 2, 2026  
**Status:** DRAFT / APPROVED FOR IMPLEMENTATION  
**Project:** DexLens (Pokémon TCG Scanner)  
**Target Environments:** Localhost Dev / Test, Containerized Debian/Alpine Docker, Production (`https://dexlens.studionz.nl`)

---

## 1. Executive Summary & Objective

Phase 8 elevates DexLens from a verified live scanner prototype to a production-grade, early-access pilot application ready for real collectors, Reddit communities, and TCG shop employees and owners.

The primary objective is to obtain empirical field validation:
1. **Recognition Performance:** Measure real-world OCR and candidate accuracy across diverse physical cards, sleeves, lighting, and camera hardware.
2. **Workflow Conversion:** Track whether users prefer Auto-capture vs. Manual-capture vs. File-upload, and whether they confirm and add cards to their collections.
3. **Friction Points:** Detect scan drop-offs, camera permission denials, glare, blur, and candidate corrections.
4. **Data Ownership:** Provide secure session and user ownership ensuring collectors have private, persistent collections with seamless anonymous-to-authenticated data migration.
5. **Operational Resilience:** Maintain strict privacy (zero image or OCR data in telemetry), zero scan-breaking side-effects, rate limiting, and an installable Progressive Web App (PWA) experience.

---

## 2. Architecture & Workstream Division

```
                      +------------------------------------------+
                      |         DexLens Web Client (Next.js)     |
                      |  - Live Scan & Go (Auto/Manual)          |
                      |  - PWA Manifest & Service Worker         |
                      |  - Onboarding Tips & Guidance            |
                      |  - Scan Feedback & Correction Modal      |
                      |  - Pilot Diagnostics Dashboard           |
                      +--------------------+---------------------+
                                           | HTTP / SameSite Cookies
                                           v
                      +------------------------------------------+
                      |       FastAPI Backend (/api/v1)          |
                      |  - Security & Rate-Limiting Middleware   |
                      |  - Session / Auth Dependency Injection   |
                      +----+-------------------+---------------+--+
                           |                   |               |
             +-------------+                   |               +-------------+
             v                                 v                             v
  +--------------------+             +--------------------+        +--------------------+
  |  Auth & Ownership  |             |  Privacy Analytics |        |   Scan Feedback    |
  |  - users           |             |  - allowlisted     |        |  - corrections     |
  |  - user_sessions   |             |    event pipeline  |        |  - reasons         |
  |  - Argon2id hash   |             |  - 30d retention   |        |  - metrics summary |
  |  - collection claim|             |  - zero raw photos |        |  - admin guard     |
  +----------+---------+             +---------+----------+        +---------+----------+
             |                                 |                             |
             +---------------------------------+-----------------------------+
                                               |
                                               v
                             +-----------------------------------+
                             |     MariaDB 11.4 Engine (InnoDB)   |
                             |   Alembic Migration 0014 (Head)   |
                             +-----------------------------------+
```

The work is partitioned into specialized workstreams coordinated by the lead agent:

| Workstream | Focus Domain | Key Artifacts |
|---|---|---|
| **WS1** | Baseline Audit & Verification | Preflight test matrix, environment inspection, design document |
| **WS2** | Users, Sessions & Data Ownership | `User`, `UserSession`, Argon2id auth, `user_id` on collections/scans, session claiming |
| **WS3** | Privacy-Safe Product Analytics | Event dictionary, allowlist validator, `product_analytics_events` table, retention purge |
| **WS4** | Scan Feedback & Diagnostics | `scan_feedback` table, feedback widget, candidate correction tracking, pilot dashboard |
| **WS5** | Security & Operational Hardening | Body limits, rate limiting, security headers, clean error handling, logging |
| **WS6** | PWA & Mobile Scanner Experience | Web app manifest, service worker, offline fallback, scanner onboarding tips |
| **WS7** | Testing, Audit & Phase Readiness | Concurrency, Playwright E2E scenarios, 15-step phase-readiness audit |

---

## 3. Data Models & Migration 0014 Schema

### 3.1 `users`
Represents registered collectors and shop managers.
- `id`: String(36), PK (UUIDv4)
- `email`: String(255), UNIQUE, NOT NULL, INDEX
- `password_hash`: String(255), NOT NULL (Argon2id format)
- `role`: String(32), NOT NULL, DEFAULT `'user'` (`'user'`, `'admin'`, `'pilot'`)
- `is_active`: Boolean, NOT NULL, DEFAULT `True`
- `created_at`: DateTime, NOT NULL
- `updated_at`: DateTime, NOT NULL

### 3.2 `user_sessions`
Represents active browser sessions (both authenticated users and anonymous pilot visitors).
- `id`: String(36), PK (UUIDv4)
- `session_token_hash`: String(64), UNIQUE, NOT NULL, INDEX (SHA-256 of raw cookie token)
- `user_id`: String(36), FK -> `users.id` (ON DELETE CASCADE), NULLABLE, INDEX
- `session_type`: String(16), NOT NULL (`'authenticated'`, `'anonymous'`)
- `expires_at`: DateTime, NOT NULL, INDEX
- `created_at`: DateTime, NOT NULL
- `updated_at`: DateTime, NOT NULL
- `ip_hash`: String(64), NULLABLE (HMAC-SHA256 salt-hashed for anomaly detection without raw IP storage)
- `user_agent`: String(255), NULLABLE

### 3.3 Ownership Extensions to Existing Models
- `collection_items`:
  - `user_id`: String(36), FK -> `users.id` (ON DELETE CASCADE), NULLABLE, INDEX
  - `anonymous_session_id`: String(36), NULLABLE, INDEX
  - Generated `owner_key` (`u:<user_id>` / `a:<anonymous_session_id>` / `legacy`) plus a real unique constraint on `(owner_key, provider, card_id, language, variant, condition)`. Migration 0014 safely merges pre-existing duplicates before enforcing this database invariant.
- `scans` & `scan_sessions`:
  - `user_id`: String(36), FK -> `users.id` (ON DELETE SET NULL), NULLABLE, INDEX
  - `anonymous_session_id`: String(36), NULLABLE, INDEX

### 3.4 `product_analytics_events`
- `id`: String(36), PK (UUIDv4)
- `event_name`: String(64), NOT NULL, INDEX (Strict Allowlist)
- `schema_version`: Integer, NOT NULL, DEFAULT 1
- `actor_type`: String(16), NOT NULL (`'auth'`, `'anon'`)
- `actor_id`: String(64), NOT NULL, INDEX (HMAC-SHA256 pseudonym; raw user/session IDs are never stored in analytics)
- `session_id`: String(64), NULLABLE, INDEX
- `scan_id`: String(36), NULLABLE, INDEX
- `timestamp`: DateTime, NOT NULL, INDEX
- `capture_mode`: String(16), NULLABLE (`'auto'`, `'manual'`, `'upload'`)
- `device_category`: String(32), NULLABLE (`'mobile'`, `'tablet'`, `'desktop'`)
- `browser_category`: String(32), NULLABLE (`'safari_ios'`, `'chrome_android'`, `'chrome_desktop'`, `'firefox'`, `'other'`)
- `viewport_category`: String(16), NULLABLE (`'compact'`, `'standard'`, `'wide'`)
- `processing_duration_ms`: Integer, NULLABLE
- `confidence_state`: String(16), NULLABLE (`'high'`, `'medium'`, `'low'`, `'none'`)
- `candidate_count`: Integer, NULLABLE
- `is_top_suggestion_selected`: Boolean, NULLABLE
- `failure_category`: String(64), NULLABLE
- `metadata_json`: Text, NULLABLE (Sanitized JSON allowlist, <= 2KB)
- `created_at`: DateTime, NOT NULL, INDEX

### 3.5 `scan_feedback`
- `id`: String(36), PK (UUIDv4)
- `scan_id`: String(36), FK -> `scans.id` (ON DELETE CASCADE), NOT NULL, INDEX
- `user_id`: String(36), FK -> `users.id` (ON DELETE CASCADE), NULLABLE, INDEX
- `anonymous_session_id`: String(36), NULLABLE, INDEX
- `feedback_type`: String(32), NOT NULL (`'correct_match'`, `'wrong_card'`, `'in_alternatives'`, `'not_found'`, `'ocr_incorrect'`, `'crop_failed'`, `'too_slow'`, `'other'`)
- `suggested_card_id`: String(100), NULLABLE
- `selected_card_id`: String(100), NULLABLE
- `confidence_state`: String(16), NULLABLE
- `selected_in_candidates`: Boolean, NULLABLE
- `notes`: String(500), NULLABLE
- `device_category`: String(32), NULLABLE
- `created_at`: DateTime, NOT NULL, INDEX
- Generated `owner_key` and idempotency constraint: unique `(scan_id, owner_key)`.

---

## 4. Workstream Implementation Specifications

### 4.1 Workstream 2: Users, Sessions, and Data Ownership
- **Authentication Strategy:**
  - Secure HTTP-only cookies (`dexlens_session`) with `SameSite=Lax`, `Path=/`, and `Secure` (dynamic based on `SECURE_COOKIES` setting).
  - No tokens in `localStorage`.
  - Password hashing via standard `cryptography.hazmat.primitives.kdf.argon2.Argon2id` using recommended RFC 9106 memory/iteration parameters (64MB memory, 3 iterations, 4 parallelism).
  - Constant-time verification preventing email enumeration attacks. Login errors return generic *"Ongeldige inloggegevens"*. Registration returns consistent status.
  - Rate limiting on `/api/v1/auth/login` and `/api/v1/auth/register` (max 10 requests / minute).
- **Anonymous Pilot Mode & Session Claiming:**
  - If a user opens DexLens without logging in, the API automatically provisions an anonymous `user_session`.
  - Scans and collection additions attach to the anonymous session.
  - Registration and login automatically transfer data from the verified anonymous cookie session. The explicit `POST /api/v1/auth/claim-anonymous-session` recovery endpoint additionally requires both the anonymous session ID and its raw token as proof of ownership.
  - Isolation invariant: Collection endpoints (`/api/v1/collection/...`) filter strictly by `(user_id == current_user.id)` or `(anonymous_session_id == current_session.id)`. Non-owned items return 404.

### 4.2 Workstream 3: Privacy-Safe Product Analytics
- **20 Approved Product Events:**
  1. `scan_started`
  2. `camera_permission_granted`
  3. `camera_permission_denied`
  4. `capture_mode_changed`
  5. `auto_capture_triggered`
  6. `manual_capture_triggered`
  7. `upload_started`
  8. `upload_completed`
  9. `scan_processing_started`
  10. `scan_processing_completed`
  11. `scan_processing_failed`
  12. `no_card_detected`
  13. `no_catalog_candidates`
  14. `candidate_list_shown`
  15. `candidate_selected`
  16. `top_candidate_corrected`
  17. `card_confirmed`
  18. `card_added_to_collection`
  19. `scan_abandoned`
  20. `user_feedback_submitted`
- **Privacy & Safety Guarantees:**
  - Client-side helper `trackEvent(name, payload)` wraps `fetch` in `catch(() => {})` or uses `navigator.sendBeacon`. Any network or API failure is 100% swallowed on the client and never disrupts scanning.
  - Server validation rejects unknown event names or payload fields not in the bounded schema.
  - Payload text size strictly bounded (max 2048 bytes).
  - Retention cleanup job deletes analytics older than 30 days (`ANALYTICS_RETENTION_DAYS`).

### 4.3 Workstream 4: Scan Feedback and Diagnostics
- **Scan Feedback Interface:**
  - Integrated into `LiveScanMatchModal` and `apps/web/src/app/scan/[id]/page.tsx` as a compact, collapsible chip: *"Klopt deze kaart?"*.
  - User can tap thumbs up (*"Klopt"*) or options (*"Verkeerde kaart"*, *"Juiste stond in alternatieven"*, *"Niet gevonden"*, etc.).
  - Can be dismissed or skipped with zero friction.
- **Pilot Diagnostics Dashboard (`/pilot-diagnostics`):**
  - Displays aggregated metrics:
    - Total scan sessions & completion rate
    - Recognition success rate & top-candidate acceptance rate
    - Candidate correction rate
    - Processing duration percentiles (median & p95)
    - Auto vs. Manual vs. Upload capture distribution & success
    - Failure categories breakdown
  - Protected by admin session check or `X-Pilot-Admin-Token` header.
  - Exposes zero PII or raw user records.

### 4.4 Workstream 5: Operations, Monitoring & Security
- Rate limiting middleware: Sliding window in-memory limiter for general API (60 req/min/IP) and auth endpoints (10 req/min/IP).
- Exception handlers: Ensure all exceptions output standardized error payloads without traceback or internal server details.
- Health endpoint: `GET /api/v1/health` verifying DB connectivity.

### 4.5 Workstream 6: PWA & Mobile Experience
- Web App Manifest: `manifest.json` configured with standalone mode, `#20251f` theme/background, DexLens branding, icons (192, 512, maskable).
- Service Worker: `public/sw.js` implementing Cache-First/Stale-While-Revalidate for static assets only. Strictly bypasses `/api/*` and dynamic scan uploads.
- First-time Scanner Onboarding:
  - Concise modal explaining card placement in the frame, lighting, reflection reduction, and Auto vs. Handmatig mode.
  - Dismissible and stored in `localStorage` so it does not annoy repeating collectors.

### 4.6 Workstream 7: Testing & Verification
- Comprehensive automated verification across all 15 audit gates.
- Playwright E2E covering authentication, anonymous sessions, session claiming, scan feedback, analytics firing, and PWA manifest presence.

---

## 5. Non-Negotiable Preservations
- Live Scan & Go viewfinder, auto-capture stability tracker, and manual shutter remain primary.
- Upload fallback remains 100% supported.
- Explicit user confirmation is strictly required for catalog matches; heuristic scores are never auto-confirmed.
- DexLens warm visual design language is preserved.

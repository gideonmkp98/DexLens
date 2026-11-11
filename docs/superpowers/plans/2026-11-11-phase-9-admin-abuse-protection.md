# Phase 9: Administration Experience & Adaptive Abuse Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement server-protected admin controls (user management, status transitions, quota overrides, beta codes, append-only audit logging) and adaptive abuse protection with Cloudflare Turnstile managed verification for public registration, invites, and scan bursts.

**Architecture:** 
- Strict server-side authorization on every `/api/v1/admin` endpoint requiring a database-verified admin user session.
- Append-only administrative audit log table sanitizing all metadata (no passwords, tokens, or raw secrets).
- Clean decoupled service interfaces for Beta and Quota management.
- Cloudflare Turnstile integration with server-side Siteverify, action/hostname validation, single-use short-lived replay protection, and trusted proxy IP extraction.
- Adaptive scan abuse detector providing friction-free scans for normal users while challenging suspicious burst patterns and enforcing hard rate limits.
- Modern accessible Next.js admin dashboard (`/admin`) invisible and inaccessible to ordinary users, featuring confirmation modals for risky state changes.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, MariaDB / Alembic, Pydantic v2, Python `cryptography` / `httpx`, Next.js 15, TypeScript, Tailwind CSS.

---

## Global Constraints

- Work only inside the current Git worktree and feature branch `admin_experience_abuse_protection`.
- Never modify or reset main.
- Do not deploy.
- Do not commit secrets, environment files, or production credentials.
- Mark Alembic migration as provisional (`0015_provisional`).
- Never trust client-supplied role or spoofable `X-Forwarded-For` headers.
- Sequential backend test runs only (never run full suite and concurrency suite at the same time).
- Preserve existing scanning, OCR, catalog, and collection functionality.

---

## Review Focus

1. **Role Spoofing & Authorization Bypass:** Ensure ordinary users sending `role: admin` in headers, cookies, or body cannot access any admin endpoint.
2. **Turnstile Replay & Action Mismatch:** Ensure used tokens are immediately rejected if replayed, and tokens generated for "login" or "dummy" cannot be used for "register" or "scan".
3. **Session Invalidation on User Suspension:** Ensure when an admin suspends or blocks a user, all active sessions for that user are immediately invalidated in the database.
4. **IP Spoofing via Headers:** Ensure `X-Forwarded-For` is only honored if the peer IP is explicitly listed in `TRUSTED_PROXY_IPS`.
5. **PII and Secret Leakage in Audit Logs:** Ensure password hashes, session tokens, and sensitive auth data are systematically scrubbed before audit insertion.

---

## Tasks

### Task 1: Database Models & Provisional Alembic Migration
- [ ] Create `AdminAuditLog` model in `services/api/app/models/audit.py`.
- [ ] Create `BetaCode` model in `services/api/app/models/beta.py`.
- [ ] Create `GlobalSetting` model in `services/api/app/models/setting.py`.
- [ ] Extend `User` model in `services/api/app/models/user.py` with `status`, `verification_status`, and `scan_quota_override`.
- [ ] Export new models in `services/api/app/models/__init__.py`.
- [ ] Create provisional Alembic migration `services/api/alembic/versions/0015_provisional_phase9_admin_and_abuse.py`.
- [ ] Run migration and verify tables create cleanly in test and dev databases.

### Task 2: Turnstile & Anti-Abuse Core Services
- [ ] Add Turnstile and Abuse settings in `services/api/app/core/config.py`.
- [ ] Implement `TurnstileService` in `services/api/app/services/turnstile.py` with Siteverify validation, replay detection, and test mode.
- [ ] Implement `ScanAbuseService` in `services/api/app/services/abuse.py` for sliding-window burst tracking and challenge triggers.
- [ ] Implement `AuditService` in `services/api/app/services/audit.py` with safe metadata sanitization.
- [ ] Unit test Turnstile validation, replay prevention, and audit sanitization in `services/api/tests/test_turnstile.py`.

### Task 3: Domain Service Interfaces (Beta & Quotas) & Admin Service
- [ ] Implement `QuotaServiceInterface` and `DefaultQuotaService` in `services/api/app/services/quota_service.py`.
- [ ] Implement `BetaServiceInterface` and `DefaultBetaService` in `services/api/app/services/beta_service.py`.
- [ ] Implement `AdminService` in `services/api/app/services/admin.py` for user lookup, status transitions, and session termination.
- [ ] Unit test service interfaces and admin user transitions in `services/api/tests/test_admin_services.py`.

### Task 4: Backend Admin & Protected API Endpoints
- [ ] Add `require_admin_user` dependency in `services/api/app/api/deps.py`.
- [ ] Implement admin user endpoints (`/api/v1/admin/users`) in `services/api/app/api/v1/admin/users.py`.
- [ ] Implement admin quota endpoints (`/api/v1/admin/settings/quota`) in `services/api/app/api/v1/admin/quotas.py`.
- [ ] Implement admin beta code endpoints (`/api/v1/admin/beta/codes`) in `services/api/app/api/v1/admin/beta.py`.
- [ ] Implement admin audit log endpoints (`/api/v1/admin/audit-logs`) in `services/api/app/api/v1/admin/audit.py`.
- [ ] Implement admin abuse status endpoints (`/api/v1/admin/abuse`) in `services/api/app/api/v1/admin/abuse.py`.
- [ ] Register admin routers in `services/api/app/api/v1/router.py`.
- [ ] Add Turnstile verification to `POST /api/v1/auth/register` and public beta claim endpoints.
- [ ] Integrate adaptive abuse challenge in scan endpoints (`POST /api/v1/scans` and `POST /api/v1/scan-sessions/{id}/capture`).
- [ ] Run backend test suites covering authorization, user state changes, Turnstile validation, and scanning burst protection.

### Task 5: Frontend Admin Experience & Abuse Challenges
- [ ] Add admin API client and types in `apps/web/src/lib/admin.ts`.
- [ ] Build accessible Cloudflare Turnstile component `apps/web/src/components/TurnstileWidget.tsx`.
- [ ] Integrate Turnstile into `apps/web/src/components/AuthModal.tsx` registration tab.
- [ ] Build `apps/web/src/components/ScanChallengeModal.tsx` for recovering from scan challenges.
- [ ] Create `/admin` page and management tabs in `apps/web/src/app/admin/page.tsx`:
  - User lookup, filtering, status badges, and action modals (activate/suspend/block).
  - Quota override modal and global quota settings.
  - Beta code management and revoke confirmation dialogs.
  - Append-only audit log viewer.
  - Server-protection and non-admin access denial view.
- [ ] Update `apps/web/src/components/AppHeader.tsx` to conditionally show the Admin link only for verified admin users.
- [ ] Run frontend typecheck, lint, and formatting.

### Task 6: End-to-End Verification & Commit
- [ ] Run full backend test suite (`pytest -q`).
- [ ] Run dedicated MariaDB concurrency suite sequentially (`pytest tests/test_concurrency_mariadb.py -q`).
- [ ] Run frontend typecheck (`npm run typecheck`).
- [ ] Run frontend linting (`npm run lint`).
- [ ] Review git diff and ensure all files are cleanly formatted with no extraneous changes or secrets.
- [ ] Commit changes to `admin_experience_abuse_protection` branch.
- [ ] Prepare final report covering all 8 required topics.

# Agent Playbook & Operational Rules: Pokémon TCG Scanner

**Scope:** Autonomous Agents, Sub-Agents, and System Engineers working on Pokémon TCG Scanner
**Referenced Skill:** `.agents/skills/phase-readiness-audit/SKILL.md`
**Status:** MANDATORY OPERATIONAL POLICY

---

## 1. Core Operating Principles

1. **Evidence Before Assertions:** Never claim a test passes, a build succeeds, or a bug is resolved without executing the verification command and inspecting output.
2. **Preserve Uncommitted Changes:** The working tree contains ongoing work across phases. Never perform hard resets (`git reset --hard`, `git checkout .`) or discard uncommitted edits.
3. **Reactive Notification Handling:** Never poll `manage_task(Action='status')` in a tight loop. Let the messaging system wake the agent upon task completion.

---

## 2. Windows Host & PowerShell Specifics

- **Node/NPM Invocations:**
  Always use `npm.cmd` and `npx.cmd`. Using raw `npm` or `npx` invokes `npm.ps1`, which triggers PowerShell script execution policy errors.
- **Bracketed Routes:**
  Next.js uses paths like `apps/web/src/app/cards/[id]/page.tsx`. PowerShell treats brackets as character-set wildcards. Always use `-LiteralPath` for path cmdlets:
  ```powershell
  Get-Content -LiteralPath "apps/web/src/app/cards/[id]/page.tsx"
  ```
- **Cross-Platform Commands:**
  Do not run Linux-specific bash utilities (`sed -i`, `grep`, `export`) on the Windows host. Run them inside Docker containers using `docker compose exec`.

---

## 3. Database Safety & Test Isolation

- **Test Database Isolation:**
  Automated tests (Pytest, isolated E2E) must only execute against a database ending in `_test` (`tcg_test`).
- **Destructive Operation Safety Guard:**
  Any destructive bulk reset or table drop endpoint (`POST /api/v1/testing/reset`) strictly checks `db_name.endswith("_test")` and rejects requests against non-test databases with HTTP 403 Forbidden.
- **Scoped Test Cleanups:**
  When testing against persistent environments, cleanups must be scoped strictly to test-generated fixture IDs (`TEST_CARD_IDS`), preventing data loss in development catalogs.

---

## 4. Concurrency & Data Integrity

- **Database-Atomic Optimistic Concurrency:**
  Updates to collection items must use database-atomic conditional queries:
  ```sql
  UPDATE collection_items
  SET ..., version = version + 1
  WHERE id = :id AND version = :expected_version
  ```
  A row count of 0 must be checked to distinguish HTTP 404 (missing item) from HTTP 409 (`VERSION_CONFLICT`). `expected_version` is mandatory.
- **Grouping Unique Constraints:**
  `uq_collection_items_grouping` on `(provider, card_id, language, variant, condition)` prevents duplicate physical rows. Concurrent insert races must catch `IntegrityError` (1062) and merge into the existing row gracefully.

---

## 5. Artifact Hygiene & Build Readiness

- **Ignore Hygiene:**
  Ensure all test outputs (`test-results/`, `playwright-report/`) and build outputs (`.next/`, `*.tsbuildinfo`) are registered in `.gitignore` and `apps/web/.prettierignore` to prevent linter errors and repository bloat.
- **Next.js Standalone Mode:**
  `sharp` must be listed in `dependencies` in `apps/web/package.json` so it is preserved in standalone Docker production builds.

---

## 6. Phase Audit Execution

Before declaring readiness or advancing between phases:
1. Invoke the audit protocol defined in `.agents/skills/phase-readiness-audit/SKILL.md`.
2. Execute all 16 verification gates sequentially.
3. Record exact outputs and command exit codes in the phase readiness report.

---

## 7. Live Camera & Scan Sessions Architecture (Phase 7)

- **Browser-First Camera Management:**
  `useCamera` encapsulates `navigator.mediaDevices.getUserMedia` with mobile rear camera preference (`facingMode: { ideal: "environment" }`), device switching, and torch toggling.
  On unmount, navigation, or error, every active `MediaStreamTrack` MUST be explicitly stopped via `track.stop()`.
- **Client-Side Offscreen Quality Engine:**
  Frame analysis operates on a 320×240 offscreen canvas every 180ms (~5-6 FPS) to conserve CPU. Frames are evaluated against BT.601 luminance (exposure), specular glare ratio, $3 \times 3$ Laplacian kernel sharpness, and motion MAD before triggering server upload.
- **Single-Roundtrip Server Execution:**
  `POST /api/v1/scan-sessions/{session_id}/capture` accepts a multipart image frame and executes automatic OpenCV card detection, perspective warp, local OCR, and catalog candidate ranking in a single roundtrip, returning `LiveCaptureResponse`.
- **Continuous Multi-Card Sessions:**
  `scan_sessions` table (Alembic `0011`) tracks active scanning sessions. *"Volgende kaart scannen"* rearms the camera viewfinder instantly without navigation or session re-creation.

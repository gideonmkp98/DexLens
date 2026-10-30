# Operational Memory & Process Guide: Pokémon TCG Scanner

**Target Audience:** AI Agents (Phases 6, 7, and beyond), Autonomous Sub-Agents, and System Engineers
**Date Established:** October 30, 2026
**Status:** ACTIVE & MANDATORY REFERENCE

---

## 1. Purpose & Scope

This guide captures hard-won operational memory, system-level stumbling blocks, and non-obvious tooling edge cases identified across Phases 4, 5, and 6 of the Pokémon TCG Scanner project.

The project operates in a hybrid environment:
- **Host OS:** Windows (PowerShell 5/7)
- **Container Environment:** Linux containers (Debian-slim for Python API, Alpine Linux for Next.js web runtime, MariaDB 11.4)
- **Networking:** Localhost browser access vs. internal Docker container service networking (`http://api:8000`, `mariadb:3306`)
- **State Engines:** Persistent MariaDB dev database (`tcg_db`), isolated Pytest database (`tcg_test`), and local disk uploads (`/app/uploads`)

Future agents—especially those implementing Phase 7—**must read and adhere to these guidelines** to prevent recurring failures, broken builds, test contamination, and context window exhaustion.

---

## 2. Windows PowerShell Tooling & Cross-Platform Ergonomics

### 2.1 The `npm.cmd` and `npx.cmd` Requirement
- **The Stumbling Block:**
  On Windows systems, running `npm` or `npx` directly resolves to `npm.ps1` or `npx.ps1`. If PowerShell's execution policy prohibits running unsigned scripts (e.g. `Restricted` or default enterprise policies), commands fail immediately with:
  ```text
  File C:\Program Files\nodejs\npm.ps1 cannot be loaded because running scripts is disabled on this system.
  ```
- **The Permanent Rule:**
  **Always invoke `npm.cmd` and `npx.cmd` explicitly** when executing Node/npm commands in PowerShell.
  ```powershell
  # CORRECT
  npm.cmd run build
  npm.cmd run typecheck
  npm.cmd run lint
  npm.cmd run format:check
  npm.cmd run test:e2e
  npx.cmd playwright test

  # INCORRECT (Will fail if execution policies are restricted)
  npm run build
  npx playwright test
  ```

---

### 2.2 Dynamic Next.js Routes and PowerShell `-LiteralPath`
- **The Stumbling Block:**
  Next.js App Router uses square brackets for dynamic routes (e.g., `apps/web/src/app/cards/[id]/page.tsx` and `apps/web/src/app/scan/[id]/page.tsx`).
  PowerShell treats square brackets `[` and `]` as wildcard regex characters (character sets). When using cmdlets such as `Select-String`, `Get-ChildItem`, `Get-Content`, or `Test-Path` with `-Path`, PowerShell fails with:
  ```text
  Cannot find path '...apps\web\src\app\cards\[id]\page.tsx' because it does not exist.
  ```
- **The Permanent Rule:**
  **Always use `-LiteralPath` instead of `-Path`** whenever querying or manipulating file paths that may contain `[id]` or other bracketed segments.
  ```powershell
  # CORRECT
  Select-String -LiteralPath "apps/web/src/app/cards/[id]/page.tsx" -Pattern "AddToCollection"
  Get-Content -LiteralPath "apps/web/src/app/scan/[id]/page.tsx"
  Test-Path -LiteralPath "apps/web/src/app/cards/[id]/page.tsx"

  # INCORRECT (PowerShell expands [id] as wildcard matching 'i' or 'd')
  Select-String -Path "apps/web/src/app/cards/[id]/page.tsx" -Pattern "AddToCollection"
  ```

---

### 2.3 Avoiding Unix Bash Utilities on Windows Host
- **The Stumbling Block:**
  Agents often assume a bash environment and attempt to run Unix utilities (`grep`, `sed`, `awk`, `export`, `rm -rf`, `which`, `head`, `tail`) directly in the host shell. On Windows, these commands either do not exist or map to PowerShell aliases with incompatible parameter syntax.
- **The Permanent Rule:**
  Use native PowerShell cmdlets or short cross-platform Python one-liners on the host. When Unix utilities are required (e.g. `sed -i` on shell scripts), execute them inside the appropriate Docker container.

  | Action | Unix / Bash (Avoid on Host) | Windows PowerShell (Use This) |
  |---|---|---|
  | Set env variable | `export FOO=bar` | `$env:FOO = "bar"` |
  | Search text | `grep -rn "term" src/` | `Select-String -Path "src\*" -Pattern "term"` |
  | Remove directory | `rm -rf dir` | `Remove-Item -Recurse -Force -LiteralPath "dir"` |
  | View first N lines | `head -n 20 file.txt` | `Get-Content -LiteralPath "file.txt" -TotalCount 20` |
  | Find files | `find . -name "*.tsx"` | `Get-ChildItem -Recurse -Filter "*.tsx"` |
  | Test port / URL | `curl -f http://...` | `Invoke-WebRequest -Uri "http://..." -UseBasicParsing` |
  | In-place edit / Sed | `sed -i 's/a/b/' file.sh` | Run via `docker exec` or Python script |

---

### 2.4 CRLF vs. LF Line Endings for Shell Entrypoints
- **The Stumbling Block:**
  Git on Windows checkouts often converts `LF` to `CRLF` (`\r\n`). When a shell script (`entrypoint.sh`) with CRLF line endings is executed inside a Linux Docker container, Linux `/bin/sh` fails with:
  ```text
  exec /app/entrypoint.sh: no such file or directory
  # or
  /app/entrypoint.sh: line 2: $'\r': command not found
  ```
  Furthermore, host volume bind-mounts (`./services/api:/app` in `docker-compose.dev.yml`) overlay the host's CRLF file directly over any normalized file baked into the Docker image!
- **The Permanent Safeguards:**
  1. `.gitattributes` enforces LF in git:
     ```gitattributes
     *.sh text eol=lf
     ```
  2. `services/api/Dockerfile` normalizes line endings during build:
     ```dockerfile
     RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh
     ```
  3. `docker-compose.dev.yml` defensively normalizes line endings at container startup before executing:
     ```yaml
     entrypoint:
       - /bin/sh
       - -c
       - |
         sed -i 's/\r$//' /app/entrypoint.sh
         exec /app/entrypoint.sh "$$@"
       - --
     ```

---

## 3. Long-Running Async Commands & Reactive Agent Notifications

### 3.1 The Anti-Pattern: Tight Polling Loops
- **The Stumbling Block:**
  When a command runs longer than `WaitMsBeforeAsync`, the agent execution environment automatically spins it off into a background task (e.g. `task-72`).
  Inexperienced agents repeatedly invoke `manage_task(Action='status')` or run sleep loops. This wastes thousands of context tokens, inflates turn counts, and adds zero value.
- **The Permanent Rule:**
  **Never poll `manage_task(Action='status')` in a loop.**
  The agent messaging framework automatically sends a push notification message (`priority=MESSAGE_PRIORITY_HIGH`) to the agent context as soon as the background task finishes.
- **Protocol:**
  1. Launch command with appropriate `WaitMsBeforeAsync` (e.g., 5000 to 10000ms for quick checks, or let it transition to background).
  2. If the tool reports that it is running as a background task, **stop calling tools immediately and end your turn**.
  3. Wait for the reactive wakeup message containing the task output and exit code.
  4. If waiting for multiple external jobs or needing a hard timeout, use the `schedule` tool with `TimerCondition=<task_id>` rather than host sleep commands.

---

## 4. Test Environment State Contamination & Isolation

### 4.1 Playwright E2E Test State Contamination
- **The Stumbling Block:**
  Playwright end-to-end tests run against the live development container environment (`localhost:3000` -> `api:8000` -> `tcg_db`).
  In Phase 6, tests added physical cards (e.g. Pikachu `base1-58` or Blastoise `base1-2`) to the collection. When tests were run a second time without database cleanup:
  - Pikachu already existed with `quantity = 2`.
  - The new scan triggered `add_from_scan`, which merged into the existing row, setting `quantity = 3`.
  - The UI test incremented the count to `4` and asserted `toContainText("×2")`.
  - The assertion failed, reporting `×4` instead of `×2`.
- **The Permanent Rule:**
  **Every E2E test file that mutates server state must declare explicit isolation cleanup hooks in `test.beforeEach` and `test.afterEach`.**
- **The Canonical Isolation Pattern (`apps/web/e2e/collection-flow.spec.ts`):**
  ```typescript
  import { test, expect, type APIRequestContext } from "@playwright/test";

  const TEST_CARD_IDS = new Set(["base1-58", "base1-2"]);

  async function cleanupTestCards(request: APIRequestContext) {
    try {
      const idsToDelete: string[] = [];
      let page = 1;
      let hasMore = true;

      while (hasMore) {
        const res = await request.get(`/api/v1/collection?page=${page}&page_size=100`);
        if (!res.ok()) break;
        const data = await res.json();
        const items = (data.items || []) as Array<{ id: string; card_id: string }>;
        for (const item of items) {
          if (TEST_CARD_IDS.has(item.card_id)) {
            idsToDelete.push(item.id);
          }
        }
        hasMore = data.has_more ?? false;
        page++;
      }

      for (const id of idsToDelete) {
        await request.delete(`/api/v1/collection/${id}`);
      }
    } catch (err) {
      console.warn("Failed to clean up test cards:", err);
    }
  }

  test.describe("Collection E2E Tests", () => {
    test.beforeEach(async ({ request }) => {
      await cleanupTestCards(request);
    });

    test.afterEach(async ({ request }) => {
      await cleanupTestCards(request);
    });

    // ... tests ...
  });
  ```

---

### 4.2 Pytest MariaDB Database Isolation & Foreign Key Teardown
- **The Stumbling Block:**
  Pytest runs against a dedicated test database (`tcg_test`). However, MariaDB behaves differently from SQLite:
  1. **Foreign Key Drop Order:** When tearing down metadata (`Base.metadata.drop_all`), MariaDB raises error `1451: Cannot delete or update a parent row: a foreign key constraint fails` if table dependencies (e.g. `collection_scan_links` referencing `scans`) are dropped out of order or if active connection pool handles hold metadata locks.
  2. **Active Pool Disposal:** Calling `test_engine.dispose()` closes all open connections before schema-wide drops.
  3. **Foreign Key Check Disabling:** In MariaDB/MySQL test fixtures, setting `SET FOREIGN_KEY_CHECKS = 0` during teardown ensures reliable session cleanup without deadlocks:
     ```python
     with test_engine.connect() as conn:
         conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
         Base.metadata.drop_all(bind=conn)
         conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
         conn.commit()
     ```
  4. **Relationship Cascade Configuration:** Any model with a foreign key back-reference to `scans` or `collection_items` must specify `passive_deletes=True` or ORM cascade rules to match the SQL DDL `ON DELETE CASCADE` / `ON DELETE SET NULL`.

---

## 5. Linter & Prettier Ignore Hygiene for Generated Artifacts

### 5.1 The Stumbling Block: Generated Artifact Contamination
- Running Playwright creates `apps/web/test-results/` and `apps/web/playwright-report/` (containing bundled HTML, JSON traces, and screenshots).
- Next.js builds create `.next/`, `out/`, and `tsconfig.tsbuildinfo`.
- Pytest creates `.pytest_cache/` and `.coverage`.
- If these directories are omitted from `.gitignore`:
  - `git status` shows thousands of untracked files.
  - Agents risk committing multi-megabyte binary artifacts.
- If omitted from `.prettierignore`:
  - Running `npm.cmd run format:check` scans minified files in `playwright-report` and `test-results`, throwing formatting errors or exhausting heap memory.

### 5.2 The Permanent Rule
**Every generated output directory must be registered in both `.gitignore` AND `apps/web/.prettierignore`.**

#### Check: Root `.gitignore`
```gitignore
# Test & coverage outputs
test-results/
playwright-report/
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Build outputs
.next/
out/
build/
dist/
*.tsbuildinfo
```

#### Check: `apps/web/.prettierignore`
```prettierignore
node_modules
.next
out
build
dist
test-results
playwright-report
```

---

## 6. Next.js Standalone Build & Image Optimization Runtime Requirements

### 6.1 The Stumbling Block: `sharp` in Alpine Linux Standalone Containers
- In `apps/web/next.config.mjs`, `output: "standalone"` is enabled to output a production server folder (`.next/standalone`) that can be executed directly with `node server.js`.
- Next.js uses `sharp` for native image transformation (`<Image />`).
- If `sharp` is placed in `devDependencies`, production builds (`npm install --omit=dev`) or multi-stage Docker builds discard it.
- In Alpine Linux (`node:20-alpine`), standard glibc binaries fail; Alpine requires musl libc bindings (`@img/sharp-linux-musl-x64`).
- Missing `sharp` causes Next.js to log runtime warnings:
  ```text
  Image Optimization using Next.js default loader is not compatible with standalone mode. Please install sharp or customize your loader.
  ```
  Card image resizing degrades, and card scan slabs experience higher latency and CPU usage.

### 6.2 The Permanent Rule
1. **Always declare `sharp` in `dependencies` (production dependencies) in `apps/web/package.json`**:
   ```json
   "dependencies": {
     "next": "^14.2.35",
     "react": "^18.3.1",
     "react-dom": "^18.3.1",
     "sharp": "^0.35.5"
   }
   ```
2. Verify standalone production builds locally:
   ```powershell
   npm.cmd run build
   ```
   Confirm that `.next/standalone` is generated and that `apps/web/public` and `.next/static` are copied as expected by the Docker production runner.

---

## 7. Database Migration Continuity & Schema Synchronization

### 7.1 The Stumbling Block: Migration Drift and Orphaned Heads
- Alembic tracks migrations sequentially via revision hashes in `services/api/alembic/versions/`.
- Recurring risks:
  1. A migration file is added to `alembic/versions/` but never applied to the running MariaDB container (`alembic upgrade head`).
  2. Multiple sub-agents generate migrations from the same base revision, creating multiple branching heads without a merge revision (`alembic heads` showing 2+ revisions).
  3. Readiness reports document an old revision (e.g. `0008`) while the code has advanced to `0009`.
  4. SQLAlchemy models define columns or constraints not yet reflected in the Alembic revision.

### 7.2 The Permanent Rules for Database Changes
1. **The Verification Gate:**
   Always run both commands and confirm that exactly ONE revision is returned, and that `current` matches `heads`:
   ```powershell
   docker exec tcg_api alembic current
   docker exec tcg_api alembic heads
   ```
2. **Bidirectional Migration Testing:**
   Never consider a database migration task complete until both upgrade and downgrade have been tested against MariaDB:
   ```powershell
   docker exec tcg_api alembic downgrade -1
   docker exec tcg_api alembic upgrade head
   ```
3. **Model & Migration Parity:**
   Verify that all columns, check constraints, indexes, and foreign keys in `services/api/app/models/*.py` match the `op.create_table` or `op.add_column` calls in the migration file.
4. **Container Boot Automation:**
   `services/api/entrypoint.sh` must always run `alembic upgrade head` before launching `uvicorn`, guaranteeing that all environments automatically apply pending migrations upon startup.

---

## 8. Summary: Quick Preflight Checklist for Future Phases (Phase 7+)

Before starting or completing any development increment, run this checklist:

```markdown
### Preflight Operational Checklist
- [ ] Windows PowerShell Commands:
  - Invoked `npm.cmd` and `npx.cmd` (not bare `npm`/`npx`).
  - Used `-LiteralPath` for all paths containing `[id]` (e.g. `cards/[id]/page.tsx`).
  - No Unix bash commands (`grep`, `sed`, `rm -rf`) executed on the Windows host.
- [ ] Async Commands & Agent Flow:
  - No tight polling loops on `manage_task(Action='status')`.
  - Let reactive background task notifications wake the agent.
- [ ] Test Isolation:
  - Playwright E2E tests include `beforeEach` and `afterEach` data cleanup hooks.
  - MariaDB test database (`tcg_test`) runs with proper FK cascade and teardown disposal.
- [ ] Linter & Prettier Hygiene:
  - `playwright-report` and `test-results` are in `.gitignore` and `.prettierignore`.
  - `npm.cmd run format:check` and `npm.cmd run lint` pass cleanly.
- [ ] Next.js Standalone Build:
  - `sharp` is listed in `dependencies` in `apps/web/package.json`.
  - `npm.cmd run build` succeeds with standalone output.
- [ ] Database Migrations:
  - `docker exec tcg_api alembic current` matches `docker exec tcg_api alembic heads`.
  - Tested both `alembic downgrade -1` and `alembic upgrade head`.
  - All uncommitted changes preserved.
```

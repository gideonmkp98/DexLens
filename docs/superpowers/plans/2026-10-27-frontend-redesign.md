# DexLens Frontend Redesign Implementation Plan

**Goal:** Transform the Pokémon TCG scanner frontend from an internal developer dashboard into **DexLens**, a modern, collector-focused consumer web application with mobile-first navigation, sleek card visual language, and preserved scanning & catalog features.

**Architecture:**
- Next.js 14 (App Router) + Tailwind CSS + TypeScript.
- Client-side navigation (`AppHeader` for desktop, `MobileNavigation` bottom bar for mobile).
- Reusable UI component layer: `CardTile`, `CardImage`, `EmptyState`, `LoadingSkeleton`, `SectionHeader`, `PageContainer`, `ViewfinderFrame`.
- Centralized API layer: `@/lib/api.ts` (unchanged backend contracts).

**Tech Stack:** Next.js 14.2, React 18, Tailwind CSS, TypeScript 5.

---

## Task Decomposition

### Task 1: Design Tokens, Global CSS & Layout Chrome
- **Files**:
  - `apps/web/src/app/globals.css`
  - `apps/web/tailwind.config.ts`
  - `apps/web/src/app/layout.tsx`
  - `apps/web/src/components/AppHeader.tsx` (new)
  - `apps/web/src/components/MobileNavigation.tsx` (new)
  - `apps/web/src/components/Footer.tsx` (new)
- **Goal**: Establish the obsidian/indigo dark mode, clean light mode, responsive header, sticky mobile bottom navigation, and consumer footer.
- **Verification**: `npm.cmd run typecheck --prefix apps/web` and `npm.cmd run build --prefix apps/web`.

### Task 2: Core Visual Components (CardTile, Skeleton, EmptyState)
- **Files**:
  - `apps/web/src/components/CardImage.tsx` (refactored with shine & badge support)
  - `apps/web/src/components/CardTile.tsx` (new consumer card display component)
  - `apps/web/src/components/LoadingSkeleton.tsx` (new reusable skeleton loaders)
  - `apps/web/src/components/EmptyState.tsx` (new consumer empty state component)
- **Goal**: Create standard building blocks used across Home, Cards, Sets, and Scanner pages.
- **Verification**: `npm.cmd run typecheck --prefix apps/web`.

### Task 3: Public Consumer Landing Page & Relocate Health Monitor
- **Files**:
  - `apps/web/src/app/page.tsx` (redesigned consumer homepage: Hero, Quick-Scan dropzone, Featured Cards, Popular Sets, Value Props)
  - `apps/web/src/app/debug/page.tsx` (new dedicated page preserving the original API & Database health monitor)
- **Goal**: Replace the single health box on `/` with a vibrant public landing page while preserving health monitoring on `/debug`.
- **Verification**: `npm.cmd run build --prefix apps/web`.

### Task 4: Consumer Card Scanner Experience (`/scan`)
- **Files**:
  - `apps/web/src/app/scan/page.tsx`
  - `apps/web/src/components/ViewfinderGuide.tsx` (new card framing guide)
- **Goal**: Build a mobile-optimized camera/upload experience with card-shaped viewfinder, drag-and-drop, instant file preview, and friendly validation error messages.
- **Verification**: `npm.cmd run typecheck --prefix apps/web`.

### Task 5: Consumer Scan Result & Candidate Selection (`/scan/[id]`)
- **Files**:
  - `apps/web/src/app/scan/[id]/page.tsx`
  - `apps/web/src/components/CornerSelector.tsx` (refactored with English consumer labels and clean handles)
- **Goal**: Redesign the scan result to prioritize card artwork, recognized card details, and candidate cards, moving technical OCR logs into a collapsible diagnostics drawer.
- **Verification**: `npm.cmd run build --prefix apps/web`.

### Task 6: Card Catalog Discovery & Detail Redesign (`/cards` and `/cards/[id]`)
- **Files**:
  - `apps/web/src/app/cards/page.tsx` (2-col mobile / multi-col desktop visual card grid, sticky search bar)
  - `apps/web/src/app/cards/[id]/page.tsx` (collector-grade showcase, large artwork, attacks/abilities, future market value placeholders)
- **Goal**: Deliver a consumer-first card browsing and detail experience.
- **Verification**: `npm.cmd run build --prefix apps/web`.

### Task 7: Sets Explorer & Detail Redesign (`/sets` and `/sets/[id]`)
- **Files**:
  - `apps/web/src/app/sets/page.tsx`
  - `apps/web/src/app/sets/[id]/page.tsx`
- **Goal**: Visual set browsing with set logos, release dates, card count progress indicators, and integrated card grids.
- **Verification**: `npm.cmd run build --prefix apps/web`.

### Task 8: Responsive Verification, Accessibility & Build Check
- **Actions**:
  - Verify layout at 375px, 430px, 768px, 1024px, and 1440px.
  - Check keyboard accessibility and contrast.
  - Run full production build: `npm.cmd run build --prefix apps/web`.

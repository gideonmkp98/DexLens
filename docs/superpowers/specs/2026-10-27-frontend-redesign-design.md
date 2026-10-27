# DexLens — Frontend Redesign Specification

- **Date**: 2026-10-27
- **Target Branch**: master
- **Status**: Approved for Implementation

---

## 1. Executive Summary

Transform the `tgc-scanner` web frontend from an internal developer/admin dashboard into **DexLens**, a modern, high-polish, public-facing web application built for Pokémon TCG collectors and casual hobbyists. The visual identity adopts a collectible card aesthetic (dark obsidian & porcelain neutral foundations, electric indigo/violet accents, holographic card highlights, tactile elevation) while keeping the existing FastAPI backend, OCR scanner logic, and database intact.

---

## 2. Branding & Visual Direction

### 2.1 Brand Identity
- **Product Name**: **DexLens** (easily configurable via a central constants file).
- **Tagline**: *"Scan. Identify. Collect."*
- **Legal & IP Boundary**: Zero official Pokémon logos, copyrighted characters, or direct brand imitation. Card scans and external card images loaded from catalog CDNs remain displayed cleanly where supported.
- **Tone**: Modern, collectible-focused, energetic, premium, slightly playful, fast, and mobile-first.

### 2.2 Color Palette & Design Tokens
- **Dark Mode (Default/Primary for Collectors)**:
  - Background Base: `#080c14` (Obsidian depth)
  - Surface Card: `#0f172a` / `#131c2e` with subtle borders (`rgba(255, 255, 255, 0.08)`)
  - Accent Electric: Indigo & Violet (`#6366f1` / `#8b5cf6` with subtle gradients)
  - Secondary Accents: Emerald (`#10b981`) for confirmed/high-confidence, Amber (`#f59e0b`) for pending/adjust, Rose (`#f43f5e`) for errors.
- **Light Mode**:
  - Background Base: `#f8fafc` / `#f1f5f9`
  - Surface Card: `#ffffff` with subtle borders (`#e2e8f0`)
  - Accent: Vibrant Indigo (`#4f46e5`)
- **Card Artwork Treatment**:
  - Aspect ratio: standard 2.5/3.5 standard TCG ratio
  - Rounded corners: `rounded-xl`
  - Soft ambient shadows (`shadow-md shadow-indigo-950/20`), smooth hover lift (`hover:-translate-y-1 hover:shadow-xl transition-all duration-200`)
- **Typography**:
  - Expressive modern sans (`Inter` / system-ui sans-serif font stack)
  - Clear visual hierarchy with compact labels, punchy headings, and bold tabular numbers.

---

## 3. Navigation Architecture

### 3.1 Mobile Navigation (`MobileNavigation`)
- Sticky bottom navigation bar (fixed bottom-0, safe-area padded):
  - **Home** (icon + label) → `/`
  - **Explore** (cards & sets) → `/cards`
  - **Scan** (elevated center floating action button with vibrant gradient background and scan icon) → `/scan`
  - **Sets** (set explorer) → `/sets`
  - **Saved / Collection** (folder/bookmark icon with "Soon" chip) → future-ready preview

### 3.2 Desktop Navigation (`AppHeader`)
- Sticky top navigation bar (`backdrop-blur-md bg-white/90 dark:bg-[#080c14]/90 border-b border-slate-200/80 dark:border-slate-800/80`):
  - Brand Logo & Title: **DexLens** with an electric card emblem
  - Navigation links:
    - **Scan** (with prominent pill CTA styling)
    - **Explore Cards**
    - **Sets**
    - **Collection** (with subtle "Preview/Soon" badge)
  - Quick Search input / search shortcut
  - Theme Toggle (Dark / Light)
  - Discreet Diagnostics / Debug link (subtle icon in header or footer linking to `/debug`)

---

## 4. Page-by-Page Specifications

### 4.1 Home Page (`/`)
- **Hero Section**:
  - Eyebrow chip: `Collector-Grade Card Scanner`
  - Headline: `Scan. Identify. Collect.`
  - Subhead: `Instantly identify any Pokémon card with high-speed camera scanning, track set checklists, and discover cards in seconds.`
  - Dual CTAs:
    - Primary: `Start Free Scan` (links to `/scan`)
    - Secondary: `Explore Catalog` (links to `/cards`)
- **Quick-Scan Dropzone Card**:
  - Interactive hero drop/upload card directly on the homepage so users can drop a photo or click to scan without leaving the landing page.
- **Trending / Featured Cards Section**:
  - Real cards fetched live via `getCards({ page_size: 8 })`.
  - Visual card grid displaying real card art, card name, set name, and card number.
- **Popular Sets Section**:
  - Real sets fetched via `getSets({ page_size: 6 })` displaying set logo/symbol, total cards, and release date.
- **Product Benefits (3 Clean Pillars)**:
  - ⚡ *Instant Identification*: Advanced neural OCR trained on card titles, numbers, and set icons.
  - 🗂️ *Complete Catalog*: Browse sets, variants, rarities, and card details.
  - 💎 *Collector-Ready*: Built for deck builders, binders, and future portfolio tracking.
- **Future Feature Preview Banner**:
  - Discreet teaser for market values, price history, and digital binder sync (no fake stats, clearly marked upcoming features).

### 4.2 Scanner Upload Page (`/scan`)
- Dedicated, distraction-free scan experience.
- Mobile camera viewport guide with card-shaped dashed bounding box overlay: *"Align card inside the frame"*.
- Actions:
  - Direct file upload / mobile camera button: *"Take Photo or Choose File"*
  - Drag-and-drop zone with instant local image preview upon selection.
  - Format badges: JPEG, PNG, WebP (up to 15MB).
  - Clear loading spinner with informative step message (*"Uploading & preparing image..."*).

### 4.3 Scan Result & Verification Page (`/scan/[id]`)
- **Hero Card Presentation**:
  - Primary focus: Cropped card artwork displayed prominently alongside the match result.
  - Match Card Badge: Confirmed card name, set, number, and confidence state (e.g., `High Confidence Match`).
  - Candidate Carousel / List: If multiple candidates match, display selectable card tiles with clear visual selection state.
  - Primary Actions:
    - `View in Catalog` → `/cards/[card_id]`
    - `Scan Another Card` → `/scan`
    - `Adjust Crop Corners` → opens the perspective adjustment modal/panel.
- **Crop Adjustment Mode**:
  - Preserves full existing corner-adjustment functionality (`CornerSelector`) with clean, consumer-friendly labels (Top-Left, Top-Right, Bottom-Right, Bottom-Left).
- **Diagnostics Accordion (Collapsible)**:
  - Technical OCR raw text, candidate scores, internal IDs, and image quality warnings tucked neatly inside a collapsed `Developer / Scan Diagnostics` drawer so normal users see a sleek result while developers can still debug.

### 4.4 Card Catalog & Search Page (`/cards`)
- Sticky search and filter bar:
  - Card name search input (debounced or search button).
  - Card number input.
  - Set selector dropdown.
  - Reset filters button.
- Responsive Card Grid:
  - Mobile: 2 columns with optimized aspect ratio and clear typography.
  - Tablet: 3-4 columns.
  - Desktop: 4-6 columns.
- State handling:
  - Skeleton cards during loading.
  - Friendly empty state when no cards match filters (*"No cards found matching your search. Try adjusting your filters."*).
  - Pagination controls with current page and previous/next buttons.

### 4.5 Card Detail Page (`/cards/[id]`)
- Two-column responsive layout (single-column mobile):
  - **Left**: Large interactive card artwork with subtle holographic sheen container and high-res image zoom.
  - **Right**:
    - Card Title, Local ID, Set Name (linking to set), Rarity badge, Type & HP pills.
    - Attacks & Abilities: Card attack rows with energy cost badges, damage points, and rule text.
    - Collector Metadata: Illustrator credit, regulation mark, available print variants (Holo, Reverse Holo, Normal).
    - Future-ready Collector Action Bar:
      - `Add to Collection` (interactive preview modal explaining feature coming soon)
      - `Track Market Value` (preview placeholder for future price tracking)

### 4.6 Sets Directory & Detail Pages (`/sets` and `/sets/[id]`)
- `/sets`: Clean grid of card sets with set symbol, set logo, card count progress, and release date badge.
- `/sets/[id]`: Set hero banner with logo, set statistics, and an integrated card grid of all cards in that set.

### 4.7 Dedicated Health / Debug Page (`/debug`)
- Relocates the previous root health monitor (`getHealth()`) into `/debug`.
- Displays real-time API connectivity, MariaDB database status, timestamp, and refresh button.

---

## 5. Responsive Design Targets
- **375px** (iPhone SE): Single column layouts, 2-column card grid, accessible 44px+ tap targets, bottom navigation bar.
- **430px** (iPhone Pro Max): Comfortable padding, full-width card previews.
- **768px** (iPad / Tablet): 3-column card grid, side-by-side card detail preview.
- **1024px** (Desktop): Multi-column card catalog (4-5 cols), full desktop header.
- **1440px** (Widescreen): Max-width constraints (`max-w-7xl`), centered layouts, no stretched content.

---

## 6. Preserved Functionality & Zero-Regression Verification
- Corner dragging and perspective crop (`detectCard`, `cropScan`, `confirmCrop`).
- OCR trigger and candidate confirmation (`recognizeCard`, `searchCardCandidates`, `confirmCatalogCard`, `resetCatalogCardConfirmation`).
- Catalog search, pagination, and set filtering.
- Dark mode toggle with persistent local storage.
- Backend health verification.

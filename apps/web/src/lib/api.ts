export interface HealthResponse {
  status: "ok" | "degraded" | "disconnected" | string;
  database: "connected" | "disconnected" | string;
}

export interface SetSummary {
  id?: string | number | null;
  source?: string;
  external_id: string;
  name: string;
  language?: string;
  series?: string | null;
  logo_url?: string | null;
  symbol_url?: string | null;
  release_date?: string | null;
  printed_total?: number | null;
  total?: number | null;
  card_count: number;
  local_card_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SetDetail extends SetSummary {}

export interface PaginatedSetsResponse {
  items: SetSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more?: boolean;
}

export interface CardSetBrief {
  id?: string | number | null;
  external_id: string;
  name: string;
}

export interface CardListItem {
  id?: string | number | null;
  source?: string;
  external_id: string;
  set_id: string;
  local_id: string;
  name: string;
  language: string;
  image_base_url?: string | null;
  small_image_url: string | null;
  large_image_url: string | null;
  set_name?: string | null;
}

export interface CardAttack {
  name?: string;
  cost?: string[];
  damage?: string | number;
  effect?: string;
}

export interface CardAbility {
  type?: string;
  name?: string;
  effect?: string;
}

export interface CardDetail {
  id?: string | number | null;
  source?: string;
  external_id: string;
  set_id?: string | null;
  local_id: string;
  name: string;
  language: string;
  image_base_url?: string | null;
  small_image_url: string | null;
  large_image_url: string | null;
  set?: CardSetBrief | null;
  category?: string | null;
  illustrator?: string | null;
  rarity?: string | null;
  hp?: number | null;
  types?: string[] | null;
  regulation_mark?: string | null;
  regulationMark?: string | null;
  variants?: Record<string, boolean> | null;
  attacks?: CardAttack[] | null;
  abilities?: CardAbility[] | null;
  status?: "available" | "stale" | "unavailable" | string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PaginatedCardsResponse {
  items: CardListItem[];
  total: number | null;
  page: number;
  page_size: number;
  has_more?: boolean;
}

export interface CardEnrichmentDetails {
  category?: string | null;
  illustrator?: string | null;
  rarity?: string | null;
  hp?: number | null;
  types?: string[] | null;
  regulationMark?: string | null;
  variants?: Record<string, boolean> | null;
  attacks?: CardAttack[] | null;
  abilities?: CardAbility[] | null;
}

export interface CardEnrichmentResponse {
  status: "available" | "stale" | "unavailable" | string;
  source: string;
  fetched_at: string | null;
  details: CardEnrichmentDetails | null;
}

// Browser requests stay on the web app's origin. Next.js proxies /api requests
// to the API container, so production does not expose an internal Docker host.
const API_BASE_URL = "";

/**
 * Fetch backend health status from /api/v1/health.
 */
export async function getHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (res.ok || res.status === 503) {
      const data = (await res.json()) as HealthResponse;
      return {
        status: data.status ?? "degraded",
        database: data.database ?? "disconnected",
      };
    }

    return { status: "disconnected", database: "disconnected" };
  } catch {
    return { status: "disconnected", database: "disconnected" };
  }
}

/**
 * Fetch paginated sets from /api/v1/sets.
 */
export async function getSets(params?: {
  page?: number;
  page_size?: number;
  language?: string;
}): Promise<PaginatedSetsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", params.page.toString());
  if (params?.page_size)
    searchParams.set("page_size", params.page_size.toString());
  if (params?.language) searchParams.set("language", params.language);

  const query = searchParams.toString();
  const url = `${API_BASE_URL}/api/v1/sets${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch sets: HTTP ${res.status}`);
  }

  return res.json() as Promise<PaginatedSetsResponse>;
}

/**
 * Fetch a single set's metadata and card count from /api/v1/sets/{id}.
 */
export async function getSet(id: string): Promise<SetDetail> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/sets/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch set ${id}: HTTP ${res.status}`);
  }

  return res.json() as Promise<SetDetail>;
}

/**
 * Fetch paginated cards matching filters from /api/v1/cards.
 */
export async function getCards(params?: {
  name?: string;
  number?: string;
  set_id?: string;
  language?: string;
  page?: number;
  page_size?: number;
}): Promise<PaginatedCardsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.name) searchParams.set("name", params.name);
  if (params?.number) searchParams.set("number", params.number);
  if (params?.set_id) searchParams.set("set_id", params.set_id);
  if (params?.language) searchParams.set("language", params.language);
  if (params?.page) searchParams.set("page", params.page.toString());
  if (params?.page_size)
    searchParams.set("page_size", params.page_size.toString());

  const query = searchParams.toString();
  const url = `${API_BASE_URL}/api/v1/cards${query ? `?${query}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch cards: HTTP ${res.status}`);
  }

  return res.json() as Promise<PaginatedCardsResponse>;
}

/**
 * Fetch card metadata from /api/v1/cards/{id}.
 */
export async function getCard(id: string): Promise<CardDetail> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/cards/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch card ${id}: HTTP ${res.status}`);
  }

  return res.json() as Promise<CardDetail>;
}

/**
 * Fetch on-demand remote enrichment details from /api/v1/cards/{id}/details.
 */
export async function getCardDetails(
  id: string
): Promise<CardEnrichmentResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/cards/${encodeURIComponent(id)}/details`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(
      `Failed to fetch card details for ${id}: HTTP ${res.status}`
    );
  }

  return res.json() as Promise<CardEnrichmentResponse>;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export interface Point {
  x: number;
  y: number;
}

export interface CropCorners {
  top_left: Point;
  top_right: Point;
  bottom_right: Point;
  bottom_left: Point;
}

export interface DetectResponse {
  detected: boolean;
  corners: CropCorners;
  message: string;
  score: number;
}

export interface CropRequest {
  corners: CropCorners;
  rotation?: number;
  expected_version: number;
}

export interface ConfirmCropRequest {
  crop_version: number;
}

export interface CandidateMatchItem {
  id: string;
  name: string;
  local_id: string;
  set_id: string;
  set_name: string;
  image_url: string | null;
  score: number;
  reasons: string[];
  hp?: string | null;
  matched_attacks?: string[];
  matched_abilities?: string[];
  visual_similarity?: number | null;
}

export interface ConfirmedCardInfo {
  id: string;
  name: string;
  set_name: string;
  number: string;
  image_url: string | null;
  confirmed_at: string;
}

export interface FieldEvidenceItem {
  raw_text?: string | null;
  normalized?: string | null;
  confidence_level: "high" | "medium" | "low" | "uncertain" | string;
  source_region?: string | null;
  alternatives?: string[];
}

export interface ImageQualityInfo {
  width: number;
  height: number;
  is_low_res: boolean;
  warning?: string | null;
  guidance?: string | null;
}

export interface RecognitionEvidence {
  name: FieldEvidenceItem;
  number: FieldEvidenceItem;
  denominator: FieldEvidenceItem;
  set_info: FieldEvidenceItem;
  image_quality: ImageQualityInfo;
  hp?: string | null;
  attacks?: string[];
  abilities?: string[];
}

export interface RecognizeResponse {
  recognition_id: string;
  crop_version: number;
  raw_text: string;
  recognized_name: string | null;
  recognized_number: string | null;
  recognized_set_code: string | null;
  ocr_confidence: number;
  confidence_state?: "high" | "medium" | "low" | string;
  image_quality?: ImageQualityInfo | null;
  evidence?: RecognitionEvidence | null;
  catalog_status?: "ok" | "unavailable" | string;
  catalog_error?: string | null;
  search_version?: number;
  card_selection_version?: number;
  candidates: CandidateMatchItem[];
  total_candidates: number;
}

export interface SearchCandidatesRequest {
  name?: string | null;
  number?: string | null;
  set_id?: string | null;
  set_code?: string | null;
  expected_crop_version: number;
  expected_search_version?: number;
}

export interface SearchCandidatesResponse {
  search_version: number;
  crop_version: number;
  confidence_state?: "high" | "medium" | "low" | string;
  catalog_status?: "ok" | "unavailable" | string;
  candidates: CandidateMatchItem[];
  total_candidates: number;
}

export interface ConfirmCardRequest {
  card_id: string;
  expected_crop_version: number;
  expected_search_version?: number;
  expected_selection_version?: number;
}

export interface ResetCardConfirmationRequest {
  expected_crop_version: number;
  expected_selection_version?: number;
}

export interface ScanResponse {
  id: string;
  status: string;
  image_url: string;
  width: number;
  height: number;
  content_type: string;
  file_size: number;
  created_at: string;
  expires_at: string;

  // Phase 4 fields
  crop_status?: "none" | "detected" | "preview" | "confirmed" | string;
  corners?: CropCorners | null;
  rotation?: number;
  crop_image_url?: string | null;
  crop_width?: number | null;
  crop_height?: number | null;
  crop_file_size?: number | null;
  crop_version?: number;
  confirmed_at?: string | null;

  // Phase 5 fields
  recognition_status?: "none" | "processing" | "completed" | "failed" | string;
  recognition_id?: string | null;
  ocr_crop_version?: number | null;
  ocr_raw_text?: string | null;
  recognized_name?: string | null;
  recognized_number?: string | null;
  recognized_set_code?: string | null;
  ocr_confidence?: number | null;
  confidence_state?: "high" | "medium" | "low" | string;
  image_quality?: ImageQualityInfo | null;
  evidence?: RecognitionEvidence | null;
  search_version?: number;
  candidate_search_version?: number;
  card_selection_version?: number;
  catalog_status?: "none" | "ok" | "unavailable" | string;
  catalog_error?: string | null;
  user_search_name?: string | null;
  user_search_number?: string | null;
  user_search_set_code?: string | null;
  user_search_provider_set_id?: string | null;
  candidates?: CandidateMatchItem[] | null;
  confirmed_card?: ConfirmedCardInfo | null;
}

export class ApiError extends Error {
  code?: string;
  status: number;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function parseApiError(
  res: Response,
  fallbackMsg: string
): Promise<ApiError> {
  let errorMsg = `${fallbackMsg}: HTTP ${res.status}`;
  let errorCode: string | undefined;
  try {
    const err = await res.json();
    if (err?.detail && typeof err.detail === "object") {
      errorMsg = err.detail.message || errorMsg;
      errorCode = err.detail.code;
    } else if (typeof err?.detail === "string") {
      errorMsg = err.detail;
    } else if (err?.message) {
      errorMsg = err.message;
      errorCode = err.code;
    }
  } catch {
    // Non-JSON response
  }
  return new ApiError(errorMsg, res.status, errorCode);
}

/**
 * Upload a single card image file to /api/v1/scans.
 */
export async function uploadScan(file: File): Promise<ScanResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/v1/scans`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw await parseApiError(res, "Upload failed");
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Fetch scan metadata from /api/v1/scans/{id}.
 */
export async function getScan(id: string): Promise<ScanResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Failed to fetch scan");
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Build absolute URL for the stored scan image.
 */
export function getScanImageUrl(id: string): string {
  return `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/image`;
}

/**
 * Request automatic card corner detection for a scan.
 */
export async function detectCard(id: string): Promise<DetectResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/detect`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Card detection failed");
  }

  return res.json() as Promise<DetectResponse>;
}

/**
 * Request perspective-corrected crop preview with specified corners and rotation.
 */
export async function cropScan(
  id: string,
  request: CropRequest
): Promise<ScanResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/crop`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(request),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Crop generation failed");
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Confirm the current previewed crop version.
 */
export async function confirmCrop(
  id: string,
  request: ConfirmCropRequest
): Promise<ScanResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(request),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Crop confirmation failed");
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Build absolute URL for the cropped card image.
 */
export function getScanCropImageUrl(
  id: string,
  version?: number | null
): string {
  const query =
    version !== undefined && version !== null ? `?v=${version}` : "";
  return `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/crop/image${query}`;
}

/**
 * Trigger OCR card text recognition and initial catalog matching on confirmed crop.
 */
export async function recognizeCard(id: string): Promise<RecognizeResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/recognize`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Card recognition failed");
  }

  return res.json() as Promise<RecognizeResponse>;
}

/**
 * Search catalog candidates with corrected card name, number, or set.
 */
export async function searchCardCandidates(
  id: string,
  request: SearchCandidatesRequest
): Promise<SearchCandidatesResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/search-candidates`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(request),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Candidate search failed");
  }

  return res.json() as Promise<SearchCandidatesResponse>;
}

/**
 * Explicitly confirm a matched catalog card.
 */
export async function confirmCatalogCard(
  id: string,
  request: ConfirmCardRequest
): Promise<ScanResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/confirm-card`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(request),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Card confirmation failed");
  }

  return res.json() as Promise<ScanResponse>;
}

/**
 * Reset confirmed card selection while preserving the confirmed crop.
 */
export async function resetCatalogCardConfirmation(
  id: string,
  request: ResetCardConfirmationRequest
): Promise<ScanResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(id)}/reset-card-confirmation`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(request),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Reset card confirmation failed");
  }

  return res.json() as Promise<ScanResponse>;
}

// -------------------------------------------------------------
// Phase 6: Personal Collection & Scan Library Types & API
// -------------------------------------------------------------

export type CollectionCondition =
  | "mint"
  | "near_mint"
  | "lightly_played"
  | "moderately_played"
  | "heavily_played"
  | "damaged";

export type CollectionVariant =
  | "normal"
  | "holo"
  | "reverse_holo"
  | "first_edition"
  | "promo"
  | "masterball"
  | "pokeball";

export interface CollectionItem {
  id: string;
  card_id: string;
  provider: string;
  card_name: string;
  set_id: string;
  set_name: string;
  collector_number: string;
  card_image_url: string | null;
  quantity: number;
  language: string;
  variant: CollectionVariant;
  condition: CollectionCondition;
  notes: string | null;
  purchase_price: number | string | null;
  currency: string | null;
  acquired_at: string | null;
  source_scan_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionListResponse {
  items: CollectionItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface CollectionSetDistributionItem {
  set_id: string;
  set_name: string;
  count: number;
  total_cards: number;
}

export interface CollectionStats {
  total_cards: number;
  unique_cards: number;
  total_sets: number;
  duplicate_count: number;
  condition_distribution: Record<string, number>;
  set_distribution: CollectionSetDistributionItem[];
  recent_additions: CollectionItem[];
}

export interface CreateCollectionItemRequest {
  card_id: string;
  provider?: string;
  card_name?: string | null;
  set_id?: string | null;
  set_name?: string | null;
  collector_number?: string | null;
  card_image_url?: string | null;
  quantity?: number;
  language?: string;
  variant?: CollectionVariant;
  condition?: CollectionCondition;
  notes?: string | null;
  purchase_price?: number | null;
  currency?: string | null;
  acquired_at?: string | null;
  source_scan_id?: string | null;
}

export interface UpdateCollectionItemRequest {
  quantity?: number;
  condition?: CollectionCondition;
  variant?: CollectionVariant;
  notes?: string | null;
  purchase_price?: number | null;
  currency?: string | null;
  acquired_at?: string | null;
  expected_version: number;
}

export interface AddFromScanRequest {
  condition?: CollectionCondition;
  variant?: CollectionVariant;
  quantity?: number;
  notes?: string | null;
  purchase_price?: number | null;
  currency?: string | null;
  acquired_at?: string | null;
}

/**
 * Retrieve personal collection items with filtering, sorting, and pagination.
 */
export async function getCollection(params?: {
  q?: string;
  query?: string;
  set_id?: string;
  condition?: string;
  language?: string;
  variant?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}): Promise<CollectionListResponse> {
  const searchParams = new URLSearchParams();
  const qVal = params?.q ?? params?.query;
  if (qVal) searchParams.set("query", qVal);
  if (params?.set_id) searchParams.set("set_id", params.set_id);
  if (params?.condition) searchParams.set("condition", params.condition);
  if (params?.language) searchParams.set("language", params.language);
  if (params?.variant) searchParams.set("variant", params.variant);
  if (params?.sort) searchParams.set("sort", params.sort);
  if (params?.page) searchParams.set("page", params.page.toString());
  if (params?.page_size)
    searchParams.set("page_size", params.page_size.toString());

  const queryStr = searchParams.toString();
  const url = `${API_BASE_URL}/api/v1/collection${queryStr ? `?${queryStr}` : ""}`;

  const res = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!res.ok) {
    throw await parseApiError(res, "Ophalen van collectie mislukt");
  }

  return res.json() as Promise<CollectionListResponse>;
}

/**
 * Retrieve a single collection item by UUID.
 */
export async function getCollectionItem(id: string): Promise<CollectionItem> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/collection/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, `Collectie-item ${id} niet gevonden`);
  }

  return res.json() as Promise<CollectionItem>;
}

/**
 * Retrieve aggregated collection summary metrics and distribution stats.
 */
export async function getCollectionStats(): Promise<CollectionStats> {
  const res = await fetch(`${API_BASE_URL}/api/v1/collection/stats`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  if (!res.ok) {
    throw await parseApiError(res, "Ophalen van collectiestatistieken mislukt");
  }

  return res.json() as Promise<CollectionStats>;
}

/**
 * Manually add a card specimen to personal collection.
 */
export async function createCollectionItem(
  data: CreateCollectionItemRequest
): Promise<CollectionItem> {
  const res = await fetch(`${API_BASE_URL}/api/v1/collection`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    cache: "no-store",
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    throw await parseApiError(res, "Toevoegen aan collectie mislukt");
  }

  return res.json() as Promise<CollectionItem>;
}

/**
 * Update editable attributes of a collection item with optimistic concurrency.
 */
export async function updateCollectionItem(
  id: string,
  data: UpdateCollectionItemRequest
): Promise<CollectionItem> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/collection/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: JSON.stringify(data),
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Bijwerken van collectie-item mislukt");
  }

  return res.json() as Promise<CollectionItem>;
}

/**
 * Remove a card specimen from personal collection.
 */
export async function deleteCollectionItem(id: string): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/collection/${encodeURIComponent(id)}`,
    {
      method: "DELETE",
      cache: "no-store",
    }
  );

  if (!res.ok && res.status !== 204) {
    throw await parseApiError(res, "Verwijderen van kaart mislukt");
  }
}

/**
 * Add a verified, confirmed scan card to personal collection (idempotent).
 */
export async function addScanToCollection(
  scanId: string,
  data?: AddFromScanRequest
): Promise<CollectionItem> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(scanId)}/collection`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      cache: "no-store",
      body: data ? JSON.stringify(data) : undefined,
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Scan toevoegen aan collectie mislukt");
  }

  return res.json() as Promise<CollectionItem>;
}

/** Return the collection item linked to this exact scan, if already added. */
export async function getScanCollectionItem(
  scanId: string
): Promise<CollectionItem | null> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scans/${encodeURIComponent(scanId)}/collection`,
    { cache: "no-store" }
  );

  if (res.status === 404) return null;
  if (!res.ok) {
    throw await parseApiError(res, "Collectiestatus van scan ophalen mislukt");
  }
  return res.json() as Promise<CollectionItem>;
}

// -------------------------------------------------------------
// Phase 7: Live Scan & Go Session Types & API
// -------------------------------------------------------------

export interface ScanSessionResponse {
  id: string;
  status: "active" | "completed" | "abandoned" | string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  total_scans: number;
}

export interface ScanSessionItemResponse {
  scan_id: string;
  session_id: string | null;
  status: string;
  crop_status: string;
  created_at: string;
  image_url: string;
  crop_image_url: string | null;
  best_match: CandidateMatchItem | null;
  candidates: CandidateMatchItem[];
  confirmed_card: ConfirmedCardInfo | null;
  in_collection: boolean;
  collection_quantity: number;
  collection_item_id: string | null;
}

export interface ScanSessionDetailResponse {
  id: string;
  status: "active" | "completed" | "abandoned" | string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  total_scans: number;
  items: ScanSessionItemResponse[];
}

export interface LiveCaptureResponse {
  scan: ScanResponse;
  detected: boolean;
  corners: CropCorners | null;
  candidates: CandidateMatchItem[];
  best_match: CandidateMatchItem | null;
  in_collection: boolean;
  collection_quantity: number;
  collection_item_id: string | null;
  session_id: string;
  session_status: string;
}

/**
 * Create a new live scan session for continuous camera scanning.
 */
export async function createScanSession(): Promise<ScanSessionResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/scan-sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    cache: "no-store",
    body: JSON.stringify({}),
  });

  if (!res.ok) {
    throw await parseApiError(res, "Aanmaken van scansessie mislukt");
  }

  return res.json() as Promise<ScanSessionResponse>;
}

/**
 * Retrieve scan session details including scanned items.
 */
export async function getScanSession(
  id: string
): Promise<ScanSessionDetailResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scan-sessions/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Ophalen van scansessie mislukt");
  }

  return res.json() as Promise<ScanSessionDetailResponse>;
}

/**
 * Capture a live camera frame within an active scan session.
 * Sends multipart/form-data with the image file.
 */
export async function captureLiveScanFrame(
  sessionId: string,
  imageFile: File | Blob
): Promise<LiveCaptureResponse> {
  const formData = new FormData();
  if (imageFile instanceof File) {
    formData.append("file", imageFile);
  } else {
    formData.append("file", imageFile, "live_frame.jpg");
  }

  const res = await fetch(
    `${API_BASE_URL}/api/v1/scan-sessions/${encodeURIComponent(sessionId)}/capture`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
      body: formData,
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Vastleggen van live scanframe mislukt");
  }

  return res.json() as Promise<LiveCaptureResponse>;
}

/**
 * Mark an active scan session as completed.
 */
export async function completeScanSession(
  id: string
): Promise<ScanSessionResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/scan-sessions/${encodeURIComponent(id)}/complete`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw await parseApiError(res, "Afronden van scansessie mislukt");
  }

  return res.json() as Promise<ScanSessionResponse>;
}

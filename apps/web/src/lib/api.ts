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

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

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
